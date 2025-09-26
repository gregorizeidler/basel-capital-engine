"""Main Basel Capital Engine coordinating all calculations."""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import logging

from .config import BaselConfig
from .capital import Capital
from .exposure import Portfolio
from .buffers import RegulatoryBuffers, BufferBreach
from ..metrics.ratios import CapitalRatios, LeverageRatio
from ..rwa.credit import CreditRiskCalculator
from ..rwa.market import MarketRiskCalculator
from ..rwa.operational import OperationalRiskCalculator


logger = logging.getLogger(__name__)


class BaselResults(BaseModel):
    """Complete results from Basel capital calculations."""
    
    # Capital amounts
    cet1_capital: float
    tier1_capital: float
    total_capital: float
    
    # RWA breakdown
    credit_rwa: float
    market_rwa: float
    operational_rwa: float
    total_rwa: float
    
    # Capital ratios
    cet1_ratio: float
    tier1_ratio: float
    basel_ratio: float  # Total capital ratio
    
    # Leverage ratio
    leverage_ratio: float
    total_exposure_measure: float
    
    # Buffer analysis
    buffer_requirements: Dict[str, float]
    buffer_breaches: List[BufferBreach]
    mda_restrictions: Dict[str, Any]
    
    # Detailed breakdowns
    rwa_breakdown: Dict[str, Any]
    capital_breakdown: Dict[str, Any]
    
    # Metadata
    calculation_date: Optional[str] = None
    bank_name: Optional[str] = None
    
    def meets_minimum_requirements(self) -> bool:
        """Check if bank meets minimum regulatory requirements."""
        return (
            self.cet1_ratio >= 0.045 and  # 4.5%
            self.tier1_ratio >= 0.06 and  # 6.0%
            self.basel_ratio >= 0.08 and  # 8.0%
            self.leverage_ratio >= 0.03    # 3.0%
        )
    
    def get_summary_metrics(self) -> Dict[str, Any]:
        """Get summary of key metrics."""
        return {
            "capital_adequacy": {
                "cet1_ratio": f"{self.cet1_ratio:.2%}",
                "tier1_ratio": f"{self.tier1_ratio:.2%}", 
                "total_capital_ratio": f"{self.basel_ratio:.2%}",
                "leverage_ratio": f"{self.leverage_ratio:.2%}",
            },
            "capital_amounts": {
                "cet1_capital": self.cet1_capital,
                "tier1_capital": self.tier1_capital,
                "total_capital": self.total_capital,
            },
            "rwa_summary": {
                "credit_rwa": self.credit_rwa,
                "market_rwa": self.market_rwa,
                "operational_rwa": self.operational_rwa,
                "total_rwa": self.total_rwa,
            },
            "compliance": {
                "meets_minimums": self.meets_minimum_requirements(),
                "buffer_breaches": len(self.buffer_breaches),
                "mda_applicable": self.mda_restrictions.get("applicable", False),
            }
        }


class BaselEngine:
    """Main engine for Basel III capital calculations."""
    
    def __init__(self, config: Optional[BaselConfig] = None):
        """Initialize Basel engine with configuration."""
        self.config = config or BaselConfig.load_default()
        
        # Initialize risk calculators
        self.credit_calculator = CreditRiskCalculator(self.config)
        self.market_calculator = MarketRiskCalculator(self.config)
        self.operational_calculator = OperationalRiskCalculator(self.config)
        
        logger.info("Basel Capital Engine initialized")
    
    def calculate_all_metrics(self, portfolio: Portfolio, capital: Capital, 
                            buffers: Optional[RegulatoryBuffers] = None) -> BaselResults:
        """Calculate all Basel metrics for a portfolio."""
        logger.info(f"Calculating Basel metrics for portfolio {portfolio.portfolio_id}")
        
        # Calculate RWAs
        credit_rwa = self.credit_calculator.calculate_total_rwa(portfolio)
        market_rwa = self.market_calculator.calculate_total_rwa(portfolio)
        operational_rwa = self.operational_calculator.calculate_rwa(portfolio)
        
        total_rwa = credit_rwa + market_rwa + operational_rwa
        
        # Calculate capital amounts
        cet1_capital = capital.calculate_cet1_capital()
        tier1_capital = capital.calculate_tier1_capital()
        total_capital = capital.calculate_total_capital()
        
        # Calculate ratios
        cet1_ratio = cet1_capital / total_rwa if total_rwa > 0 else 0
        tier1_ratio = tier1_capital / total_rwa if total_rwa > 0 else 0
        basel_ratio = total_capital / total_rwa if total_rwa > 0 else 0
        
        # Calculate leverage ratio
        leverage_calculator = LeverageRatio(self.config)
        leverage_results = leverage_calculator.calculate(portfolio, capital)
        
        # Buffer analysis
        if buffers is None:
            buffers = RegulatoryBuffers()
        
        buffer_breaches = buffers.check_buffer_breaches(
            cet1_ratio, tier1_ratio, basel_ratio, total_rwa
        )
        mda_restrictions = buffers.get_mda_restrictions(buffer_breaches)
        
        # Detailed breakdowns
        rwa_breakdown = {
            "credit": {
                "total": credit_rwa,
                "details": self.credit_calculator.get_detailed_breakdown(portfolio)
            },
            "market": {
                "total": market_rwa,
                "details": self.market_calculator.get_detailed_breakdown(portfolio)
            },
            "operational": {
                "total": operational_rwa,
                "details": self.operational_calculator.get_detailed_breakdown(portfolio)
            }
        }
        
        return BaselResults(
            cet1_capital=cet1_capital,
            tier1_capital=tier1_capital,
            total_capital=total_capital,
            credit_rwa=credit_rwa,
            market_rwa=market_rwa,
            operational_rwa=operational_rwa,
            total_rwa=total_rwa,
            cet1_ratio=cet1_ratio,
            tier1_ratio=tier1_ratio,
            basel_ratio=basel_ratio,
            leverage_ratio=leverage_results.leverage_ratio,
            total_exposure_measure=leverage_results.total_exposure_measure,
            buffer_requirements=buffers.get_buffer_breakdown(),
            buffer_breaches=buffer_breaches,
            mda_restrictions=mda_restrictions,
            rwa_breakdown=rwa_breakdown,
            capital_breakdown=capital.get_capital_summary(),
            bank_name=portfolio.bank_name,
        )
    
    def calculate_rwa_only(self, portfolio: Portfolio) -> Dict[str, float]:
        """Calculate only RWA components."""
        credit_rwa = self.credit_calculator.calculate_total_rwa(portfolio)
        market_rwa = self.market_calculator.calculate_total_rwa(portfolio)
        operational_rwa = self.operational_calculator.calculate_rwa(portfolio)
        
        return {
            "credit_rwa": credit_rwa,
            "market_rwa": market_rwa,
            "operational_rwa": operational_rwa,
            "total_rwa": credit_rwa + market_rwa + operational_rwa
        }
    
    def calculate_capital_ratios(self, capital: Capital, total_rwa: float) -> CapitalRatios:
        """Calculate capital ratios given capital and RWA."""
        calculator = CapitalRatios(self.config)
        return calculator.calculate_all_ratios(capital, total_rwa)
    
    def validate_inputs(self, portfolio: Portfolio, capital: Capital) -> List[str]:
        """Validate inputs and return list of issues."""
        issues = []
        
        # Validate portfolio
        if not portfolio.exposures:
            issues.append("Portfolio has no exposures")
        
        total_exposure = portfolio.get_total_exposure()
        if total_exposure <= 0:
            issues.append("Portfolio has zero or negative total exposure")
        
        # Validate individual exposures
        for i, exposure in enumerate(portfolio.exposures):
            if exposure.current_exposure <= 0:
                issues.append(f"Exposure {i} has zero or negative amount")
            
            # Validate credit risk parameters if present
            if exposure.probability_of_default is not None:
                if not self.config.validate_exposure_data(
                    exposure.current_exposure,
                    exposure.probability_of_default,
                    exposure.loss_given_default or 0.45,  # Default LGD
                    exposure.maturity or 2.5  # Default maturity
                ):
                    issues.append(f"Exposure {i} has invalid risk parameters")
        
        # Validate capital
        capital_issues = capital.validate_capital_structure()
        issues.extend(capital_issues)
        
        return issues
    
    def run_diagnostics(self, portfolio: Portfolio, capital: Capital) -> Dict[str, Any]:
        """Run comprehensive diagnostics on inputs."""
        diagnostics = {
            "input_validation": self.validate_inputs(portfolio, capital),
            "portfolio_stats": {
                "total_exposures": len(portfolio.exposures),
                "total_amount": portfolio.get_total_exposure(),
                "concentration_metrics": portfolio.get_concentration_metrics(),
                "exposure_types": self._get_exposure_type_breakdown(portfolio),
                "rating_distribution": self._get_rating_distribution(portfolio),
            },
            "capital_stats": capital.get_capital_summary(),
            "config_summary": {
                "minimum_cet1": self.config.get_minimum_ratio("cet1_minimum"),
                "minimum_tier1": self.config.get_minimum_ratio("tier1_minimum"),
                "minimum_total": self.config.get_minimum_ratio("total_capital_minimum"),
                "conservation_buffer": self.config.get_buffer_requirement("conservation"),
            }
        }
        
        return diagnostics
    
    def _get_exposure_type_breakdown(self, portfolio: Portfolio) -> Dict[str, float]:
        """Get breakdown of exposures by type."""
        breakdown = {}
        for exposure in portfolio.exposures:
            exp_type = exposure.exposure_type.value
            breakdown[exp_type] = breakdown.get(exp_type, 0) + exposure.current_exposure
        return breakdown
    
    def _get_rating_distribution(self, portfolio: Portfolio) -> Dict[str, int]:
        """Get distribution of exposures by rating."""
        distribution = {}
        for exposure in portfolio.exposures:
            rating = exposure.external_rating or "unrated"
            distribution[rating] = distribution.get(rating, 0) + 1
        return distribution
    
    def compare_approaches(self, portfolio: Portfolio) -> Dict[str, Any]:
        """Compare different calculation approaches (SA vs IRB, etc.)."""
        # This is a placeholder for comparing different methodologies
        # In a full implementation, this would run both SA and IRB calculations
        
        sa_rwa = self.credit_calculator.calculate_standardized_rwa(portfolio)
        
        return {
            "standardized_approach": {
                "credit_rwa": sa_rwa,
                "description": "Standardized Approach for Credit Risk"
            },
            "irb_approach": {
                "credit_rwa": sa_rwa * 0.85,  # Mock IRB typically lower
                "description": "Internal Ratings-Based Approach (mock)"
            },
            "comparison": {
                "rwa_difference": sa_rwa * 0.15,
                "capital_impact": sa_rwa * 0.15 * 0.045,  # Assuming 4.5% CET1 minimum
            }
        }
