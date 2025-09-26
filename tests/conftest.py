"""Pytest configuration and shared fixtures."""

import pytest
import tempfile
import os
from pathlib import Path

from src.basileia.core.config import BaselConfig
from src.basileia.core.exposure import Portfolio, Exposure, ExposureType, ExposureClass
from src.basileia.core.capital import Capital, CapitalComponents
from src.basileia.simulator.portfolio import PortfolioGenerator, BankSize


@pytest.fixture(scope="session")
def test_config():
    """Test configuration fixture."""
    return BaselConfig.load_default()


@pytest.fixture
def temp_dir():
    """Temporary directory fixture."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def simple_exposure():
    """Simple exposure fixture."""
    return Exposure(
        exposure_id="simple_001",
        exposure_type=ExposureType.LOANS,
        exposure_class=ExposureClass.CORPORATE,
        original_exposure=1000000,
        current_exposure=950000,
        probability_of_default=0.02,
        loss_given_default=0.45,
        maturity=3.0,
        external_rating="BBB"
    )


@pytest.fixture
def simple_portfolio(simple_exposure):
    """Simple portfolio fixture."""
    portfolio = Portfolio(
        portfolio_id="simple_portfolio",
        bank_name="Test Bank"
    )
    portfolio.add_exposure(simple_exposure)
    return portfolio


@pytest.fixture
def simple_capital():
    """Simple capital structure fixture."""
    components = CapitalComponents(
        common_shares=1000000,
        retained_earnings=500000,
        accumulated_oci=25000,
        at1_instruments=200000,
        t2_instruments=300000,
        goodwill=50000,
        intangible_assets=25000
    )
    
    return Capital(
        bank_name="Test Bank",
        components=components
    )


@pytest.fixture
def medium_bank_portfolio():
    """Medium bank portfolio fixture using generator."""
    generator = PortfolioGenerator(seed=42)
    portfolio, capital = generator.generate_bank_portfolio(BankSize.MEDIUM, "Test Medium Bank")
    return portfolio, capital


@pytest.fixture
def large_bank_portfolio():
    """Large bank portfolio fixture using generator."""
    generator = PortfolioGenerator(seed=123)
    portfolio, capital = generator.generate_bank_portfolio(BankSize.LARGE, "Test Large Bank")
    return portfolio, capital


@pytest.fixture
def diversified_portfolio():
    """Diversified portfolio with multiple asset classes."""
    portfolio = Portfolio(portfolio_id="diversified", bank_name="Diversified Bank")
    
    # Sovereign exposure
    sovereign = Exposure(
        exposure_id="sovereign_001",
        exposure_type=ExposureType.SECURITIES,
        exposure_class=ExposureClass.SOVEREIGN,
        original_exposure=2000000,
        current_exposure=2000000,
        external_rating="AAA"
    )
    
    # Corporate loan
    corporate = Exposure(
        exposure_id="corporate_001",
        exposure_type=ExposureType.LOANS,
        exposure_class=ExposureClass.CORPORATE,
        original_exposure=3000000,
        current_exposure=2800000,
        probability_of_default=0.025,
        loss_given_default=0.45,
        maturity=4.0,
        external_rating="A"
    )
    
    # Retail mortgage
    retail = Exposure(
        exposure_id="retail_001",
        exposure_type=ExposureType.LOANS,
        exposure_class=ExposureClass.RETAIL_MORTGAGE,
        original_exposure=1500000,
        current_exposure=1400000,
        probability_of_default=0.008,
        loss_given_default=0.25,
        maturity=25.0
    )
    
    # Trading security
    trading = Exposure(
        exposure_id="trading_001",
        exposure_type=ExposureType.TRADING_SECURITIES,
        exposure_class=ExposureClass.CORPORATE,
        original_exposure=1000000,
        current_exposure=1000000,
        market_value=985000,
        sensitivities={"ir_5y": 4925, "credit_spread": 1970}
    )
    
    # Commitment
    commitment = Exposure(
        exposure_id="commitment_001",
        exposure_type=ExposureType.COMMITMENTS,
        exposure_class=ExposureClass.CORPORATE,
        original_exposure=500000,
        current_exposure=500000,
        credit_conversion_factor=0.75
    )
    
    portfolio.add_exposure(sovereign)
    portfolio.add_exposure(corporate)
    portfolio.add_exposure(retail)
    portfolio.add_exposure(trading)
    portfolio.add_exposure(commitment)
    
    return portfolio


@pytest.fixture
def stress_test_data():
    """Stress test scenario data."""
    return {
        "baseline": {},
        "adverse": {
            "interest_rate": 300,  # +300 bps
            "fx_usd_brl": 0.25,   # 25% depreciation
            "credit_pd_multiplier": 1.4,  # 40% increase in PDs
            "equity_shock": -0.3,  # -30% equity decline
            "real_estate_shock": -0.2  # -20% property decline
        },
        "severely_adverse": {
            "interest_rate": 500,  # +500 bps
            "fx_usd_brl": 0.4,    # 40% depreciation
            "credit_pd_multiplier": 2.0,  # 100% increase in PDs
            "equity_shock": -0.5,  # -50% equity decline
            "real_estate_shock": -0.35  # -35% property decline
        }
    }


@pytest.fixture
def operational_risk_data():
    """Operational risk financial data."""
    return {
        "interest_income": 15000000,
        "interest_expense": 6000000,
        "dividend_income": 500000,
        "fee_income": 3000000,
        "fee_expense": 800000,
        "trading_income": 2000000,
        "other_income": 1200000,
        "other_expense": 400000,
        "historical_losses": 25000000,
        "gross_income_year_1": 18000000,
        "gross_income_year_2": 19500000,
        "gross_income_year_3": 17800000
    }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "property: marks tests as property-based tests"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Mark property-based tests
        if "test_properties" in item.nodeid:
            item.add_marker(pytest.mark.property)
        
        # Mark integration tests
        if "integration" in item.nodeid or "test_engine" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        
        # Mark slow tests
        if any(marker in item.nodeid for marker in ["stress", "large", "comprehensive"]):
            item.add_marker(pytest.mark.slow)


# Custom assertion helpers
def assert_capital_hierarchy(capital):
    """Assert that capital hierarchy is maintained."""
    cet1 = capital.calculate_cet1_capital()
    tier1 = capital.calculate_tier1_capital()
    total = capital.calculate_total_capital()
    
    assert cet1 <= tier1 + 1e-6, f"CET1 ({cet1}) should not exceed Tier 1 ({tier1})"
    assert tier1 <= total + 1e-6, f"Tier 1 ({tier1}) should not exceed Total ({total})"


def assert_rwa_non_negative(rwa_dict):
    """Assert that all RWA components are non-negative."""
    for component, value in rwa_dict.items():
        assert value >= 0, f"RWA component {component} should be non-negative, got {value}"


def assert_ratio_bounds(ratio_dict):
    """Assert that ratios are within reasonable bounds."""
    for ratio_name, ratio_value in ratio_dict.items():
        if "ratio" in ratio_name.lower():
            assert 0 <= ratio_value <= 1.0, f"Ratio {ratio_name} should be between 0 and 100%, got {ratio_value:.2%}"


# Parametrize helpers
BANK_SIZES = [BankSize.SMALL, BankSize.MEDIUM, BankSize.LARGE]
EXPOSURE_CLASSES = [ExposureClass.SOVEREIGN, ExposureClass.CORPORATE, ExposureClass.RETAIL_MORTGAGE]
RATINGS = ["AAA", "AA", "A", "BBB", "BB", "B", "unrated"]
