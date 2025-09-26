"""Capital ratios and leverage calculations for Basel Capital Engine."""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import logging

from ..core.capital import Capital
from ..core.exposure import Portfolio, ExposureType
from ..core.config import BaselConfig

logger = logging.getLogger(__name__)


class RatioResults(BaseModel):
    """Results from capital ratio calculations."""
    
    cet1_ratio: float = Field(ge=0, description="CET1 ratio")
    tier1_ratio: float = Field(ge=0, description="Tier 1 ratio")
    total_capital_ratio: float = Field(ge=0, description="Total capital ratio")
    
    # Minimum requirements
    cet1_minimum: float = Field(default=0.045)
    tier1_minimum: float = Field(default=0.06)
    total_minimum: float = Field(default=0.08)
    
    # Excess/shortfall
    cet1_excess: float = Field(description="CET1 excess over minimum")
    tier1_excess: float = Field(description="Tier 1 excess over minimum")
    total_excess: float = Field(description="Total capital excess over minimum")
    
    def meets_requirements(self) -> bool:
        """Check if all ratios meet minimum requirements."""
        return (
            self.cet1_ratio >= self.cet1_minimum and
            self.tier1_ratio >= self.tier1_minimum and
            self.total_capital_ratio >= self.total_minimum
        )
    
    def get_binding_constraint(self) -> str:
        """Identify the binding constraint (lowest ratio relative to requirement)."""
        cet1_margin = self.cet1_ratio - self.cet1_minimum
        tier1_margin = self.tier1_ratio - self.tier1_minimum
        total_margin = self.total_capital_ratio - self.total_minimum
        
        margins = {
            "CET1": cet1_margin,
            "Tier 1": tier1_margin,
            "Total Capital": total_margin
        }
        
        return min(margins.items(), key=lambda x: x[1])[0]


class LeverageRatioResults(BaseModel):
    """Results from leverage ratio calculations."""
    
    leverage_ratio: float = Field(ge=0, description="Leverage ratio")
    tier1_capital: float = Field(ge=0, description="Tier 1 capital")
    total_exposure_measure: float = Field(ge=0, description="Total exposure measure")
    
    # Components of exposure measure
    on_balance_sheet: float = Field(default=0, ge=0)
    derivatives: float = Field(default=0, ge=0)
    securities_financing: float = Field(default=0, ge=0)
    off_balance_sheet: float = Field(default=0, ge=0)
    
    # Minimum requirement
    minimum_leverage_ratio: float = Field(default=0.03)
    
    def meets_requirement(self) -> bool:
        """Check if leverage ratio meets minimum requirement."""
        return self.leverage_ratio >= self.minimum_leverage_ratio
    
    def get_excess_shortfall(self) -> float:
        """Get excess or shortfall in leverage ratio."""
        return self.leverage_ratio - self.minimum_leverage_ratio


class CapitalRatios:
    """Calculator for capital adequacy ratios."""
    
    def __init__(self, config: BaselConfig):
        self.config = config
    
    def calculate_all_ratios(self, capital: Capital, total_rwa: float) -> RatioResults:
        """Calculate all capital ratios."""
        if total_rwa <= 0:
            logger.warning("Total RWA is zero or negative, ratios cannot be calculated")
            return RatioResults(
                cet1_ratio=0,
                tier1_ratio=0,
                total_capital_ratio=0,
                cet1_excess=-self.config.get_minimum_ratio("cet1_minimum"),
                tier1_excess=-self.config.get_minimum_ratio("tier1_minimum"),
                total_excess=-self.config.get_minimum_ratio("total_capital_minimum")
            )
        
        # Get capital amounts
        cet1_capital = capital.calculate_cet1_capital()
        tier1_capital = capital.calculate_tier1_capital()
        total_capital = capital.calculate_total_capital()
        
        # Calculate ratios
        cet1_ratio = cet1_capital / total_rwa
        tier1_ratio = tier1_capital / total_rwa
        total_capital_ratio = total_capital / total_rwa
        
        # Get minimum requirements
        cet1_min = self.config.get_minimum_ratio("cet1_minimum")
        tier1_min = self.config.get_minimum_ratio("tier1_minimum")
        total_min = self.config.get_minimum_ratio("total_capital_minimum")
        
        return RatioResults(
            cet1_ratio=cet1_ratio,
            tier1_ratio=tier1_ratio,
            total_capital_ratio=total_capital_ratio,
            cet1_minimum=cet1_min,
            tier1_minimum=tier1_min,
            total_minimum=total_min,
            cet1_excess=cet1_ratio - cet1_min,
            tier1_excess=tier1_ratio - tier1_min,
            total_excess=total_capital_ratio - total_min
        )
    
    def calculate_required_capital(self, total_rwa: float, target_ratio: float, 
                                 tier: str = "cet1") -> float:
        """Calculate required capital to achieve target ratio."""
        return total_rwa * target_ratio
    
    def calculate_capital_impact(self, current_capital: float, current_rwa: float,
                               rwa_change: float) -> Dict[str, float]:
        """Calculate impact of RWA change on capital ratios."""
        current_ratio = current_capital / current_rwa if current_rwa > 0 else 0
        new_rwa = current_rwa + rwa_change
        new_ratio = current_capital / new_rwa if new_rwa > 0 else 0
        
        return {
            "current_ratio": current_ratio,
            "new_ratio": new_ratio,
            "ratio_change": new_ratio - current_ratio,
            "ratio_change_bps": (new_ratio - current_ratio) * 10000
        }


class LeverageRatio:
    """Calculator for leverage ratio."""
    
    def __init__(self, config: BaselConfig):
        self.config = config
    
    def calculate(self, portfolio: Portfolio, capital: Capital) -> LeverageRatioResults:
        """Calculate leverage ratio and components."""
        tier1_capital = capital.calculate_tier1_capital()
        
        # Calculate exposure measure components
        on_balance_sheet = self._calculate_on_balance_sheet_exposure(portfolio)
        derivatives = self._calculate_derivatives_exposure(portfolio)
        securities_financing = self._calculate_securities_financing_exposure(portfolio)
        off_balance_sheet = self._calculate_off_balance_sheet_exposure(portfolio)
        
        total_exposure_measure = (
            on_balance_sheet + derivatives + securities_financing + off_balance_sheet
        )
        
        leverage_ratio = tier1_capital / total_exposure_measure if total_exposure_measure > 0 else 0
        
        return LeverageRatioResults(
            leverage_ratio=leverage_ratio,
            tier1_capital=tier1_capital,
            total_exposure_measure=total_exposure_measure,
            on_balance_sheet=on_balance_sheet,
            derivatives=derivatives,
            securities_financing=securities_financing,
            off_balance_sheet=off_balance_sheet,
            minimum_leverage_ratio=self.config.get_minimum_ratio("leverage_minimum")
        )
    
    def _calculate_on_balance_sheet_exposure(self, portfolio: Portfolio) -> float:
        """Calculate on-balance sheet exposure for leverage ratio."""
        on_balance_types = [
            ExposureType.LOANS,
            ExposureType.SECURITIES,
            ExposureType.CASH
        ]
        
        exposure = 0.0
        for exp in portfolio.exposures:
            if exp.exposure_type in on_balance_types:
                # Use accounting value (current_exposure) minus specific provisions
                exposure += exp.current_exposure
        
        return exposure
    
    def _calculate_derivatives_exposure(self, portfolio: Portfolio) -> float:
        """Calculate derivatives exposure using SA-CCR approach (simplified)."""
        derivatives_exposure = 0.0
        
        for exp in portfolio.exposures:
            if exp.exposure_type == ExposureType.DERIVATIVES:
                # Simplified SA-CCR: Replacement Cost + Add-on
                replacement_cost = max(0, exp.market_value or 0)
                
                # Simplified add-on based on notional and asset class
                notional = exp.current_exposure
                add_on = self._calculate_derivative_addon(exp, notional)
                
                derivatives_exposure += replacement_cost + add_on
        
        return derivatives_exposure
    
    def _calculate_derivative_addon(self, exposure, notional: float) -> float:
        """Calculate derivative add-on (simplified SA-CCR)."""
        # Simplified add-on factors by asset class
        addon_factors = {
            "interest_rate": 0.005,  # 0.5%
            "fx": 0.04,             # 4.0%
            "equity": 0.07,         # 7.0%
            "commodity": 0.10,      # 10.0%
            "credit": 0.05          # 5.0%
        }
        
        asset_class = getattr(exposure, 'asset_class', 'interest_rate')
        factor = addon_factors.get(asset_class, 0.05)
        
        return notional * factor
    
    def _calculate_securities_financing_exposure(self, portfolio: Portfolio) -> float:
        """Calculate securities financing transactions exposure."""
        # Simplified - in practice this would include repos, reverse repos, etc.
        return 0.0
    
    def _calculate_off_balance_sheet_exposure(self, portfolio: Portfolio) -> float:
        """Calculate off-balance sheet exposure."""
        off_balance_types = [
            ExposureType.COMMITMENTS,
            ExposureType.GUARANTEES
        ]
        
        exposure = 0.0
        for exp in portfolio.exposures:
            if exp.exposure_type in off_balance_types:
                # Apply credit conversion factor
                ccf = exp.credit_conversion_factor or self._get_default_ccf(exp)
                exposure += exp.current_exposure * ccf
        
        return exposure
    
    def _get_default_ccf(self, exposure) -> float:
        """Get default credit conversion factor."""
        # Simplified CCF mapping
        ccf_mapping = {
            ExposureType.COMMITMENTS: 0.75,  # Unconditional commitments
            ExposureType.GUARANTEES: 1.0     # Financial guarantees
        }
        
        return ccf_mapping.get(exposure.exposure_type, 0.5)
    
    def calculate_required_tier1_capital(self, total_exposure_measure: float, 
                                       target_leverage_ratio: float) -> float:
        """Calculate required Tier 1 capital to achieve target leverage ratio."""
        return total_exposure_measure * target_leverage_ratio
    
    def analyze_leverage_drivers(self, portfolio: Portfolio) -> Dict[str, Any]:
        """Analyze key drivers of leverage ratio."""
        results = self.calculate(portfolio, None)  # Dummy capital for exposure calculation
        
        total_exposure = results.total_exposure_measure
        
        return {
            "exposure_breakdown": {
                "on_balance_sheet": {
                    "amount": results.on_balance_sheet,
                    "percentage": results.on_balance_sheet / total_exposure if total_exposure > 0 else 0
                },
                "derivatives": {
                    "amount": results.derivatives,
                    "percentage": results.derivatives / total_exposure if total_exposure > 0 else 0
                },
                "securities_financing": {
                    "amount": results.securities_financing,
                    "percentage": results.securities_financing / total_exposure if total_exposure > 0 else 0
                },
                "off_balance_sheet": {
                    "amount": results.off_balance_sheet,
                    "percentage": results.off_balance_sheet / total_exposure if total_exposure > 0 else 0
                }
            },
            "largest_component": self._identify_largest_component(results),
            "optimization_opportunities": self._identify_optimization_opportunities(results)
        }
    
    def _identify_largest_component(self, results: LeverageRatioResults) -> str:
        """Identify the largest component of exposure measure."""
        components = {
            "on_balance_sheet": results.on_balance_sheet,
            "derivatives": results.derivatives,
            "securities_financing": results.securities_financing,
            "off_balance_sheet": results.off_balance_sheet
        }
        
        return max(components.items(), key=lambda x: x[1])[0]
    
    def _identify_optimization_opportunities(self, results: LeverageRatioResults) -> List[str]:
        """Identify potential optimization opportunities."""
        opportunities = []
        
        if results.derivatives > results.total_exposure_measure * 0.3:
            opportunities.append("High derivatives exposure - consider netting optimization")
        
        if results.off_balance_sheet > results.total_exposure_measure * 0.2:
            opportunities.append("Significant off-balance sheet exposure - review CCF optimization")
        
        if results.leverage_ratio < results.minimum_leverage_ratio * 1.1:
            opportunities.append("Low leverage ratio buffer - consider capital raising or exposure reduction")
        
        return opportunities
