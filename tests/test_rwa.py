"""Tests for RWA calculation modules."""

import pytest
import numpy as np
from unittest.mock import Mock, patch

from src.basileia.core.config import BaselConfig
from src.basileia.core.exposure import (
    Portfolio, Exposure, ExposureType, ExposureClass, CreditRiskMitigation
)
from src.basileia.rwa.credit import CreditRiskCalculator, CreditApproach
from src.basileia.rwa.market import MarketRiskCalculator, MarketRiskApproach
from src.basileia.rwa.operational import OperationalRiskCalculator, OperationalRiskApproach


class TestCreditRiskCalculator:
    """Test credit risk RWA calculations."""
    
    @pytest.fixture
    def config(self):
        """Basel configuration fixture."""
        return BaselConfig.load_default()
    
    @pytest.fixture
    def calculator(self, config):
        """Credit risk calculator fixture."""
        return CreditRiskCalculator(config)
    
    @pytest.fixture
    def sample_portfolio(self):
        """Sample portfolio fixture."""
        portfolio = Portfolio(portfolio_id="test")
        
        # Add sovereign exposure
        sovereign_exp = Exposure(
            exposure_id="sovereign_001",
            exposure_type=ExposureType.SECURITIES,
            exposure_class=ExposureClass.SOVEREIGN,
            original_exposure=1000000,
            current_exposure=1000000,
            external_rating="AAA"
        )
        
        # Add corporate exposure
        corporate_exp = Exposure(
            exposure_id="corporate_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=2000000,
            current_exposure=1800000,
            external_rating="BBB",
            probability_of_default=0.02,
            loss_given_default=0.45,
            maturity=3.0
        )
        
        # Add retail mortgage
        retail_exp = Exposure(
            exposure_id="retail_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.RETAIL_MORTGAGE,
            original_exposure=500000,
            current_exposure=450000,
            probability_of_default=0.01,
            loss_given_default=0.25,
            maturity=25.0
        )
        
        portfolio.add_exposure(sovereign_exp)
        portfolio.add_exposure(corporate_exp)
        portfolio.add_exposure(retail_exp)
        
        return portfolio
    
    def test_standardized_approach_calculation(self, calculator, sample_portfolio):
        """Test standardized approach RWA calculation."""
        rwa = calculator.calculate_standardized_rwa(sample_portfolio)
        
        assert rwa > 0
        
        # Sovereign AAA should have 0% risk weight
        # Corporate BBB should have 100% risk weight
        # Retail mortgage should have 35% risk weight
        # Expected: 0 + 1,800,000 * 1.0 + 450,000 * 0.35 = 2,057,500
        expected_rwa = 1800000 * 1.0 + 450000 * 0.35
        assert abs(rwa - expected_rwa) < 10000  # Allow for small differences
    
    def test_irb_approach_calculation(self, calculator, sample_portfolio):
        """Test IRB approach RWA calculation."""
        rwa = calculator.calculate_irb_rwa(sample_portfolio, CreditApproach.IRB_ADVANCED)
        
        assert rwa > 0
        
        # IRB should generally produce different results than SA
        sa_rwa = calculator.calculate_standardized_rwa(sample_portfolio)
        assert rwa != sa_rwa
    
    def test_risk_weight_lookup(self, calculator):
        """Test risk weight lookup for different asset classes and ratings."""
        # Test sovereign risk weights
        assert calculator._get_sovereign_risk_weight("AAA") == 0.0
        assert calculator._get_sovereign_risk_weight("A") > 0.0
        assert calculator._get_sovereign_risk_weight("B") > calculator._get_sovereign_risk_weight("A")
        
        # Test corporate risk weights
        assert calculator._get_corporate_risk_weight("AAA") < calculator._get_corporate_risk_weight("BBB")
        assert calculator._get_corporate_risk_weight("unrated") > 0.0
    
    def test_credit_risk_mitigation(self, calculator, config):
        """Test credit risk mitigation effects."""
        # Create exposure with collateral
        crm = CreditRiskMitigation(
            collateral_type="residential_property",
            collateral_value=120000
        )
        
        exposure = Exposure(
            exposure_id="test_crm",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.RETAIL_MORTGAGE,
            original_exposure=100000,
            current_exposure=100000,
            crm=crm
        )
        
        # Calculate RWA with and without CRM
        portfolio_with_crm = Portfolio(portfolio_id="with_crm")
        portfolio_with_crm.add_exposure(exposure)
        
        exposure_no_crm = exposure.model_copy()
        exposure_no_crm.crm = None
        portfolio_no_crm = Portfolio(portfolio_id="no_crm")
        portfolio_no_crm.add_exposure(exposure_no_crm)
        
        rwa_with_crm = calculator.calculate_standardized_rwa(portfolio_with_crm)
        rwa_no_crm = calculator.calculate_standardized_rwa(portfolio_no_crm)
        
        # RWA with CRM should be lower
        assert rwa_with_crm < rwa_no_crm
    
    def test_detailed_breakdown(self, calculator, sample_portfolio):
        """Test detailed RWA breakdown functionality."""
        breakdown = calculator.get_detailed_breakdown(sample_portfolio)
        
        assert "by_exposure_class" in breakdown
        assert "by_rating" in breakdown
        assert "by_geography" in breakdown
        assert "by_sector" in breakdown
        assert "total_ead" in breakdown
        assert "total_rwa" in breakdown
        assert "average_risk_weight" in breakdown
        
        # Check that breakdown sums correctly
        class_total_rwa = sum(v["rwa"] for v in breakdown["by_exposure_class"].values())
        assert abs(class_total_rwa - breakdown["total_rwa"]) < 1e-6
    
    def test_concentration_adjustments(self, calculator):
        """Test concentration risk adjustments."""
        # Create portfolio with concentration
        portfolio = Portfolio(portfolio_id="concentrated")
        
        # Large exposure to single counterparty
        large_exposure = Exposure(
            exposure_id="large_001",
            counterparty_id="large_counterparty",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=5000000,
            current_exposure=5000000
        )
        
        # Small exposure to different counterparty
        small_exposure = Exposure(
            exposure_id="small_001",
            counterparty_id="small_counterparty",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000
        )
        
        portfolio.add_exposure(large_exposure)
        portfolio.add_exposure(small_exposure)
        
        adjustments = calculator.calculate_concentration_adjustments(portfolio)
        
        assert "single_name_addon" in adjustments
        assert "sector_addon" in adjustments
        assert "total_concentration_addon" in adjustments
        
        # Should have concentration adjustment due to large exposure
        assert adjustments["single_name_addon"] > 0


class TestMarketRiskCalculator:
    """Test market risk RWA calculations."""
    
    @pytest.fixture
    def config(self):
        """Basel configuration fixture."""
        return BaselConfig.load_default()
    
    @pytest.fixture
    def calculator(self, config):
        """Market risk calculator fixture."""
        return MarketRiskCalculator(config)
    
    @pytest.fixture
    def trading_portfolio(self):
        """Trading portfolio fixture."""
        portfolio = Portfolio(portfolio_id="trading")
        
        # Add trading securities
        trading_bond = Exposure(
            exposure_id="trading_bond_001",
            exposure_type=ExposureType.TRADING_SECURITIES,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=1000000,
            current_exposure=1000000,
            market_value=980000,
            maturity=5.0,
            sensitivities={
                "ir_5y": 4900,  # 5-year interest rate sensitivity
                "credit_spread": 1960  # Credit spread sensitivity
            }
        )
        
        # Add FX position
        fx_position = Exposure(
            exposure_id="fx_position_001",
            exposure_type=ExposureType.TRADING_SECURITIES,
            exposure_class=ExposureClass.FX,
            original_exposure=500000,
            current_exposure=500000,
            market_value=505000,
            currency="USD",
            sensitivities={
                "fx_delta": 5000  # FX delta sensitivity
            }
        )
        
        # Add derivative
        derivative = Exposure(
            exposure_id="derivative_001",
            exposure_type=ExposureType.DERIVATIVES,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=2000000,  # Notional
            current_exposure=2000000,
            market_value=15000,  # Small MTM
            sensitivities={
                "ir_2y": 1000,
                "ir_5y": 3000,
                "ir_10y": 2000
            }
        )
        
        portfolio.add_exposure(trading_bond)
        portfolio.add_exposure(fx_position)
        portfolio.add_exposure(derivative)
        
        return portfolio
    
    def test_frtb_sa_calculation(self, calculator, trading_portfolio):
        """Test FRTB Sensitivities-Based Approach."""
        rwa = calculator.calculate_frtb_sa_rwa(trading_portfolio.get_trading_book_exposures())
        
        assert rwa > 0
    
    def test_var_calculation(self, calculator, trading_portfolio):
        """Test VaR-based market risk calculation."""
        rwa = calculator.calculate_var_rwa(trading_portfolio.get_trading_book_exposures())
        
        assert rwa > 0
    
    def test_basel2_standardized(self, calculator, trading_portfolio):
        """Test Basel II standardized approach."""
        rwa = calculator.calculate_standardized_rwa(trading_portfolio.get_trading_book_exposures())
        
        assert rwa > 0
    
    def test_risk_classification(self, calculator):
        """Test risk factor classification."""
        # Create different types of exposures
        bond_exposure = Exposure(
            exposure_id="bond",
            exposure_type=ExposureType.TRADING_SECURITIES,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=1000000,
            current_exposure=1000000
        )
        
        equity_exposure = Exposure(
            exposure_id="equity",
            exposure_type=ExposureType.TRADING_SECURITIES,
            exposure_class=ExposureClass.EQUITY,
            original_exposure=1000000,
            current_exposure=1000000
        )
        
        fx_exposure = Exposure(
            exposure_id="fx",
            exposure_type=ExposureType.TRADING_SECURITIES,
            exposure_class=ExposureClass.FX,
            original_exposure=1000000,
            current_exposure=1000000,
            currency="USD"
        )
        
        # Test risk factor identification
        assert calculator._has_interest_rate_risk(bond_exposure) is True
        assert calculator._has_equity_risk(equity_exposure) is True
        assert calculator._has_fx_risk(fx_exposure) is True
    
    def test_sensitivity_extraction(self, calculator):
        """Test sensitivity extraction from exposures."""
        exposure = Exposure(
            exposure_id="test",
            exposure_type=ExposureType.TRADING_SECURITIES,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=1000000,
            current_exposure=1000000,
            sensitivities={
                "ir_2y": 1000,
                "ir_5y": 2000,
                "ir_10y": 1500,
                "credit_spread": 800,
                "fx_delta": 500
            }
        )
        
        ir_sens = calculator._extract_ir_sensitivities(exposure)
        credit_delta = calculator._extract_credit_spread_delta(exposure)
        fx_delta = calculator._extract_fx_delta(exposure)
        
        assert len(ir_sens) == 3
        assert "2y" in ir_sens
        assert "5y" in ir_sens
        assert "10y" in ir_sens
        assert credit_delta == 800
        assert fx_delta == 500
    
    def test_detailed_breakdown(self, calculator, trading_portfolio):
        """Test detailed market risk breakdown."""
        breakdown = calculator.get_detailed_breakdown(trading_portfolio)
        
        assert "by_risk_class" in breakdown
        assert "by_currency" in breakdown
        assert "by_desk" in breakdown
        assert "total_market_value" in breakdown
        assert "total_rwa" in breakdown
        
        # Risk class breakdown should have expected components
        risk_classes = breakdown["by_risk_class"]
        assert "girr" in risk_classes
        assert "csr_ns" in risk_classes
        assert "equity" in risk_classes
        assert "fx" in risk_classes
    
    def test_stressed_var(self, calculator, trading_portfolio):
        """Test stressed VaR calculation."""
        stress_scenario = {
            "interest_rate": 200,  # 200 bps shock
            "equity_shock": -0.2,  # -20% equity shock
            "fx_shock": 0.15       # 15% FX shock
        }
        
        stressed_var = calculator.calculate_stressed_var(
            trading_portfolio.get_trading_book_exposures(),
            stress_scenario
        )
        
        base_var = calculator.calculate_var_rwa(trading_portfolio.get_trading_book_exposures())
        
        # Stressed VaR should be higher than base VaR
        assert stressed_var > base_var


class TestOperationalRiskCalculator:
    """Test operational risk RWA calculations."""
    
    @pytest.fixture
    def config(self):
        """Basel configuration fixture."""
        return BaselConfig.load_default()
    
    @pytest.fixture
    def calculator(self, config):
        """Operational risk calculator fixture."""
        return OperationalRiskCalculator(config)
    
    @pytest.fixture
    def sample_portfolio(self):
        """Sample portfolio fixture."""
        portfolio = Portfolio(portfolio_id="test")
        
        # Add some exposures to estimate business indicator
        exposure = Exposure(
            exposure_id="op_test_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000000,  # €100M
            current_exposure=100000000
        )
        
        portfolio.add_exposure(exposure)
        return portfolio
    
    def test_sma_calculation_without_financial_data(self, calculator, sample_portfolio):
        """Test SMA calculation without financial data (estimated from portfolio)."""
        rwa = calculator.calculate_sma_rwa(sample_portfolio, None)
        
        assert rwa > 0
    
    def test_sma_calculation_with_financial_data(self, calculator, sample_portfolio):
        """Test SMA calculation with provided financial data."""
        financial_data = {
            "interest_income": 5000000,
            "interest_expense": 2000000,
            "dividend_income": 100000,
            "fee_income": 1000000,
            "fee_expense": 200000,
            "trading_income": 500000,
            "other_income": 300000,
            "other_expense": 100000
        }
        
        rwa = calculator.calculate_sma_rwa(sample_portfolio, financial_data)
        
        assert rwa > 0
    
    def test_business_indicator_calculation(self, calculator, sample_portfolio):
        """Test business indicator calculation."""
        financial_data = {
            "interest_income": 10000000,
            "interest_expense": 4000000,
            "dividend_income": 500000,
            "fee_income": 2000000,
            "fee_expense": 500000,
            "trading_income": 1000000,
            "other_income": 800000,
            "other_expense": 300000
        }
        
        bi = calculator.calculate_business_indicator(sample_portfolio, financial_data)
        
        # BI = ILDC + SCTB + FB
        # ILDC = interest_income + dividend_income = 10.5M
        # SCTB = max(0, fee_income - fee_expense) = 1.5M
        # FB = |trading_income| + |other_income - other_expense| = 1M + 0.5M = 1.5M
        # Total = 13.5M
        expected_bi = 10500000 + 1500000 + 1500000
        assert abs(bi - expected_bi) < 1000
    
    def test_bic_calculation(self, calculator, sample_portfolio):
        """Test Business Indicator Component calculation."""
        financial_data = {
            "business_indicator": 500000000  # €500M - Bucket 1
        }
        
        bic = calculator.calculate_business_indicator_component(sample_portfolio, financial_data)
        
        # For €500M BI, should be in Bucket 1 with 12% coefficient
        expected_bic = 500000000 * 0.12
        assert abs(bic - expected_bic) < 1000
        
        # Test Bucket 2
        financial_data["business_indicator"] = 5000000000  # €5B - Bucket 2
        bic = calculator.calculate_business_indicator_component(sample_portfolio, financial_data)
        
        # Bucket 1: €1B * 12% = €120M
        # Bucket 2: (€5B - €1B) * 15% = €600M
        # Total: €720M
        expected_bic = 1000000000 * 0.12 + 4000000000 * 0.15
        assert abs(bic - expected_bic) < 10000
    
    def test_ilm_calculation(self, calculator):
        """Test Internal Loss Multiplier calculation."""
        # Test with no loss data (should return 1.0)
        ilm = calculator.calculate_internal_loss_multiplier(None)
        assert ilm == 1.0
        
        # Test with low losses (should return 1.0)
        financial_data = {
            "historical_losses": 10000000,  # €10M - below threshold
            "business_indicator": 1000000000  # €1B
        }
        
        ilm = calculator.calculate_internal_loss_multiplier(financial_data)
        assert ilm == 1.0
        
        # Test with high losses (should return > 1.0)
        financial_data = {
            "historical_losses": 50000000,  # €50M - above threshold
            "business_indicator": 1000000000  # €1B
        }
        
        ilm = calculator.calculate_internal_loss_multiplier(financial_data)
        assert ilm > 1.0
        assert ilm <= 5.0  # ILM is capped at 5.0
    
    def test_basic_indicator_approach(self, calculator):
        """Test Basic Indicator Approach calculation."""
        financial_data = {
            "gross_income_year_1": 100000000,  # €100M
            "gross_income_year_2": 120000000,  # €120M
            "gross_income_year_3": 110000000   # €110M
        }
        
        rwa = calculator.calculate_basic_indicator_rwa(financial_data)
        
        # Average = €110M, capital = €110M * 15% = €16.5M, RWA = €16.5M * 12.5 = €206.25M
        expected_rwa = 110000000 * 0.15 * 12.5
        assert abs(rwa - expected_rwa) < 10000
    
    def test_detailed_breakdown(self, calculator, sample_portfolio):
        """Test detailed operational risk breakdown."""
        financial_data = {
            "interest_income": 10000000,
            "fee_income": 2000000,
            "trading_income": 1000000,
            "business_indicator": 13000000
        }
        
        breakdown = calculator.get_detailed_breakdown(sample_portfolio, financial_data)
        
        assert "business_indicator" in breakdown
        assert "bic_bucket" in breakdown
        assert "marginal_coefficient" in breakdown
        assert "business_indicator_component" in breakdown
        assert "internal_loss_multiplier" in breakdown
        assert "sma_capital_requirement" in breakdown
        assert "operational_rwa" in breakdown
        assert "bi_components" in breakdown
        assert "ilm_details" in breakdown
    
    def test_scenario_simulation(self, calculator, sample_portfolio):
        """Test business indicator scenario simulation."""
        scenario_adjustments = {
            "stress_scenario": -0.2,  # 20% decrease in BI
            "growth_scenario": 0.3    # 30% increase in BI
        }
        
        results = calculator.simulate_bi_scenarios(sample_portfolio, scenario_adjustments)
        
        assert "base_scenario" in results
        assert "scenarios" in results
        assert "stress_scenario" in results["scenarios"]
        assert "growth_scenario" in results["scenarios"]
        
        # Stress scenario should have lower RWA than base
        base_rwa = results["base_scenario"]["rwa"]
        stress_rwa = results["scenarios"]["stress_scenario"]["rwa"]
        growth_rwa = results["scenarios"]["growth_scenario"]["rwa"]
        
        assert stress_rwa < base_rwa
        assert growth_rwa > base_rwa


class TestRWAIntegration:
    """Integration tests for all RWA components."""
    
    @pytest.fixture
    def config(self):
        """Basel configuration fixture."""
        return BaselConfig.load_default()
    
    @pytest.fixture
    def comprehensive_portfolio(self):
        """Comprehensive portfolio with all risk types."""
        portfolio = Portfolio(portfolio_id="comprehensive")
        
        # Credit risk exposures
        corporate_loan = Exposure(
            exposure_id="corp_loan_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=5000000,
            current_exposure=4800000,
            probability_of_default=0.025,
            loss_given_default=0.45,
            maturity=4.0
        )
        
        retail_mortgage = Exposure(
            exposure_id="retail_mtg_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.RETAIL_MORTGAGE,
            original_exposure=2000000,
            current_exposure=1900000,
            probability_of_default=0.01,
            loss_given_default=0.25,
            maturity=20.0
        )
        
        # Market risk exposures
        trading_bond = Exposure(
            exposure_id="trading_bond_001",
            exposure_type=ExposureType.TRADING_SECURITIES,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=3000000,
            current_exposure=3000000,
            market_value=2950000,
            sensitivities={"ir_5y": 14750, "credit_spread": 5900}
        )
        
        fx_position = Exposure(
            exposure_id="fx_pos_001",
            exposure_type=ExposureType.TRADING_SECURITIES,
            exposure_class=ExposureClass.FX,
            original_exposure=1000000,
            current_exposure=1000000,
            market_value=1020000,
            currency="USD",
            sensitivities={"fx_delta": 10000}
        )
        
        # Off-balance sheet
        commitment = Exposure(
            exposure_id="commitment_001",
            exposure_type=ExposureType.COMMITMENTS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=2000000,
            current_exposure=2000000,
            credit_conversion_factor=0.75
        )
        
        portfolio.add_exposure(corporate_loan)
        portfolio.add_exposure(retail_mortgage)
        portfolio.add_exposure(trading_bond)
        portfolio.add_exposure(fx_position)
        portfolio.add_exposure(commitment)
        
        return portfolio
    
    def test_total_rwa_calculation(self, config, comprehensive_portfolio):
        """Test total RWA calculation across all risk types."""
        from src.basileia.core.engine import BaselEngine
        
        engine = BaselEngine(config)
        rwa_results = engine.calculate_rwa_only(comprehensive_portfolio)
        
        assert rwa_results["credit_rwa"] > 0
        assert rwa_results["market_rwa"] >= 0  # May be 0 if no trading book
        assert rwa_results["operational_rwa"] > 0
        assert rwa_results["total_rwa"] > 0
        
        # Total should equal sum of components
        total_calc = (rwa_results["credit_rwa"] + 
                     rwa_results["market_rwa"] + 
                     rwa_results["operational_rwa"])
        assert abs(rwa_results["total_rwa"] - total_calc) < 1e-6
    
    def test_rwa_consistency_across_approaches(self, config):
        """Test that different approaches produce reasonable results."""
        credit_calc = CreditRiskCalculator(config)
        market_calc = MarketRiskCalculator(config)
        
        # Create simple portfolio
        portfolio = Portfolio(portfolio_id="test")
        exposure = Exposure(
            exposure_id="test_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=1000000,
            current_exposure=1000000,
            probability_of_default=0.02,
            loss_given_default=0.45,
            maturity=3.0
        )
        portfolio.add_exposure(exposure)
        
        # Test different credit approaches
        sa_rwa = credit_calc.calculate_standardized_rwa(portfolio)
        irb_rwa = credit_calc.calculate_irb_rwa(portfolio, CreditApproach.IRB_ADVANCED)
        
        assert sa_rwa > 0
        assert irb_rwa > 0
        
        # IRB and SA should be in reasonable range of each other
        ratio = max(sa_rwa, irb_rwa) / min(sa_rwa, irb_rwa)
        assert ratio < 5.0  # Should not differ by more than 5x
    
    def test_rwa_scalability(self, config):
        """Test RWA calculations scale appropriately."""
        credit_calc = CreditRiskCalculator(config)
        
        # Create base exposure
        base_exposure = Exposure(
            exposure_id="base_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=1000000,
            current_exposure=1000000
        )
        
        portfolio1 = Portfolio(portfolio_id="p1")
        portfolio1.add_exposure(base_exposure)
        
        # Create portfolio with doubled exposure
        double_exposure = base_exposure.model_copy()
        double_exposure.current_exposure = 2000000
        double_exposure.exposure_id = "double_001"
        
        portfolio2 = Portfolio(portfolio_id="p2")
        portfolio2.add_exposure(double_exposure)
        
        rwa1 = credit_calc.calculate_standardized_rwa(portfolio1)
        rwa2 = credit_calc.calculate_standardized_rwa(portfolio2)
        
        # RWA should scale linearly with exposure amount (for SA)
        assert abs(rwa2 / rwa1 - 2.0) < 0.01
