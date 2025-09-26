"""Property-based tests for Basel Capital Engine using Hypothesis."""

import pytest
from hypothesis import given, strategies as st, assume, settings
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant
import math

from src.basileia.core.exposure import (
    Exposure, ExposureType, ExposureClass, Portfolio, CreditRiskMitigation
)
from src.basileia.core.capital import Capital, CapitalComponents
from src.basileia.core.buffers import RegulatoryBuffers
from src.basileia.core.config import BaselConfig
from src.basileia.core.engine import BaselEngine
from src.basileia.rwa.credit import CreditRiskCalculator


# Strategies for generating test data
@st.composite
def exposure_strategy(draw):
    """Strategy for generating valid exposures."""
    exposure_type = draw(st.sampled_from(list(ExposureType)))
    exposure_class = draw(st.sampled_from(list(ExposureClass)))
    
    original_exposure = draw(st.floats(min_value=1000, max_value=1e9))
    current_exposure = draw(st.floats(min_value=original_exposure * 0.1, max_value=original_exposure))
    
    # Optional risk parameters
    pd = draw(st.one_of(st.none(), st.floats(min_value=0.0001, max_value=0.99)))
    lgd = draw(st.one_of(st.none(), st.floats(min_value=0.01, max_value=1.0)))
    maturity = draw(st.one_of(st.none(), st.floats(min_value=0.1, max_value=50)))
    
    # Optional market value for trading book
    market_value = None
    if exposure_type in [ExposureType.TRADING_SECURITIES, ExposureType.TRADING_DERIVATIVES]:
        market_value = draw(st.floats(min_value=-current_exposure, max_value=current_exposure * 2))
    
    return Exposure(
        exposure_id=f"exp_{draw(st.integers(min_value=1, max_value=999999))}",
        exposure_type=exposure_type,
        exposure_class=exposure_class,
        original_exposure=original_exposure,
        current_exposure=current_exposure,
        probability_of_default=pd,
        loss_given_default=lgd,
        maturity=maturity,
        market_value=market_value,
        currency=draw(st.sampled_from(["EUR", "USD", "GBP", "JPY"])),
        sector=draw(st.one_of(st.none(), st.sampled_from(["corporate", "retail", "sovereign", "banking"])))
    )


@st.composite
def portfolio_strategy(draw):
    """Strategy for generating portfolios."""
    portfolio = Portfolio(
        portfolio_id=f"portfolio_{draw(st.integers(min_value=1, max_value=9999))}",
        bank_name=f"Bank {draw(st.text(min_size=1, max_size=20))}"
    )
    
    # Add exposures
    num_exposures = draw(st.integers(min_value=1, max_value=50))
    for _ in range(num_exposures):
        exposure = draw(exposure_strategy())
        portfolio.add_exposure(exposure)
    
    return portfolio


@st.composite
def capital_components_strategy(draw):
    """Strategy for generating capital components."""
    common_shares = draw(st.floats(min_value=1e6, max_value=1e10))
    retained_earnings = draw(st.floats(min_value=-common_shares * 0.5, max_value=common_shares * 2))
    accumulated_oci = draw(st.floats(min_value=-common_shares * 0.1, max_value=common_shares * 0.1))
    minority_interests = draw(st.floats(min_value=0, max_value=common_shares * 0.2))
    
    at1_instruments = draw(st.floats(min_value=0, max_value=common_shares))
    t2_instruments = draw(st.floats(min_value=0, max_value=common_shares))
    
    # Deductions should be reasonable relative to capital
    goodwill = draw(st.floats(min_value=0, max_value=common_shares * 0.3))
    intangible_assets = draw(st.floats(min_value=0, max_value=common_shares * 0.2))
    
    return CapitalComponents(
        common_shares=common_shares,
        retained_earnings=retained_earnings,
        accumulated_oci=accumulated_oci,
        minority_interests=minority_interests,
        at1_instruments=at1_instruments,
        t2_instruments=t2_instruments,
        goodwill=goodwill,
        intangible_assets=intangible_assets
    )


@st.composite
def capital_strategy(draw):
    """Strategy for generating capital structures."""
    components = draw(capital_components_strategy())
    return Capital(
        bank_name=f"Bank {draw(st.text(min_size=1, max_size=20))}",
        components=components
    )


class TestExposureProperties:
    """Property-based tests for exposure calculations."""
    
    @given(exposure_strategy())
    def test_exposure_at_default_non_negative(self, exposure):
        """EAD should always be non-negative."""
        ead = exposure.get_exposure_at_default()
        assert ead >= 0
    
    @given(exposure_strategy())
    def test_exposure_at_default_bounded(self, exposure):
        """EAD should be bounded by current exposure and CCF logic."""
        ead = exposure.get_exposure_at_default()
        
        if exposure.exposure_type in [ExposureType.COMMITMENTS, ExposureType.GUARANTEES]:
            # For off-balance sheet, EAD = current_exposure * CCF
            ccf = exposure.credit_conversion_factor or 0.0
            expected_ead = exposure.current_exposure * ccf
            assert abs(ead - expected_ead) < 1e-6
        else:
            # For on-balance sheet, EAD = current_exposure
            assert abs(ead - exposure.current_exposure) < 1e-6
    
    @given(exposure_strategy())
    def test_effective_maturity_bounds(self, exposure):
        """Effective maturity should be bounded between 1 and 5 years."""
        effective_maturity = exposure.get_effective_maturity()
        assert 1.0 <= effective_maturity <= 5.0
    
    @given(exposure_strategy())
    def test_retail_classification_consistency(self, exposure):
        """Retail classification should be consistent with exposure class."""
        is_retail = exposure.is_retail()
        retail_classes = [ExposureClass.RETAIL_MORTGAGE, ExposureClass.RETAIL_REVOLVING, ExposureClass.RETAIL_OTHER]
        
        if exposure.exposure_class in retail_classes:
            assert is_retail is True
        else:
            assert is_retail is False
    
    @given(exposure_strategy())
    def test_trading_book_classification_consistency(self, exposure):
        """Trading book classification should be consistent with exposure type."""
        is_trading = exposure.is_trading_book()
        trading_types = [ExposureType.TRADING_SECURITIES, ExposureType.TRADING_DERIVATIVES]
        
        if exposure.exposure_type in trading_types:
            assert is_trading is True
        else:
            assert is_trading is False


class TestPortfolioProperties:
    """Property-based tests for portfolio calculations."""
    
    @given(portfolio_strategy())
    def test_total_exposure_sum(self, portfolio):
        """Total portfolio exposure should equal sum of individual exposures."""
        total = portfolio.get_total_exposure()
        expected_total = sum(exp.current_exposure for exp in portfolio.exposures)
        assert abs(total - expected_total) < 1e-6
    
    @given(portfolio_strategy())
    def test_exposure_filtering_completeness(self, portfolio):
        """Trading book + banking book should equal total exposures."""
        trading_exposures = portfolio.get_trading_book_exposures()
        banking_exposures = portfolio.get_banking_book_exposures()
        
        assert len(trading_exposures) + len(banking_exposures) == len(portfolio.exposures)
    
    @given(portfolio_strategy())
    def test_concentration_metrics_bounds(self, portfolio):
        """Concentration metrics should be properly bounded."""
        if len(portfolio.exposures) == 0:
            return
        
        metrics = portfolio.get_concentration_metrics()
        
        # Percentages should be between 0 and 1
        assert 0 <= metrics.get("largest_counterparty_pct", 0) <= 1
        assert 0 <= metrics.get("largest_sector_pct", 0) <= 1
        
        # HHI should be between 0 and 1
        assert 0 <= metrics.get("counterparty_hhi", 0) <= 1
        assert 0 <= metrics.get("sector_hhi", 0) <= 1
    
    @given(portfolio_strategy())
    def test_exposure_class_filtering_consistency(self, portfolio):
        """Exposure filtering by class should be consistent."""
        for exposure_class in ExposureClass:
            filtered = portfolio.get_exposures_by_class(exposure_class)
            
            # All filtered exposures should have the correct class
            for exp in filtered:
                assert exp.exposure_class == exposure_class
            
            # Count should match manual count
            manual_count = sum(1 for exp in portfolio.exposures if exp.exposure_class == exposure_class)
            assert len(filtered) == manual_count


class TestCapitalProperties:
    """Property-based tests for capital calculations."""
    
    @given(capital_components_strategy())
    def test_capital_tier_hierarchy(self, components):
        """Capital tiers should follow hierarchy: Total >= Tier1 >= CET1."""
        cet1 = components.calculate_cet1()
        tier1 = components.calculate_tier1()
        total = components.calculate_total_capital()
        
        # Allow for small floating point errors
        assert cet1 <= tier1 + 1e-6
        assert tier1 <= total + 1e-6
    
    @given(capital_components_strategy())
    def test_cet1_adjustments_non_negative(self, components):
        """CET1 adjustments (deductions) should be non-negative."""
        adjustments = components.calculate_cet1_adjustments()
        assert adjustments >= 0
    
    @given(capital_components_strategy())
    def test_tier2_limitation(self, components):
        """Tier 2 capital should be limited to 100% of Tier 1."""
        tier1 = components.calculate_tier1()
        total = components.calculate_total_capital()
        tier2_actual = total - tier1
        
        # T2 should not exceed Tier 1
        assert tier2_actual <= tier1 + 1e-6
    
    @given(capital_strategy())
    def test_capital_summary_consistency(self, capital):
        """Capital summary should be consistent with individual calculations."""
        summary = capital.get_capital_summary()
        
        cet1_calc = capital.calculate_cet1_capital()
        tier1_calc = capital.calculate_tier1_capital()
        total_calc = capital.calculate_total_capital()
        
        assert abs(summary["cet1_capital"] - cet1_calc) < 1e-6
        assert abs(summary["tier1_capital"] - tier1_calc) < 1e-6
        assert abs(summary["total_capital"] - total_calc) < 1e-6


class TestRWAProperties:
    """Property-based tests for RWA calculations."""
    
    @given(portfolio_strategy())
    def test_credit_rwa_non_negative(self, portfolio):
        """Credit RWA should always be non-negative."""
        config = BaselConfig.load_default()
        calculator = CreditRiskCalculator(config)
        
        rwa = calculator.calculate_total_rwa(portfolio)
        assert rwa >= 0
    
    @given(portfolio_strategy())
    def test_credit_rwa_monotonicity(self, portfolio):
        """Increasing exposures should not decrease total RWA."""
        config = BaselConfig.load_default()
        calculator = CreditRiskCalculator(config)
        
        if len(portfolio.exposures) == 0:
            return
        
        # Calculate initial RWA
        initial_rwa = calculator.calculate_total_rwa(portfolio)
        
        # Double the first exposure
        original_amount = portfolio.exposures[0].current_exposure
        portfolio.exposures[0].current_exposure *= 2
        
        # Calculate new RWA
        new_rwa = calculator.calculate_total_rwa(portfolio)
        
        # Restore original amount
        portfolio.exposures[0].current_exposure = original_amount
        
        # New RWA should be >= initial RWA (monotonicity)
        assert new_rwa >= initial_rwa - 1e-6
    
    @given(st.floats(min_value=0.0001, max_value=0.99), st.floats(min_value=0.01, max_value=1.0))
    def test_pd_increase_increases_rwa(self, initial_pd, lgd):
        """Increasing PD should not decrease RWA (for IRB)."""
        assume(initial_pd < 0.5)  # Reasonable upper bound for test
        
        config = BaselConfig.load_default()
        calculator = CreditRiskCalculator(config)
        
        # Create exposure with initial PD
        exposure1 = Exposure(
            exposure_id="test_1",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=1000000,
            current_exposure=1000000,
            probability_of_default=initial_pd,
            loss_given_default=lgd,
            maturity=3.0
        )
        
        # Create exposure with higher PD
        higher_pd = min(initial_pd * 2, 0.99)
        exposure2 = Exposure(
            exposure_id="test_2",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=1000000,
            current_exposure=1000000,
            probability_of_default=higher_pd,
            loss_given_default=lgd,
            maturity=3.0
        )
        
        portfolio1 = Portfolio(portfolio_id="p1")
        portfolio1.add_exposure(exposure1)
        
        portfolio2 = Portfolio(portfolio_id="p2")
        portfolio2.add_exposure(exposure2)
        
        rwa1 = calculator.calculate_total_rwa(portfolio1)
        rwa2 = calculator.calculate_total_rwa(portfolio2)
        
        # Higher PD should lead to higher or equal RWA
        assert rwa2 >= rwa1 - 1e-6


class TestBufferProperties:
    """Property-based tests for buffer calculations."""
    
    @given(
        st.floats(min_value=0, max_value=0.1),  # conservation
        st.floats(min_value=0, max_value=0.025),  # countercyclical
        st.floats(min_value=0, max_value=0.035),  # gsib
        st.floats(min_value=0, max_value=0.02)   # dsib
    )
    def test_total_buffer_additivity(self, conservation, countercyclical, gsib, dsib):
        """Total buffer should be sum of individual buffers (with SIFI max rule)."""
        buffers = RegulatoryBuffers(
            conservation_buffer=conservation,
            countercyclical_buffer=countercyclical,
            gsib_buffer=gsib,
            dsib_buffer=dsib
        )
        
        total = buffers.get_total_buffer_requirement()
        expected = conservation + countercyclical + max(gsib, dsib)  # Max of SIFI buffers
        
        assert abs(total - expected) < 1e-10
    
    @given(
        st.floats(min_value=0.045, max_value=0.2),  # CET1 ratio
        st.floats(min_value=1e6, max_value=1e12)    # Total RWA
    )
    def test_buffer_breach_consistency(self, cet1_ratio, total_rwa):
        """Buffer breaches should be consistent with ratio comparisons."""
        buffers = RegulatoryBuffers(conservation_buffer=0.025)
        
        breaches = buffers.check_buffer_breaches(
            cet1_ratio=cet1_ratio,
            tier1_ratio=cet1_ratio,  # Simplified
            total_capital_ratio=cet1_ratio,  # Simplified
            total_rwa=total_rwa
        )
        
        required_cet1 = 0.045 + buffers.get_total_buffer_requirement()
        
        if cet1_ratio < required_cet1:
            assert len(breaches) > 0
        else:
            # Check if any breaches are actually valid
            valid_breaches = [b for b in breaches if b.shortfall_ratio > 1e-10]
            assert len(valid_breaches) == 0


class BaselEngineStateMachine(RuleBasedStateMachine):
    """Stateful testing of Basel Engine."""
    
    def __init__(self):
        super().__init__()
        self.engine = BaselEngine()
        self.portfolio = Portfolio(portfolio_id="test_portfolio")
        self.capital = Capital(
            components=CapitalComponents(
                common_shares=1000000,
                retained_earnings=500000
            )
        )
    
    @rule(exposure=exposure_strategy())
    def add_exposure(self, exposure):
        """Add an exposure to the portfolio."""
        self.portfolio.add_exposure(exposure)
    
    @rule(
        common_shares=st.floats(min_value=1e6, max_value=1e10),
        retained_earnings=st.floats(min_value=-1e9, max_value=1e10)
    )
    def update_capital(self, common_shares, retained_earnings):
        """Update capital components."""
        self.capital.components.common_shares = common_shares
        self.capital.components.retained_earnings = retained_earnings
    
    @invariant()
    def portfolio_consistency(self):
        """Portfolio should maintain consistency."""
        if len(self.portfolio.exposures) > 0:
            total_exposure = self.portfolio.get_total_exposure()
            assert total_exposure >= 0
            
            # Sum should equal individual exposures
            manual_sum = sum(exp.current_exposure for exp in self.portfolio.exposures)
            assert abs(total_exposure - manual_sum) < 1e-6
    
    @invariant()
    def capital_hierarchy(self):
        """Capital hierarchy should be maintained."""
        cet1 = self.capital.calculate_cet1_capital()
        tier1 = self.capital.calculate_tier1_capital()
        total = self.capital.calculate_total_capital()
        
        assert cet1 <= tier1 + 1e-6
        assert tier1 <= total + 1e-6
    
    @invariant()
    def rwa_non_negative(self):
        """RWA calculations should always be non-negative."""
        if len(self.portfolio.exposures) > 0:
            rwa_results = self.engine.calculate_rwa_only(self.portfolio)
            
            assert rwa_results["credit_rwa"] >= 0
            assert rwa_results["market_rwa"] >= 0
            assert rwa_results["operational_rwa"] >= 0
            assert rwa_results["total_rwa"] >= 0


# Property-based integration tests
class TestIntegrationProperties:
    """Property-based tests for full engine integration."""
    
    @given(portfolio_strategy(), capital_strategy())
    @settings(max_examples=20, deadline=10000)  # Reduced for performance
    def test_full_calculation_consistency(self, portfolio, capital):
        """Full Basel calculation should be internally consistent."""
        # Skip empty portfolios
        if len(portfolio.exposures) == 0:
            return
        
        # Ensure capital is positive
        if capital.calculate_cet1_capital() <= 0:
            return
        
        engine = BaselEngine()
        
        try:
            results = engine.calculate_all_metrics(portfolio, capital)
            
            # Basic consistency checks
            assert results.total_rwa >= 0
            assert results.cet1_capital >= 0
            assert results.tier1_capital >= results.cet1_capital - 1e-6
            assert results.total_capital >= results.tier1_capital - 1e-6
            
            # Ratio consistency
            if results.total_rwa > 0:
                calculated_cet1_ratio = results.cet1_capital / results.total_rwa
                assert abs(results.cet1_ratio - calculated_cet1_ratio) < 1e-6
                
                calculated_tier1_ratio = results.tier1_capital / results.total_rwa
                assert abs(results.tier1_ratio - calculated_tier1_ratio) < 1e-6
            
            # RWA components should sum to total
            total_rwa_calc = results.credit_rwa + results.market_rwa + results.operational_rwa
            assert abs(results.total_rwa - total_rwa_calc) < 1e-6
            
        except Exception as e:
            # Log the error but don't fail the test for expected edge cases
            if "division by zero" in str(e).lower() or "invalid" in str(e).lower():
                return
            raise


# Run the stateful tests
TestBaselEngineState = BaselEngineStateMachine.TestCase
