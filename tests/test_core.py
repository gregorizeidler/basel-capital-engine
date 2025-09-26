"""Tests for core Basel Capital Engine components."""

import pytest
from decimal import Decimal
from datetime import datetime

from src.basileia.core.exposure import (
    Exposure, ExposureType, ExposureClass, Portfolio, CreditRiskMitigation
)
from src.basileia.core.capital import (
    Capital, CapitalComponents, CapitalInstrument, CapitalTier
)
from src.basileia.core.buffers import RegulatoryBuffers, BufferType
from src.basileia.core.config import BaselConfig
from src.basileia.core.engine import BaselEngine


class TestExposure:
    """Test exposure models and calculations."""
    
    def test_exposure_creation(self):
        """Test basic exposure creation."""
        exposure = Exposure(
            exposure_id="test_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.RETAIL_OTHER,
            original_exposure=100000,
            current_exposure=95000,
            probability_of_default=0.02,
            loss_given_default=0.45,
            maturity=3.0
        )
        
        assert exposure.exposure_id == "test_001"
        assert exposure.current_exposure == 95000
        assert exposure.probability_of_default == 0.02
        assert exposure.loss_given_default == 0.45
        assert exposure.maturity == 3.0
    
    def test_exposure_at_default(self):
        """Test EAD calculation."""
        # On-balance sheet exposure
        exposure1 = Exposure(
            exposure_id="test_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=95000
        )
        
        assert exposure1.get_exposure_at_default() == 95000
        
        # Off-balance sheet exposure
        exposure2 = Exposure(
            exposure_id="test_002",
            exposure_type=ExposureType.COMMITMENTS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000,
            credit_conversion_factor=0.75
        )
        
        assert exposure2.get_exposure_at_default() == 75000
    
    def test_effective_maturity(self):
        """Test effective maturity calculation with floors and caps."""
        # Test floor
        exposure1 = Exposure(
            exposure_id="test_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000,
            maturity=0.5  # 6 months
        )
        
        assert exposure1.get_effective_maturity() == 1.0  # Floor at 1 year
        
        # Test cap
        exposure2 = Exposure(
            exposure_id="test_002",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000,
            maturity=10.0  # 10 years
        )
        
        assert exposure2.get_effective_maturity() == 5.0  # Cap at 5 years
        
        # Test normal case
        exposure3 = Exposure(
            exposure_id="test_003",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000,
            maturity=3.0
        )
        
        assert exposure3.get_effective_maturity() == 3.0
    
    def test_credit_risk_mitigation(self):
        """Test credit risk mitigation calculation."""
        config = BaselConfig.load_default()
        
        # Create exposure with collateral
        crm = CreditRiskMitigation(
            collateral_type="residential_property",
            collateral_value=120000
        )
        
        exposure = Exposure(
            exposure_id="test_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.RETAIL_MORTGAGE,
            original_exposure=100000,
            current_exposure=100000,
            crm=crm
        )
        
        # Test that CRM reduces effective exposure
        mitigated_exposure = exposure.apply_credit_risk_mitigation(config)
        assert mitigated_exposure < exposure.get_exposure_at_default()
    
    def test_retail_classification(self):
        """Test retail exposure classification."""
        retail_exposure = Exposure(
            exposure_id="test_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.RETAIL_MORTGAGE,
            original_exposure=100000,
            current_exposure=100000
        )
        
        corporate_exposure = Exposure(
            exposure_id="test_002",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000
        )
        
        assert retail_exposure.is_retail() is True
        assert corporate_exposure.is_retail() is False
    
    def test_trading_book_classification(self):
        """Test trading book classification."""
        trading_exposure = Exposure(
            exposure_id="test_001",
            exposure_type=ExposureType.TRADING_SECURITIES,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000
        )
        
        banking_exposure = Exposure(
            exposure_id="test_002",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000
        )
        
        assert trading_exposure.is_trading_book() is True
        assert banking_exposure.is_trading_book() is False


class TestPortfolio:
    """Test portfolio models and calculations."""
    
    def test_portfolio_creation(self):
        """Test portfolio creation and exposure management."""
        portfolio = Portfolio(
            portfolio_id="test_portfolio",
            bank_name="Test Bank"
        )
        
        exposure = Exposure(
            exposure_id="test_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.RETAIL_OTHER,
            original_exposure=100000,
            current_exposure=95000
        )
        
        portfolio.add_exposure(exposure)
        
        assert len(portfolio.exposures) == 1
        assert portfolio.get_total_exposure() == 95000
    
    def test_exposure_filtering(self):
        """Test exposure filtering by type and class."""
        portfolio = Portfolio(portfolio_id="test")
        
        # Add different types of exposures
        loan_exposure = Exposure(
            exposure_id="loan_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000
        )
        
        trading_exposure = Exposure(
            exposure_id="trading_001",
            exposure_type=ExposureType.TRADING_SECURITIES,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=50000,
            current_exposure=50000
        )
        
        portfolio.add_exposure(loan_exposure)
        portfolio.add_exposure(trading_exposure)
        
        # Test filtering
        corporate_exposures = portfolio.get_exposures_by_class(ExposureClass.CORPORATE)
        loan_exposures = portfolio.get_exposures_by_type(ExposureType.LOANS)
        trading_exposures = portfolio.get_trading_book_exposures()
        banking_exposures = portfolio.get_banking_book_exposures()
        
        assert len(corporate_exposures) == 2
        assert len(loan_exposures) == 1
        assert len(trading_exposures) == 1
        assert len(banking_exposures) == 1
    
    def test_concentration_metrics(self):
        """Test portfolio concentration calculations."""
        portfolio = Portfolio(portfolio_id="test")
        
        # Add exposures with different counterparties and sectors
        for i in range(5):
            exposure = Exposure(
                exposure_id=f"exp_{i}",
                counterparty_id=f"counterparty_{i % 3}",  # 3 counterparties
                exposure_type=ExposureType.LOANS,
                exposure_class=ExposureClass.CORPORATE,
                original_exposure=100000,
                current_exposure=100000,
                sector=f"sector_{i % 2}"  # 2 sectors
            )
            portfolio.add_exposure(exposure)
        
        metrics = portfolio.get_concentration_metrics()
        
        assert metrics["total_exposure"] == 500000
        assert metrics["num_exposures"] == 5
        assert "largest_counterparty_pct" in metrics
        assert "largest_sector_pct" in metrics
        assert "counterparty_hhi" in metrics
        assert "sector_hhi" in metrics


class TestCapital:
    """Test capital models and calculations."""
    
    def test_capital_components(self):
        """Test capital component calculations."""
        components = CapitalComponents(
            common_shares=1000000,
            retained_earnings=500000,
            accumulated_oci=50000,
            minority_interests=25000,
            at1_instruments=200000,
            t2_instruments=300000,
            goodwill=100000,
            intangible_assets=50000
        )
        
        # Test CET1 calculation
        cet1_before = components.calculate_cet1_before_adjustments()
        assert cet1_before == 1575000  # 1M + 500K + 50K + 25K
        
        cet1_adjustments = components.calculate_cet1_adjustments()
        assert cet1_adjustments == 150000  # 100K + 50K
        
        cet1 = components.calculate_cet1()
        assert cet1 == 1425000  # 1575K - 150K
        
        # Test Tier 1 calculation
        tier1 = components.calculate_tier1()
        assert tier1 == 1625000  # 1425K + 200K
        
        # Test Total Capital calculation
        total_capital = components.calculate_total_capital()
        # T2 is limited to 100% of Tier 1, so 300K T2 is fully eligible
        assert total_capital == 1925000  # 1625K + 300K
    
    def test_capital_structure(self):
        """Test complete capital structure."""
        components = CapitalComponents(
            common_shares=1000000,
            retained_earnings=500000,
            at1_instruments=200000,
            t2_instruments=300000,
            goodwill=50000
        )
        
        capital = Capital(
            bank_name="Test Bank",
            components=components
        )
        
        # Test calculations
        cet1 = capital.calculate_cet1_capital()
        tier1 = capital.calculate_tier1_capital()
        total = capital.calculate_total_capital()
        
        assert cet1 > 0
        assert tier1 >= cet1
        assert total >= tier1
        
        # Test summary
        summary = capital.get_capital_summary()
        assert "cet1_capital" in summary
        assert "tier1_capital" in summary
        assert "total_capital" in summary
    
    def test_capital_validation(self):
        """Test capital structure validation."""
        # Valid capital structure
        valid_components = CapitalComponents(
            common_shares=1000000,
            retained_earnings=500000,
            at1_instruments=200000,
            t2_instruments=300000
        )
        
        valid_capital = Capital(components=valid_components)
        issues = valid_capital.validate_capital_structure()
        
        assert len(issues) == 0
        
        # Invalid capital structure (negative CET1)
        invalid_components = CapitalComponents(
            common_shares=100000,
            retained_earnings=-200000,  # Large negative RE
            goodwill=500000  # Excessive goodwill
        )
        
        invalid_capital = Capital(components=invalid_components)
        issues = invalid_capital.validate_capital_structure()
        
        assert len(issues) > 0


class TestRegulatoryBuffers:
    """Test regulatory buffer calculations."""
    
    def test_buffer_requirements(self):
        """Test buffer requirement calculations."""
        buffers = RegulatoryBuffers(
            conservation_buffer=0.025,  # 2.5%
            countercyclical_buffer=0.01,  # 1.0%
            gsib_buffer=0.015  # 1.5%
        )
        
        total_requirement = buffers.get_total_buffer_requirement()
        assert total_requirement == 0.05  # 5.0%
        
        breakdown = buffers.get_buffer_breakdown()
        assert breakdown["conservation"] == 0.025
        assert breakdown["countercyclical"] == 0.01
        assert breakdown["gsib"] == 0.015
        assert breakdown["total"] == 0.05
    
    def test_gsib_bucket_setting(self):
        """Test G-SIB bucket buffer setting."""
        buffers = RegulatoryBuffers()
        
        # Test different buckets
        buffers.set_gsib_buffer_from_bucket(1)
        assert buffers.gsib_buffer == 0.01
        assert buffers.gsib_bucket == 1
        
        buffers.set_gsib_buffer_from_bucket(5)
        assert buffers.gsib_buffer == 0.035
        assert buffers.gsib_bucket == 5
    
    def test_buffer_breaches(self):
        """Test buffer breach detection."""
        buffers = RegulatoryBuffers(
            conservation_buffer=0.025,
            countercyclical_buffer=0.01
        )
        
        # Test with ratios below requirements
        breaches = buffers.check_buffer_breaches(
            cet1_ratio=0.06,  # 6% - below 4.5% + 3.5% buffers
            tier1_ratio=0.07,
            total_capital_ratio=0.09,
            total_rwa=1000000
        )
        
        assert len(breaches) > 0
        
        # Test with ratios above requirements
        breaches = buffers.check_buffer_breaches(
            cet1_ratio=0.12,  # 12% - well above requirements
            tier1_ratio=0.13,
            total_capital_ratio=0.15,
            total_rwa=1000000
        )
        
        assert len(breaches) == 0
    
    def test_mda_restrictions(self):
        """Test Maximum Distributable Amount calculations."""
        buffers = RegulatoryBuffers(conservation_buffer=0.025)
        
        # Create a breach
        breaches = buffers.check_buffer_breaches(
            cet1_ratio=0.06,  # 6% - breach conservation buffer
            tier1_ratio=0.07,
            total_capital_ratio=0.09,
            total_rwa=1000000
        )
        
        mda_restrictions = buffers.get_mda_restrictions(breaches)
        
        assert mda_restrictions["applicable"] is True
        assert mda_restrictions["restriction_pct"] > 0


class TestBaselConfig:
    """Test Basel configuration management."""
    
    def test_config_loading(self):
        """Test configuration loading."""
        config = BaselConfig.load_default()
        
        assert config is not None
        assert "risk_weights" in config.model_dump()
        assert "buffers" in config.model_dump()
        assert "minimum_ratios" in config.model_dump()
    
    def test_risk_weight_lookup(self):
        """Test risk weight lookup functionality."""
        config = BaselConfig.load_default()
        
        # Test sovereign risk weight
        sovereign_weight = config.get_risk_weight("sovereign", "aaa")
        assert sovereign_weight >= 0
        
        # Test corporate risk weight
        corporate_weight = config.get_risk_weight("corporate", "bbb")
        assert corporate_weight >= 0
        
        # Test fallback
        unknown_weight = config.get_risk_weight("unknown_class", "unknown_rating")
        assert unknown_weight > 0  # Should fall back to other_assets
    
    def test_buffer_requirements(self):
        """Test buffer requirement lookup."""
        config = BaselConfig.load_default()
        
        conservation = config.get_buffer_requirement("conservation")
        assert conservation == 0.025
        
        sifi = config.get_buffer_requirement("sifi", bucket="g_sib_bucket_1")
        assert sifi > 0
    
    def test_minimum_ratios(self):
        """Test minimum ratio lookup."""
        config = BaselConfig.load_default()
        
        cet1_min = config.get_minimum_ratio("cet1_minimum")
        assert cet1_min == 0.045
        
        tier1_min = config.get_minimum_ratio("tier1_minimum")
        assert tier1_min == 0.06
        
        total_min = config.get_minimum_ratio("total_capital_minimum")
        assert total_min == 0.08
    
    def test_data_validation(self):
        """Test exposure data validation."""
        config = BaselConfig.load_default()
        
        # Valid data
        assert config.validate_exposure_data(
            exposure_amount=1000000,
            pd=0.02,
            lgd=0.45,
            maturity=3.0
        ) is True
        
        # Invalid PD
        assert config.validate_exposure_data(
            exposure_amount=1000000,
            pd=1.5,  # Invalid - > 100%
            lgd=0.45,
            maturity=3.0
        ) is False
        
        # Invalid LGD
        assert config.validate_exposure_data(
            exposure_amount=1000000,
            pd=0.02,
            lgd=1.5,  # Invalid - > 100%
            maturity=3.0
        ) is False


class TestBaselEngine:
    """Test main Basel engine integration."""
    
    def test_engine_initialization(self):
        """Test engine initialization."""
        engine = BaselEngine()
        assert engine is not None
        assert engine.config is not None
        assert engine.credit_calculator is not None
        assert engine.market_calculator is not None
        assert engine.operational_calculator is not None
    
    def test_input_validation(self):
        """Test input validation."""
        engine = BaselEngine()
        
        # Create minimal valid portfolio and capital
        portfolio = Portfolio(portfolio_id="test")
        exposure = Exposure(
            exposure_id="test_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000
        )
        portfolio.add_exposure(exposure)
        
        capital = Capital(
            components=CapitalComponents(
                common_shares=100000,
                retained_earnings=50000
            )
        )
        
        # Test validation
        issues = engine.validate_inputs(portfolio, capital)
        assert isinstance(issues, list)
    
    def test_rwa_calculation(self):
        """Test RWA-only calculation."""
        engine = BaselEngine()
        
        portfolio = Portfolio(portfolio_id="test")
        exposure = Exposure(
            exposure_id="test_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000
        )
        portfolio.add_exposure(exposure)
        
        rwa_results = engine.calculate_rwa_only(portfolio)
        
        assert "credit_rwa" in rwa_results
        assert "market_rwa" in rwa_results
        assert "operational_rwa" in rwa_results
        assert "total_rwa" in rwa_results
        assert rwa_results["total_rwa"] > 0
    
    def test_diagnostics(self):
        """Test diagnostic functionality."""
        engine = BaselEngine()
        
        # Create test data
        portfolio = Portfolio(portfolio_id="test")
        exposure = Exposure(
            exposure_id="test_001",
            exposure_type=ExposureType.LOANS,
            exposure_class=ExposureClass.CORPORATE,
            original_exposure=100000,
            current_exposure=100000
        )
        portfolio.add_exposure(exposure)
        
        capital = Capital(
            components=CapitalComponents(
                common_shares=100000,
                retained_earnings=50000
            )
        )
        
        diagnostics = engine.run_diagnostics(portfolio, capital)
        
        assert "input_validation" in diagnostics
        assert "portfolio_stats" in diagnostics
        assert "capital_stats" in diagnostics
        assert "config_summary" in diagnostics
