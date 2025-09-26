"""Stress testing scenarios for Basel Capital Engine."""

from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from pydantic import BaseModel, Field
import math


class ScenarioType(str, Enum):
    """Types of stress scenarios."""
    
    BASELINE = "baseline"
    ADVERSE = "adverse"
    SEVERELY_ADVERSE = "severely_adverse"
    CUSTOM = "custom"


class RiskFactor(str, Enum):
    """Risk factors for stress scenarios."""
    
    INTEREST_RATES = "interest_rates"
    FX_RATES = "fx_rates"
    EQUITY_PRICES = "equity_prices"
    CREDIT_SPREADS = "credit_spreads"
    REAL_ESTATE_PRICES = "real_estate_prices"
    GDP_GROWTH = "gdp_growth"
    UNEMPLOYMENT = "unemployment"
    INFLATION = "inflation"
    DEFAULT_RATES = "default_rates"
    RECOVERY_RATES = "recovery_rates"
    VOLATILITY = "volatility"


class StressShock(BaseModel):
    """Individual stress shock definition."""
    
    risk_factor: RiskFactor
    shock_value: float = Field(description="Shock magnitude (e.g., -0.3 for -30%)")
    shock_type: str = Field(default="relative", description="relative, absolute, or multiplier")
    currency: Optional[str] = None
    sector: Optional[str] = None
    geography: Optional[str] = None
    time_horizon: int = Field(default=1, description="Time horizon in years")
    
    def apply_shock(self, base_value: float) -> float:
        """Apply shock to base value."""
        if self.shock_type == "relative":
            return base_value * (1 + self.shock_value)
        elif self.shock_type == "absolute":
            return base_value + self.shock_value
        elif self.shock_type == "multiplier":
            return base_value * self.shock_value
        else:
            raise ValueError(f"Unknown shock type: {self.shock_type}")


class MacroScenario(BaseModel):
    """Macroeconomic stress scenario."""
    
    scenario_id: str
    scenario_name: str
    scenario_type: ScenarioType
    description: str
    time_horizon: int = Field(default=3, description="Scenario horizon in years")
    
    # Macroeconomic variables
    gdp_growth: Optional[float] = None  # Annual GDP growth rate
    unemployment_rate: Optional[float] = None  # Unemployment rate
    inflation_rate: Optional[float] = None  # Inflation rate
    
    # Market shocks
    shocks: List[StressShock] = Field(default_factory=list)
    
    def add_shock(self, shock: StressShock) -> None:
        """Add a stress shock to the scenario."""
        self.shocks.append(shock)
    
    def get_shocks_by_factor(self, risk_factor: RiskFactor) -> List[StressShock]:
        """Get all shocks for a specific risk factor."""
        return [shock for shock in self.shocks if shock.risk_factor == risk_factor]
    
    def get_shock_value(self, risk_factor: RiskFactor, 
                       currency: Optional[str] = None,
                       sector: Optional[str] = None) -> float:
        """Get shock value for specific risk factor and filters."""
        matching_shocks = self.get_shocks_by_factor(risk_factor)
        
        # Filter by currency and sector if specified
        if currency:
            matching_shocks = [s for s in matching_shocks if s.currency == currency or s.currency is None]
        if sector:
            matching_shocks = [s for s in matching_shocks if s.sector == sector or s.sector is None]
        
        if not matching_shocks:
            return 0.0
        
        # Return the most specific shock (with most filters)
        best_shock = max(matching_shocks, key=lambda s: (
            1 if s.currency == currency else 0,
            1 if s.sector == sector else 0
        ))
        
        return best_shock.shock_value


class StressScenario(BaseModel):
    """Complete stress testing scenario with transmission mechanisms."""
    
    macro_scenario: MacroScenario
    transmission_functions: Dict[str, Any] = Field(default_factory=dict)
    
    def calculate_pd_stress(self, base_pd: float, sector: Optional[str] = None,
                          geography: Optional[str] = None) -> float:
        """Calculate stressed PD based on macro scenario."""
        # Get credit shock
        credit_shock = self.macro_scenario.get_shock_value(
            RiskFactor.DEFAULT_RATES, sector=sector
        )
        
        if credit_shock == 0:
            # Use GDP shock as proxy if no direct credit shock
            gdp_shock = self.macro_scenario.get_shock_value(RiskFactor.GDP_GROWTH)
            if gdp_shock < 0:  # Negative GDP growth increases PDs
                credit_shock = abs(gdp_shock) * 2  # Amplification factor
        
        # Apply logistic transformation to ensure PD stays in [0,1]
        if credit_shock != 0:
            log_odds = math.log(base_pd / (1 - base_pd))
            stressed_log_odds = log_odds + credit_shock
            stressed_pd = math.exp(stressed_log_odds) / (1 + math.exp(stressed_log_odds))
            return min(0.99, stressed_pd)
        
        return base_pd
    
    def calculate_lgd_stress(self, base_lgd: float, sector: Optional[str] = None) -> float:
        """Calculate stressed LGD based on macro scenario."""
        # Recovery rates are inversely related to LGD
        recovery_shock = self.macro_scenario.get_shock_value(
            RiskFactor.RECOVERY_RATES, sector=sector
        )
        
        if recovery_shock == 0:
            # Use real estate shock as proxy for collateral values
            re_shock = self.macro_scenario.get_shock_value(RiskFactor.REAL_ESTATE_PRICES)
            if re_shock < 0:  # Falling property prices increase LGD
                recovery_shock = re_shock  # Negative shock reduces recovery
        
        # Apply shock to recovery rate, then convert back to LGD
        base_recovery = 1 - base_lgd
        stressed_recovery = max(0.01, base_recovery * (1 + recovery_shock))
        stressed_lgd = min(0.99, 1 - stressed_recovery)
        
        return stressed_lgd
    
    def calculate_market_value_stress(self, base_value: float, asset_class: str,
                                    currency: str = "EUR") -> float:
        """Calculate stressed market value for trading assets."""
        stressed_value = base_value
        
        # Apply interest rate shock
        if asset_class in ["bond", "fixed_income"]:
            ir_shock = self.macro_scenario.get_shock_value(
                RiskFactor.INTEREST_RATES, currency=currency
            )
            if ir_shock != 0:
                # Simplified duration impact (assume 5-year duration)
                duration = 5.0
                price_change = -duration * (ir_shock / 100)  # Convert bps to decimal
                stressed_value *= (1 + price_change)
        
        # Apply equity shock
        if asset_class in ["equity", "stock"]:
            equity_shock = self.macro_scenario.get_shock_value(RiskFactor.EQUITY_PRICES)
            stressed_value *= (1 + equity_shock)
        
        # Apply FX shock
        if currency != "EUR":
            fx_shock = self.macro_scenario.get_shock_value(
                RiskFactor.FX_RATES, currency=currency
            )
            stressed_value *= (1 + fx_shock)
        
        # Apply credit spread shock for corporate bonds
        if asset_class in ["corporate_bond", "bank_bond"]:
            spread_shock = self.macro_scenario.get_shock_value(RiskFactor.CREDIT_SPREADS)
            if spread_shock != 0:
                # Simplified spread duration impact
                spread_duration = 4.0
                spread_change = -spread_duration * (spread_shock / 100)
                stressed_value *= (1 + spread_change)
        
        return max(0, stressed_value)
    
    def calculate_exposure_stress(self, base_exposure: float, exposure_type: str) -> float:
        """Calculate stressed exposure (EAD) for off-balance sheet items."""
        if exposure_type in ["commitment", "line_of_credit"]:
            # Economic stress typically increases drawdown rates
            gdp_shock = self.macro_scenario.get_shock_value(RiskFactor.GDP_GROWTH)
            if gdp_shock < 0:
                # Increase CCF by 10-20% under stress
                ccf_increase = abs(gdp_shock) * 0.5
                return base_exposure * (1 + ccf_increase)
        
        return base_exposure


# Predefined scenarios
def create_baseline_scenario() -> StressScenario:
    """Create baseline (no stress) scenario."""
    macro = MacroScenario(
        scenario_id="baseline_2024",
        scenario_name="Baseline Scenario",
        scenario_type=ScenarioType.BASELINE,
        description="No stress - current market conditions",
        gdp_growth=0.02,  # 2% GDP growth
        unemployment_rate=0.07,  # 7% unemployment
        inflation_rate=0.02  # 2% inflation
    )
    
    return StressScenario(macro_scenario=macro)


def create_adverse_scenario() -> StressScenario:
    """Create adverse stress scenario."""
    macro = MacroScenario(
        scenario_id="adverse_2024",
        scenario_name="Adverse Scenario",
        scenario_type=ScenarioType.ADVERSE,
        description="Severe economic downturn with financial market stress",
        gdp_growth=-0.03,  # -3% GDP contraction
        unemployment_rate=0.12,  # 12% unemployment
        inflation_rate=0.01  # 1% low inflation
    )
    
    # Add market shocks
    shocks = [
        StressShock(
            risk_factor=RiskFactor.INTEREST_RATES,
            shock_value=300,  # +300 bps
            shock_type="absolute",
            currency="EUR"
        ),
        StressShock(
            risk_factor=RiskFactor.FX_RATES,
            shock_value=0.25,  # 25% USD/EUR appreciation
            currency="USD"
        ),
        StressShock(
            risk_factor=RiskFactor.EQUITY_PRICES,
            shock_value=-0.3  # -30% equity decline
        ),
        StressShock(
            risk_factor=RiskFactor.REAL_ESTATE_PRICES,
            shock_value=-0.2  # -20% property decline
        ),
        StressShock(
            risk_factor=RiskFactor.DEFAULT_RATES,
            shock_value=0.4,  # 40% increase in default rates
            sector="corporate"
        ),
        StressShock(
            risk_factor=RiskFactor.DEFAULT_RATES,
            shock_value=0.6,  # 60% increase for retail
            sector="retail"
        ),
        StressShock(
            risk_factor=RiskFactor.RECOVERY_RATES,
            shock_value=-0.15  # 15% reduction in recovery rates
        ),
        StressShock(
            risk_factor=RiskFactor.CREDIT_SPREADS,
            shock_value=200  # +200 bps credit spread widening
        )
    ]
    
    for shock in shocks:
        macro.add_shock(shock)
    
    return StressScenario(macro_scenario=macro)


def create_severely_adverse_scenario() -> StressScenario:
    """Create severely adverse stress scenario."""
    macro = MacroScenario(
        scenario_id="severely_adverse_2024",
        scenario_name="Severely Adverse Scenario",
        scenario_type=ScenarioType.SEVERELY_ADVERSE,
        description="Extreme tail risk scenario with systemic crisis",
        gdp_growth=-0.08,  # -8% GDP contraction
        unemployment_rate=0.18,  # 18% unemployment
        inflation_rate=-0.01  # -1% deflation
    )
    
    # Add extreme market shocks
    shocks = [
        StressShock(
            risk_factor=RiskFactor.INTEREST_RATES,
            shock_value=500,  # +500 bps
            shock_type="absolute",
            currency="EUR"
        ),
        StressShock(
            risk_factor=RiskFactor.FX_RATES,
            shock_value=0.4,  # 40% USD/EUR appreciation
            currency="USD"
        ),
        StressShock(
            risk_factor=RiskFactor.EQUITY_PRICES,
            shock_value=-0.5  # -50% equity decline
        ),
        StressShock(
            risk_factor=RiskFactor.REAL_ESTATE_PRICES,
            shock_value=-0.35  # -35% property decline
        ),
        StressShock(
            risk_factor=RiskFactor.DEFAULT_RATES,
            shock_value=1.0,  # 100% increase in corporate defaults
            sector="corporate"
        ),
        StressShock(
            risk_factor=RiskFactor.DEFAULT_RATES,
            shock_value=1.5,  # 150% increase in retail defaults
            sector="retail"
        ),
        StressShock(
            risk_factor=RiskFactor.RECOVERY_RATES,
            shock_value=-0.25  # 25% reduction in recovery rates
        ),
        StressShock(
            risk_factor=RiskFactor.CREDIT_SPREADS,
            shock_value=400  # +400 bps credit spread widening
        ),
        StressShock(
            risk_factor=RiskFactor.VOLATILITY,
            shock_value=1.0  # 100% increase in volatility
        )
    ]
    
    for shock in shocks:
        macro.add_shock(shock)
    
    return StressScenario(macro_scenario=macro)


def create_custom_scenario(scenario_name: str, shocks: Dict[str, float]) -> StressScenario:
    """Create custom stress scenario from shock dictionary."""
    macro = MacroScenario(
        scenario_id=f"custom_{scenario_name.lower().replace(' ', '_')}",
        scenario_name=scenario_name,
        scenario_type=ScenarioType.CUSTOM,
        description=f"Custom scenario: {scenario_name}"
    )
    
    # Map shock dictionary to StressShock objects
    shock_mapping = {
        "interest_rate": RiskFactor.INTEREST_RATES,
        "fx_usd": RiskFactor.FX_RATES,
        "equity": RiskFactor.EQUITY_PRICES,
        "real_estate": RiskFactor.REAL_ESTATE_PRICES,
        "credit_pd": RiskFactor.DEFAULT_RATES,
        "credit_lgd": RiskFactor.RECOVERY_RATES,
        "credit_spread": RiskFactor.CREDIT_SPREADS,
        "gdp": RiskFactor.GDP_GROWTH
    }
    
    for shock_key, shock_value in shocks.items():
        if shock_key in shock_mapping:
            risk_factor = shock_mapping[shock_key]
            
            # Determine shock type based on risk factor
            if risk_factor == RiskFactor.INTEREST_RATES:
                shock_type = "absolute"  # Basis points
            elif risk_factor == RiskFactor.CREDIT_SPREADS:
                shock_type = "absolute"  # Basis points
            else:
                shock_type = "relative"  # Percentage change
            
            stress_shock = StressShock(
                risk_factor=risk_factor,
                shock_value=shock_value,
                shock_type=shock_type,
                currency="USD" if shock_key == "fx_usd" else None
            )
            macro.add_shock(stress_shock)
    
    return StressScenario(macro_scenario=macro)


# Scenario library
PREDEFINED_SCENARIOS = {
    "baseline": create_baseline_scenario,
    "adverse": create_adverse_scenario,
    "severely_adverse": create_severely_adverse_scenario
}


def get_scenario(scenario_name: str) -> StressScenario:
    """Get predefined scenario by name."""
    if scenario_name in PREDEFINED_SCENARIOS:
        return PREDEFINED_SCENARIOS[scenario_name]()
    else:
        raise ValueError(f"Unknown scenario: {scenario_name}. Available: {list(PREDEFINED_SCENARIOS.keys())}")


def list_available_scenarios() -> List[str]:
    """List all available predefined scenarios."""
    return list(PREDEFINED_SCENARIOS.keys())
