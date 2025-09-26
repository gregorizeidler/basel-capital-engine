# Basel Capital Engine - Technical Guide

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Components](#core-components)
3. [RWA Calculations](#rwa-calculations)
4. [Capital Structure](#capital-structure)
5. [Stress Testing Framework](#stress-testing-framework)
6. [Configuration System](#configuration-system)
7. [API Reference](#api-reference)
8. [Extending the Engine](#extending-the-engine)

## Architecture Overview

The Basel Capital Engine follows a modular architecture designed for flexibility, extensibility, and regulatory compliance. The system is organized into several key layers:

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interfaces                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Streamlit   │  │ FastAPI     │  │ Jupyter Notebooks   │ │
│  │ Dashboard   │  │ REST API    │  │                     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Basel       │  │ Stress Test │  │ Portfolio           │ │
│  │ Engine      │  │ Engine      │  │ Generator           │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                    Business Logic Layer                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Credit RWA  │  │ Market RWA  │  │ Operational RWA     │ │
│  │ Calculator  │  │ Calculator  │  │ Calculator          │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Capital     │  │ Buffers     │  │ Metrics             │ │
│  │ Calculator  │  │ Manager     │  │ Calculator          │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                    Domain Model Layer                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Exposure    │  │ Capital     │  │ Portfolio           │ │
│  │ Models      │  │ Models      │  │ Models              │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                    Configuration Layer                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Basel       │  │ Risk        │  │ Stress Scenarios    │ │
│  │ Config      │  │ Weights     │  │                     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Modularity**: Each component has a single responsibility and can be used independently
2. **Configurability**: All parameters can be configured via YAML files or programmatically
3. **Extensibility**: New risk types and calculation methods can be added easily
4. **Transparency**: All calculations are explainable and auditable
5. **Performance**: Optimized for large portfolios with optional performance enhancements

## Core Components

### Exposure Model

The `Exposure` class represents individual financial exposures with all necessary attributes for regulatory capital calculations:

```python
class Exposure(BaseModel):
    # Identity
    exposure_id: str
    counterparty_id: Optional[str]
    
    # Classification
    exposure_type: ExposureType  # LOANS, SECURITIES, DERIVATIVES, etc.
    exposure_class: ExposureClass  # SOVEREIGN, CORPORATE, RETAIL, etc.
    
    # Amounts
    original_exposure: float
    current_exposure: float
    market_value: Optional[float]
    
    # Credit risk parameters
    probability_of_default: Optional[float]  # PD as decimal
    loss_given_default: Optional[float]      # LGD as decimal
    maturity: Optional[float]                # Years
    
    # Risk mitigation
    crm: Optional[CreditRiskMitigation]
    
    # Market risk
    sensitivities: Optional[Dict[str, float]]
```

**Key Methods:**
- `get_exposure_at_default()`: Calculates EAD considering CCF for off-balance sheet items
- `get_effective_maturity()`: Applies regulatory floors and caps (1-5 years)
- `apply_credit_risk_mitigation()`: Reduces exposure based on collateral/guarantees
- `is_retail()`: Determines if exposure qualifies for retail treatment
- `is_trading_book()`: Classifies as trading vs banking book

### Portfolio Model

The `Portfolio` class manages collections of exposures:

```python
class Portfolio(BaseModel):
    portfolio_id: str
    bank_name: Optional[str]
    reporting_date: Optional[str]
    exposures: List[Exposure]
    
    # Methods
    def get_total_exposure(self) -> float
    def get_exposures_by_class(self, exposure_class: ExposureClass) -> List[Exposure]
    def get_trading_book_exposures(self) -> List[Exposure]
    def get_concentration_metrics(self) -> Dict[str, Any]
```

### Capital Model

The capital structure is modeled with full Basel III compliance:

```python
class CapitalComponents(BaseModel):
    # CET1 components
    common_shares: float
    retained_earnings: float
    accumulated_oci: float
    minority_interests: float
    
    # Additional Tier 1
    at1_instruments: float
    
    # Tier 2
    t2_instruments: float
    general_provisions: float
    
    # Regulatory adjustments
    goodwill: float
    intangible_assets: float
    deferred_tax_assets: float
    # ... other deductions
```

**Capital Hierarchy:**
1. **CET1** = CET1 components - Regulatory adjustments
2. **Tier 1** = CET1 + AT1 instruments
3. **Total Capital** = Tier 1 + Tier 2 (capped at 100% of Tier 1)

## RWA Calculations

### Credit Risk RWA

The engine supports multiple approaches for credit risk:

#### Standardized Approach (SA)

Risk weights are assigned based on asset class and external rating:

| Asset Class | AAA/AA | A | BBB/BB | B and below | Unrated |
|-------------|--------|---|--------|-------------|---------|
| Sovereign   | 0%     | 20% | 50%   | 100%        | 100%    |
| Bank        | 20%    | 50% | 100%  | 150%        | 100%    |
| Corporate   | 20%    | 50% | 100%  | 150%        | 100%    |
| Retail Mortgage | 35% | 35% | 35%  | 35%         | 35%     |
| Retail Other | 75%   | 75% | 75%   | 75%         | 75%     |

**Calculation Formula:**
```
RWA = Σ(EAD × Risk Weight × (1 - CRM effectiveness))
```

Where:
- EAD = Exposure at Default
- CRM = Credit Risk Mitigation

#### IRB Approach (Mock Implementation)

For educational purposes, the engine includes a simplified IRB implementation:

**Corporate Formula (simplified):**
```python
def calculate_corporate_irb_rw(pd: float, lgd: float, maturity: float) -> float:
    # Correlation
    correlation = 0.24 * (1 - exp(-50 * pd)) / (1 - exp(-50))
    
    # Maturity adjustment
    b_factor = (0.11852 - 0.05478 * log(pd)) ** 2
    maturity_adj = (1 + (maturity - 2.5) * b_factor) / (1 - 1.5 * b_factor)
    
    # Risk weight calculation
    conditional_pd = normal_cdf(
        (sqrt(correlation) * normal_inv(0.999) + 
         sqrt(1-correlation) * normal_inv(pd)) / sqrt(1-correlation)
    )
    
    return min(lgd * conditional_pd * maturity_adj * 12.5, 12.5)
```

### Market Risk RWA

#### FRTB Sensitivities-Based Approach

The engine implements a simplified version of FRTB SA:

**Risk Classes:**
1. **GIRR** (General Interest Rate Risk)
2. **CSR-NS** (Credit Spread Risk - Non-Securitizations)
3. **Equity Risk**
4. **FX Risk**
5. **Commodity Risk**

**Calculation Steps:**
1. Extract delta sensitivities by risk factor
2. Apply risk weights by tenor/bucket
3. Aggregate within risk class using correlations
4. Sum across risk classes
5. Convert to RWA (×12.5)

**Interest Rate Risk Weights:**
| Tenor | Risk Weight |
|-------|-------------|
| 2w-1m | 1.7%        |
| 3m-6m | 1.3-1.1%    |
| 1y-30y| 1.0%        |

#### VaR Approach (Fallback)

Simplified VaR calculation for comparison:

```python
def calculate_var_rwa(exposures: List[Exposure]) -> float:
    portfolio_value = sum(exp.market_value for exp in exposures)
    daily_var = portfolio_value * 0.02  # 2% daily VaR assumption
    ten_day_var = daily_var * sqrt(10)
    return ten_day_var * 3.0 * 12.5  # 3x multiplier, 12.5 conversion
```

### Operational Risk RWA

#### Standardized Measurement Approach (SMA)

The SMA calculation follows Basel III requirements:

**Business Indicator (BI) Components:**
1. **ILDC** (Interest, Lease and Dividend Component) = Interest Income + Dividend Income
2. **SCTB** (Services Component) = max(0, Fee Income - Fee Expense)
3. **FB** (Financial Component) = |Trading Income| + |Other Income - Other Expense|

**BI = ILDC + SCTB + FB**

**Business Indicator Component (BIC):**
- Bucket 1 (BI ≤ €1bn): 12% marginal coefficient
- Bucket 2 (€1bn < BI ≤ €30bn): 15% marginal coefficient  
- Bucket 3 (BI > €30bn): 18% marginal coefficient

**Internal Loss Multiplier (ILM):**
```python
def calculate_ilm(historical_losses: float, business_indicator: float) -> float:
    if historical_losses <= 20_000_000:  # €20M threshold
        return 1.0
    
    loss_component = historical_losses
    alpha = 0.2
    ilm = log(exp(1) - 1 + (loss_component / business_indicator) ** alpha)
    
    return max(1.0, min(5.0, ilm))  # Bounded between 1 and 5
```

**Final Calculation:**
```
Operational RWA = BIC × ILM × 12.5
```

## Capital Structure

### CET1 Capital Calculation

```python
def calculate_cet1(components: CapitalComponents) -> float:
    # Base CET1
    base_cet1 = (
        components.common_shares +
        components.retained_earnings +
        components.accumulated_oci +
        components.minority_interests
    )
    
    # Regulatory adjustments (deductions)
    adjustments = (
        components.goodwill +
        components.intangible_assets +
        components.deferred_tax_assets +
        components.investments_in_own_shares +
        # ... other deductions
    )
    
    return max(0, base_cet1 - adjustments)
```

### Tier 2 Limitation

Tier 2 capital is limited to 100% of Tier 1 capital:

```python
def calculate_total_capital(cet1: float, at1: float, t2: float) -> float:
    tier1 = cet1 + at1
    eligible_t2 = min(t2, tier1)  # T2 cap
    return tier1 + eligible_t2
```

## Stress Testing Framework

### Scenario Definition

Stress scenarios are defined using the `MacroScenario` model:

```python
class MacroScenario(BaseModel):
    scenario_id: str
    scenario_name: str
    scenario_type: ScenarioType  # BASELINE, ADVERSE, SEVERELY_ADVERSE
    description: str
    time_horizon: int = 3  # years
    
    # Macroeconomic variables
    gdp_growth: Optional[float]
    unemployment_rate: Optional[float]
    inflation_rate: Optional[float]
    
    # Market shocks
    shocks: List[StressShock]
```

### Transmission Mechanisms

The stress engine translates macro shocks to risk parameter changes:

#### PD Stress Transmission

```python
def calculate_pd_stress(base_pd: float, gdp_shock: float, sector: str) -> float:
    # Logistic transformation to ensure PD ∈ [0,1]
    log_odds = log(base_pd / (1 - base_pd))
    
    # Apply sector-specific amplification
    sector_multiplier = get_sector_multiplier(sector)
    stress_impact = gdp_shock * sector_multiplier
    
    stressed_log_odds = log_odds + stress_impact
    stressed_pd = exp(stressed_log_odds) / (1 + exp(stressed_log_odds))
    
    return min(0.99, stressed_pd)
```

#### Market Value Stress

```python
def calculate_market_stress(base_value: float, asset_class: str, 
                          ir_shock: float, fx_shock: float) -> float:
    stressed_value = base_value
    
    # Interest rate impact (duration-based)
    if asset_class in ["bond", "fixed_income"]:
        duration = estimate_duration(asset_class)
        ir_impact = -duration * (ir_shock / 10000)  # Convert bps
        stressed_value *= (1 + ir_impact)
    
    # FX impact
    if has_fx_exposure(asset_class):
        stressed_value *= (1 + fx_shock)
    
    return max(0, stressed_value)
```

### Predefined Scenarios

#### Adverse Scenario
- GDP: -3% contraction
- Interest rates: +300 bps
- FX (USD/EUR): +25% appreciation
- Equity prices: -30%
- Credit PDs: +40% increase
- Real estate: -20% decline

#### Severely Adverse Scenario
- GDP: -8% contraction  
- Interest rates: +500 bps
- FX (USD/EUR): +40% appreciation
- Equity prices: -50%
- Credit PDs: +100% increase
- Real estate: -35% decline

## Configuration System

### YAML Configuration

The engine uses YAML for configuration management:

```yaml
# Risk weights for Standardized Approach
risk_weights:
  credit:
    sovereign_aaa_aa: 0.0
    sovereign_a: 0.2
    corporate_bbb_bb: 1.0
    retail_mortgage: 0.35

# Regulatory buffers
buffers:
  conservation: 0.025      # 2.5%
  countercyclical: 0.0     # Variable by jurisdiction
  
# Minimum requirements
minimum_ratios:
  cet1_minimum: 0.045      # 4.5%
  tier1_minimum: 0.06      # 6.0%
  total_capital_minimum: 0.08  # 8.0%
  leverage_minimum: 0.03   # 3.0%
```

### Dynamic Configuration

Configuration can be modified at runtime:

```python
# Load and modify configuration
config = BaselConfig.load_default()
config.risk_weights["credit"]["corporate_bbb_bb"] = 1.2  # Increase weight

# Create engine with modified config
engine = BaselEngine(config)
```

## API Reference

### Core Classes

#### BaselEngine
Main calculation engine coordinating all components.

**Methods:**
- `calculate_all_metrics(portfolio, capital, buffers)` → `BaselResults`
- `calculate_rwa_only(portfolio)` → `Dict[str, float]`
- `validate_inputs(portfolio, capital)` → `List[str]`
- `run_diagnostics(portfolio, capital)` → `Dict[str, Any]`

#### PortfolioGenerator
Generates synthetic portfolios for testing.

**Methods:**
- `generate_bank_portfolio(size, bank_name)` → `Tuple[Portfolio, Capital]`
- `generate_stressed_portfolio(portfolio, scenario)` → `Portfolio`

#### StressTestEngine
Conducts stress testing analysis.

**Methods:**
- `run_stress_test(portfolio, capital, scenario)` → `StressTestResults`
- `run_multiple_scenarios(portfolio, capital, scenarios)` → `Dict[str, StressTestResults]`

### REST API Endpoints

#### Portfolio Analysis
```
POST /portfolio
Content-Type: application/json

{
  "portfolio": { ... },
  "capital": { ... },
  "config_overrides": { ... }
}
```

#### Stress Testing
```
POST /stress
Content-Type: application/json

{
  "portfolio": { ... },
  "capital": { ... },
  "scenarios": ["adverse", "severely_adverse"]
}
```

#### Explanation
```
GET /explain/{calculation_id}
```

Returns detailed breakdown of calculations.

## Extending the Engine

### Adding New Risk Types

1. **Create Risk Calculator:**
```python
class NewRiskCalculator:
    def __init__(self, config: BaselConfig):
        self.config = config
    
    def calculate_rwa(self, portfolio: Portfolio) -> float:
        # Implementation
        pass
    
    def get_detailed_breakdown(self, portfolio: Portfolio) -> Dict[str, Any]:
        # Implementation
        pass
```

2. **Integrate with Engine:**
```python
class ExtendedBaselEngine(BaselEngine):
    def __init__(self, config: BaselConfig):
        super().__init__(config)
        self.new_risk_calculator = NewRiskCalculator(config)
    
    def calculate_all_metrics(self, portfolio, capital, buffers):
        # Add new risk calculation
        new_risk_rwa = self.new_risk_calculator.calculate_rwa(portfolio)
        # ... integrate with existing calculations
```

### Custom Stress Scenarios

```python
def create_custom_scenario(name: str, shocks: Dict[str, float]) -> StressScenario:
    macro = MacroScenario(
        scenario_id=f"custom_{name}",
        scenario_name=name,
        scenario_type=ScenarioType.CUSTOM,
        description=f"Custom scenario: {name}"
    )
    
    # Add shocks
    for risk_factor, shock_value in shocks.items():
        stress_shock = StressShock(
            risk_factor=RiskFactor(risk_factor),
            shock_value=shock_value
        )
        macro.add_shock(stress_shock)
    
    return StressScenario(macro_scenario=macro)
```

### Custom Risk Weights

```python
# Modify configuration
config = BaselConfig.load_default()

# Add custom risk weights
config.risk_weights["credit"]["custom_asset_class"] = 0.85

# Or load from custom YAML
custom_config = BaselConfig.load_from_file("custom_basel_config.yaml")
```

## Performance Considerations

### Large Portfolios

For portfolios with >10,000 exposures:

1. **Use Polars** for data processing:
```python
# Optional performance enhancement
pip install basileia-engine[performance]
```

2. **Batch Processing:**
```python
# Process portfolio in chunks
chunk_size = 1000
for i in range(0, len(portfolio.exposures), chunk_size):
    chunk = portfolio.exposures[i:i+chunk_size]
    # Process chunk
```

3. **Parallel Calculation:**
```python
from concurrent.futures import ProcessPoolExecutor

def calculate_chunk_rwa(exposures_chunk):
    # Calculate RWA for chunk
    pass

# Parallel processing
with ProcessPoolExecutor() as executor:
    results = executor.map(calculate_chunk_rwa, exposure_chunks)
```

### Memory Optimization

For memory-constrained environments:

```python
# Use generators for large datasets
def exposure_generator(data_source):
    for row in data_source:
        yield create_exposure_from_row(row)

# Process without loading all into memory
total_rwa = 0
for exposure in exposure_generator(large_dataset):
    rwa = calculate_single_exposure_rwa(exposure)
    total_rwa += rwa
```

## Validation and Testing

### Property-Based Testing

The engine uses Hypothesis for property-based testing:

```python
from hypothesis import given, strategies as st

@given(st.floats(min_value=0.0001, max_value=0.99))
def test_pd_increase_increases_rwa(pd):
    # Test that increasing PD never decreases RWA
    exposure1 = create_exposure(pd=pd)
    exposure2 = create_exposure(pd=pd * 1.5)
    
    rwa1 = calculate_rwa(exposure1)
    rwa2 = calculate_rwa(exposure2)
    
    assert rwa2 >= rwa1
```

### Invariant Testing

Key invariants are continuously tested:

1. **Capital Hierarchy:** Total ≥ Tier1 ≥ CET1 ≥ 0
2. **RWA Non-negativity:** All RWA components ≥ 0
3. **Ratio Bounds:** 0 ≤ ratios ≤ 100%
4. **Monotonicity:** Increasing risk → Increasing RWA

### Benchmarking

Compare against known results:

```python
def test_standardized_approach_benchmark():
    # Known portfolio with expected results
    portfolio = create_benchmark_portfolio()
    
    results = engine.calculate_rwa_only(portfolio)
    
    # Compare against expected values
    assert abs(results["credit_rwa"] - EXPECTED_CREDIT_RWA) < TOLERANCE
```

## Regulatory Compliance

### Basel III Alignment

The engine implements key Basel III requirements:

- ✅ **CRD IV/CRR** capital definitions
- ✅ **Standardized Approach** for credit risk
- ✅ **FRTB** (simplified) for market risk  
- ✅ **SMA** for operational risk
- ✅ **Leverage Ratio** calculation
- ✅ **Capital buffers** and MDA restrictions

### Jurisdictional Differences

Support for different implementations:

```python
# EU implementation
eu_config = BaselConfig.load_from_file("configs/eu_crd_config.yaml")

# US implementation  
us_config = BaselConfig.load_from_file("configs/us_basel_config.yaml")

# Custom jurisdiction
custom_config = BaselConfig()
custom_config.minimum_ratios["cet1_minimum"] = 0.07  # Higher requirement
```

### Audit Trail

All calculations maintain full audit trails:

```python
results = engine.calculate_all_metrics(portfolio, capital)

# Access detailed breakdown
print(results.rwa_breakdown)
print(results.capital_breakdown)

# Export for audit
results.export_audit_trail("audit_trail.json")
```

This technical guide provides a comprehensive overview of the Basel Capital Engine's architecture, calculations, and usage. For specific implementation details, refer to the source code documentation and API reference.
