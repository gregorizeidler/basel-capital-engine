"""Pydantic models for Basel Capital Engine API."""

from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum


class ExposureData(BaseModel):
    """Exposure data for API requests."""
    
    exposure_id: str
    counterparty_id: Optional[str] = None
    exposure_type: str
    exposure_class: str
    original_exposure: float = Field(gt=0)
    current_exposure: float = Field(gt=0)
    
    # Credit risk parameters
    probability_of_default: Optional[float] = Field(None, ge=0, le=1)
    loss_given_default: Optional[float] = Field(None, ge=0, le=1)
    maturity: Optional[float] = Field(None, gt=0)
    
    # Rating and classification
    external_rating: Optional[str] = None
    internal_rating: Optional[str] = None
    
    # Off-balance sheet specific
    credit_conversion_factor: Optional[float] = Field(None, ge=0, le=1)
    
    # Market risk specific
    market_value: Optional[float] = None
    sensitivities: Optional[Dict[str, float]] = None
    
    # Credit risk mitigation
    collateral_type: Optional[str] = None
    collateral_value: Optional[float] = None
    guarantee_provider: Optional[str] = None
    guarantee_amount: Optional[float] = None
    
    # Additional metadata
    currency: str = "EUR"
    business_line: Optional[str] = None
    geography: Optional[str] = None
    sector: Optional[str] = None


class PortfolioData(BaseModel):
    """Portfolio data for API requests."""
    
    portfolio_id: str
    bank_name: Optional[str] = None
    reporting_date: Optional[str] = None
    exposures: List[ExposureData]
    
    @validator('exposures')
    def validate_exposures(cls, v):
        if not v:
            raise ValueError("Portfolio must contain at least one exposure")
        return v


class CapitalData(BaseModel):
    """Capital structure data for API requests."""
    
    bank_name: Optional[str] = None
    reporting_date: Optional[str] = None
    base_currency: str = "EUR"
    
    # Capital components
    common_shares: float = Field(default=0, ge=0)
    retained_earnings: float = 0  # Can be negative
    accumulated_oci: float = 0    # Can be negative
    minority_interests: float = Field(default=0, ge=0)
    
    # Additional Tier 1
    at1_instruments: float = Field(default=0, ge=0)
    
    # Tier 2
    t2_instruments: float = Field(default=0, ge=0)
    general_provisions: float = Field(default=0, ge=0)
    
    # Regulatory adjustments and deductions
    goodwill: float = Field(default=0, ge=0)
    intangible_assets: float = Field(default=0, ge=0)
    deferred_tax_assets: float = Field(default=0, ge=0)
    cash_flow_hedge_reserve: float = 0
    shortfall_provisions: float = Field(default=0, ge=0)
    securitization_exposures: float = Field(default=0, ge=0)
    investments_in_own_shares: float = Field(default=0, ge=0)
    reciprocal_cross_holdings: float = Field(default=0, ge=0)
    investments_in_financial_institutions: float = Field(default=0, ge=0)
    mortgage_servicing_rights: float = Field(default=0, ge=0)
    
    # Threshold deductions
    significant_investments_threshold: float = Field(default=0, ge=0)
    dta_threshold: float = Field(default=0, ge=0)
    mortgage_servicing_threshold: float = Field(default=0, ge=0)


class BufferData(BaseModel):
    """Regulatory buffer data for API requests."""
    
    conservation_buffer: float = Field(default=0.025, ge=0, le=0.1)
    countercyclical_buffer: float = Field(default=0.0, ge=0, le=0.025)
    gsib_buffer: float = Field(default=0.0, ge=0, le=0.035)
    dsib_buffer: float = Field(default=0.0, ge=0, le=0.02)
    systemic_risk_buffer: float = Field(default=0.0, ge=0, le=0.05)
    
    jurisdiction: Optional[str] = None
    effective_date: Optional[str] = None
    gsib_bucket: Optional[int] = Field(None, ge=1, le=5)


class OperationalRiskData(BaseModel):
    """Operational risk data for API requests."""
    
    # Financial data for Business Indicator calculation
    interest_income: Optional[float] = None
    interest_expense: Optional[float] = None
    dividend_income: Optional[float] = None
    fee_income: Optional[float] = None
    fee_expense: Optional[float] = None
    trading_income: Optional[float] = None
    other_income: Optional[float] = None
    other_expense: Optional[float] = None
    
    # Historical loss data for ILM
    historical_losses: Optional[float] = None
    
    # Gross income for Basic Indicator Approach
    gross_income_year_1: Optional[float] = None
    gross_income_year_2: Optional[float] = None
    gross_income_year_3: Optional[float] = None


# Request models
class PortfolioRequest(BaseModel):
    """Request model for portfolio calculations."""
    
    portfolio: PortfolioData
    capital: CapitalData
    buffers: Optional[BufferData] = None
    operational_risk_data: Optional[OperationalRiskData] = None
    config_overrides: Optional[Dict[str, Any]] = None


class StressTestRequest(BaseModel):
    """Request model for stress testing."""
    
    portfolio: PortfolioData
    capital: CapitalData
    scenarios: List[str] = Field(default=["adverse"])
    custom_scenarios: Optional[Dict[str, Dict[str, float]]] = None
    buffers: Optional[BufferData] = None
    operational_risk_data: Optional[OperationalRiskData] = None
    config_overrides: Optional[Dict[str, Any]] = None
    
    @validator('scenarios')
    def validate_scenarios(cls, v):
        valid_scenarios = ["baseline", "adverse", "severely_adverse"]
        for scenario in v:
            if scenario not in valid_scenarios and not scenario.startswith("custom_"):
                raise ValueError(f"Invalid scenario: {scenario}. Valid options: {valid_scenarios} or custom_*")
        return v


# Response models
class CapitalRatiosResponse(BaseModel):
    """Capital ratios in response."""
    
    cet1_ratio: float
    tier1_ratio: float
    total_capital_ratio: float
    leverage_ratio: float
    
    # Excess/shortfall
    cet1_excess_bps: float
    tier1_excess_bps: float
    total_excess_bps: float
    leverage_excess_bps: float


class RWABreakdownResponse(BaseModel):
    """RWA breakdown in response."""
    
    credit_rwa: float
    market_rwa: float
    operational_rwa: float
    total_rwa: float
    
    # Detailed breakdowns
    credit_breakdown: Dict[str, Any]
    market_breakdown: Dict[str, Any]
    operational_breakdown: Dict[str, Any]


class BufferAnalysisResponse(BaseModel):
    """Buffer analysis in response."""
    
    buffer_requirements: Dict[str, float]
    buffer_breaches: List[Dict[str, Any]]
    mda_restrictions: Dict[str, Any]
    capital_shortfall: float


class BaselResultsResponse(BaseModel):
    """Complete Basel calculation results."""
    
    calculation_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Capital amounts
    cet1_capital: float
    tier1_capital: float
    total_capital: float
    
    # Capital ratios
    ratios: CapitalRatiosResponse
    
    # RWA breakdown
    rwa: RWABreakdownResponse
    
    # Buffer analysis
    buffers: BufferAnalysisResponse
    
    # Compliance
    meets_minimum_requirements: bool
    
    # Metadata
    bank_name: Optional[str] = None
    portfolio_summary: Dict[str, Any]


class StressTestResultResponse(BaseModel):
    """Single stress test result."""
    
    scenario_name: str
    scenario_description: str
    
    # Results
    baseline_ratios: CapitalRatiosResponse
    stressed_ratios: CapitalRatiosResponse
    
    # Impacts
    capital_impact: Dict[str, float]
    rwa_impact: Dict[str, float]
    ratio_impact: Dict[str, float]
    
    # Analysis
    buffer_breaches: List[str]
    capital_shortfall: float
    passes_minimum: bool


class StressTestResponse(BaseModel):
    """Complete stress test results."""
    
    test_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Results by scenario
    results: Dict[str, StressTestResultResponse]
    
    # Comparison analysis
    worst_case_cet1: float
    worst_case_scenario: str
    max_capital_shortfall: float
    
    # Summary
    scenarios_tested: int
    scenarios_with_breaches: int
    overall_assessment: str  # "PASS" or "FAIL"


class ExplainResponse(BaseModel):
    """Detailed explanation of calculations."""
    
    calculation_id: str
    calculation_type: str  # "portfolio" or "stress_test"
    timestamp: datetime
    
    explanation: Dict[str, Any]


class CompareResponse(BaseModel):
    """Portfolio comparison results."""
    
    comparison_id: str
    timestamp: datetime
    
    portfolios: List[Dict[str, Any]]
    comparison_analysis: Dict[str, Any]


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str  # "healthy" or "unhealthy"
    timestamp: datetime
    checks: Dict[str, Any]


class ValidationResponse(BaseModel):
    """Portfolio validation response."""
    
    valid: bool
    issues: List[str]
    warnings: List[str]
    summary: Dict[str, Any]


# Utility models for complex nested data
class ExposureImpact(BaseModel):
    """Impact on individual exposure."""
    
    exposure_id: str
    exposure_class: str
    baseline_exposure: float
    stressed_exposure: float
    impact_amount: float
    impact_percentage: float


class WaterfallComponent(BaseModel):
    """Component of waterfall analysis."""
    
    component_name: str
    baseline_value: float
    stressed_value: float
    change_value: float
    change_percentage: float


class ConcentrationMetrics(BaseModel):
    """Portfolio concentration metrics."""
    
    total_exposure: float
    num_exposures: int
    largest_counterparty_pct: float
    largest_sector_pct: float
    hhi_counterparty: float
    hhi_sector: float


class RiskWeightAnalysis(BaseModel):
    """Risk weight analysis."""
    
    average_risk_weight: float
    risk_weight_distribution: Dict[str, float]
    concentration_by_rating: Dict[str, float]
    geographic_distribution: Dict[str, float]
