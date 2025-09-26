"""ICAAP processor integrating Pillar 1 and Pillar 2 capital requirements."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum
import logging
from datetime import datetime

from ..core.engine import BaselEngine
from ..core.exposure import Portfolio
from ..core.capital import Capital
from ..core.config import BaselConfig
from .pillar2 import Pillar2Calculator, Pillar2Risk

logger = logging.getLogger(__name__)


class CapitalAdequacyAssessment(str, Enum):
    """Capital adequacy assessment levels."""
    
    ADEQUATE = "adequate"
    MARGINAL = "marginal"
    INADEQUATE = "inadequate"


class ICAAResult(BaseModel):
    """ICAAP assessment result."""
    
    # Pillar 1 requirements (from Basel III)
    pillar1_total_rwa: float = Field(ge=0)
    pillar1_capital_requirement: float = Field(ge=0)
    
    # Pillar 2 additional requirements
    pillar2_risks: Dict[str, float]
    pillar2_total_add_on: float = Field(ge=0)
    
    # Total capital requirements
    total_capital_requirement: float = Field(ge=0)
    available_capital: float = Field(ge=0)
    
    # Assessment results
    capital_surplus_deficit: float  # Can be negative
    capital_adequacy_ratio: float = Field(ge=0)
    assessment_level: CapitalAdequacyAssessment
    
    # Risk appetite and limits
    risk_appetite_utilization: Dict[str, float]
    limit_breaches: List[str]
    
    # Forward-looking analysis
    capital_projections: Optional[Dict[str, float]] = None
    stress_test_impact: Optional[Dict[str, float]] = None
    
    # Metadata
    assessment_date: str
    next_review_date: str
    
    
class ICAAProcessor:
    """
    Internal Capital Adequacy Assessment Process processor.
    
    Integrates Pillar 1 (minimum requirements) with Pillar 2 (supervisory review)
    to provide comprehensive capital adequacy assessment.
    """
    
    def __init__(self, config: Optional[BaselConfig] = None):
        """Initialize ICAAP processor."""
        self.config = config or BaselConfig()
        self.basel_engine = BaselEngine(config)
        self.pillar2_calculator = Pillar2Calculator(config)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def comprehensive_assessment(self, portfolio: Portfolio, capital: Capital,
                                business_data: Dict[str, Any],
                                assessment_date: str = None) -> ICAAResult:
        """Perform comprehensive ICAAP assessment."""
        
        self.logger.info("Starting comprehensive ICAAP assessment")
        
        # Pillar 1: Basel III calculations (existing functionality)
        pillar1_results = self.basel_engine.calculate_all_metrics(portfolio, capital)
        
        # Pillar 2: Additional risk assessments
        pillar2_results = self.pillar2_calculator.calculate_pillar2_risks(
            portfolio, capital, business_data
        )
        
        # Total capital requirements
        total_requirement = (
            pillar1_results.total_rwa * 0.08 +  # 8% minimum ratio
            pillar2_results.total_add_on
        )
        
        # Capital adequacy assessment
        available_capital = capital.total_capital
        surplus_deficit = available_capital - total_requirement
        adequacy_ratio = available_capital / total_requirement if total_requirement > 0 else float('inf')
        
        # Determine assessment level
        assessment_level = self._determine_assessment_level(adequacy_ratio, surplus_deficit)
        
        # Risk appetite analysis
        risk_appetite_utilization = self._analyze_risk_appetite_utilization(
            pillar1_results, pillar2_results, business_data
        )
        
        # Identify limit breaches
        limit_breaches = self._identify_limit_breaches(
            pillar1_results, pillar2_results, risk_appetite_utilization
        )
        
        return ICAAResult(
            pillar1_total_rwa=pillar1_results.total_rwa,
            pillar1_capital_requirement=pillar1_results.total_rwa * 0.08,
            pillar2_risks=pillar2_results.risk_breakdown,
            pillar2_total_add_on=pillar2_results.total_add_on,
            total_capital_requirement=total_requirement,
            available_capital=available_capital,
            capital_surplus_deficit=surplus_deficit,
            capital_adequacy_ratio=adequacy_ratio,
            assessment_level=assessment_level,
            risk_appetite_utilization=risk_appetite_utilization,
            limit_breaches=limit_breaches,
            assessment_date=assessment_date or datetime.now().isoformat()[:10],
            next_review_date=self._calculate_next_review_date(assessment_level)
        )
    
    def _determine_assessment_level(self, adequacy_ratio: float, 
                                  surplus_deficit: float) -> CapitalAdequacyAssessment:
        """Determine capital adequacy assessment level."""
        
        # Thresholds for assessment levels
        if adequacy_ratio >= 1.25 and surplus_deficit > 0:  # 25% buffer above requirement
            return CapitalAdequacyAssessment.ADEQUATE
        elif adequacy_ratio >= 1.10 and surplus_deficit >= 0:  # 10% buffer above requirement
            return CapitalAdequacyAssessment.MARGINAL
        else:
            return CapitalAdequacyAssessment.INADEQUATE
    
    def _analyze_risk_appetite_utilization(self, pillar1_results: Any, 
                                         pillar2_results: Any,
                                         business_data: Dict[str, Any]) -> Dict[str, float]:
        """Analyze utilization against risk appetite limits."""
        
        # Default risk appetite limits (would be configured per institution)
        risk_appetite_limits = {
            'credit_risk_concentration': 0.15,  # 15% of capital
            'market_risk_var': 0.05,           # 5% of capital
            'operational_risk_events': 0.03,    # 3% of capital
            'liquidity_gap': 0.10,             # 10% of assets
            'leverage_ratio': 0.05,            # 5% above minimum
            'geographic_concentration': 0.20,   # 20% in single geography
            'sector_concentration': 0.25       # 25% in single sector
        }
        
        utilization = {}
        
        # Calculate actual utilization vs limits
        total_capital = pillar1_results.total_capital
        
        # Credit risk concentration (largest single exposure / capital)
        if hasattr(pillar1_results, 'largest_exposure'):
            utilization['credit_risk_concentration'] = (
                pillar1_results.largest_exposure / total_capital
            ) / risk_appetite_limits['credit_risk_concentration']
        
        # Market risk VaR (if available)
        market_risk_capital = getattr(pillar1_results, 'market_rwa', 0) * 0.08
        utilization['market_risk_var'] = (
            market_risk_capital / total_capital
        ) / risk_appetite_limits['market_risk_var']
        
        # Operational risk events
        operational_risk_capital = getattr(pillar1_results, 'operational_rwa', 0) * 0.08
        utilization['operational_risk_events'] = (
            operational_risk_capital / total_capital
        ) / risk_appetite_limits['operational_risk_events']
        
        # Add other risk appetite metrics as needed
        
        return utilization
    
    def _identify_limit_breaches(self, pillar1_results: Any, pillar2_results: Any,
                               risk_appetite_utilization: Dict[str, float]) -> List[str]:
        """Identify any breaches of risk limits."""
        
        breaches = []
        
        # Check risk appetite breaches (utilization > 100%)
        for risk_type, utilization in risk_appetite_utilization.items():
            if utilization > 1.0:
                breaches.append(f"Risk appetite breach: {risk_type} ({utilization:.1%})")
        
        # Check regulatory minimum breaches
        if pillar1_results.cet1_ratio < 0.045:  # 4.5% minimum
            breaches.append(f"CET1 ratio below minimum: {pillar1_results.cet1_ratio:.2%}")
        
        if pillar1_results.tier1_ratio < 0.06:  # 6% minimum
            breaches.append(f"Tier 1 ratio below minimum: {pillar1_results.tier1_ratio:.2%}")
        
        if pillar1_results.total_capital_ratio < 0.08:  # 8% minimum
            breaches.append(f"Total capital ratio below minimum: {pillar1_results.total_capital_ratio:.2%}")
        
        if hasattr(pillar1_results, 'leverage_ratio') and pillar1_results.leverage_ratio < 0.03:
            breaches.append(f"Leverage ratio below minimum: {pillar1_results.leverage_ratio:.2%}")
        
        return breaches
    
    def _calculate_next_review_date(self, assessment_level: CapitalAdequacyAssessment) -> str:
        """Calculate next review date based on assessment level."""
        
        from datetime import datetime, timedelta
        
        # Review frequency based on assessment level
        if assessment_level == CapitalAdequacyAssessment.INADEQUATE:
            months_ahead = 3  # Quarterly review
        elif assessment_level == CapitalAdequacyAssessment.MARGINAL:
            months_ahead = 6  # Semi-annual review
        else:
            months_ahead = 12  # Annual review
        
        next_review = datetime.now() + timedelta(days=months_ahead * 30)
        return next_review.isoformat()[:10]
    
    def generate_capital_plan(self, icaap_result: ICAAResult, 
                            planning_horizon_years: int = 3) -> Dict[str, Any]:
        """Generate forward-looking capital plan."""
        
        # This would integrate with business planning data
        # For now, provide a simplified projection
        
        annual_growth_rate = 0.10  # 10% annual growth assumption
        capital_generation_rate = 0.15  # 15% annual capital generation
        
        projections = {}
        current_capital = icaap_result.available_capital
        current_requirement = icaap_result.total_capital_requirement
        
        for year in range(1, planning_horizon_years + 1):
            # Project capital requirement growth
            projected_requirement = current_requirement * (1 + annual_growth_rate) ** year
            
            # Project available capital (retained earnings + new issuances)
            projected_capital = current_capital * (1 + capital_generation_rate) ** year
            
            # Calculate surplus/deficit
            surplus_deficit = projected_capital - projected_requirement
            adequacy_ratio = projected_capital / projected_requirement
            
            projections[f"year_{year}"] = {
                'projected_capital_requirement': projected_requirement,
                'projected_available_capital': projected_capital,
                'projected_surplus_deficit': surplus_deficit,
                'projected_adequacy_ratio': adequacy_ratio,
                'capital_actions_needed': surplus_deficit < 0
            }
        
        return {
            'planning_horizon_years': planning_horizon_years,
            'assumptions': {
                'business_growth_rate': annual_growth_rate,
                'capital_generation_rate': capital_generation_rate
            },
            'projections': projections,
            'recommendations': self._generate_capital_recommendations(projections)
        }
    
    def _generate_capital_recommendations(self, projections: Dict[str, Any]) -> List[str]:
        """Generate capital management recommendations."""
        
        recommendations = []
        
        # Check if any year shows capital deficit
        deficit_years = [year for year, data in projections.items() 
                        if data['capital_actions_needed']]
        
        if deficit_years:
            recommendations.append(
                f"Capital actions required in {len(deficit_years)} year(s): {', '.join(deficit_years)}"
            )
            recommendations.append("Consider: retained earnings optimization, capital issuance, or business plan adjustments")
        
        # Check if capital ratios are declining
        ratios = [data['projected_adequacy_ratio'] for data in projections.values()]
        if len(ratios) > 1 and ratios[-1] < ratios[0]:
            recommendations.append("Capital adequacy ratio trending downward - review growth strategy")
        
        # Check if excess capital exists
        min_ratio = min(ratios)
        if min_ratio > 1.5:  # 50% above requirement
            recommendations.append("Excess capital identified - consider dividend policy or growth investments")
        
        return recommendations
    
    def stress_test_capital_adequacy(self, icaap_result: ICAAResult,
                                   stress_scenarios: Dict[str, Dict]) -> Dict[str, Any]:
        """Apply stress scenarios to capital adequacy assessment."""
        
        stress_results = {}
        
        for scenario_name, scenario_params in stress_scenarios.items():
            # Apply stress to RWA
            rwa_stress = scenario_params.get('rwa_increase', 0.0)
            stressed_rwa = icaap_result.pillar1_total_rwa * (1 + rwa_stress)
            
            # Apply stress to capital (e.g., losses)
            capital_stress = scenario_params.get('capital_loss', 0.0)
            stressed_capital = icaap_result.available_capital * (1 - capital_stress)
            
            # Apply stress to Pillar 2 risks
            pillar2_stress = scenario_params.get('pillar2_increase', 0.0)
            stressed_pillar2 = icaap_result.pillar2_total_add_on * (1 + pillar2_stress)
            
            # Calculate stressed requirements and ratios
            stressed_requirement = stressed_rwa * 0.08 + stressed_pillar2
            stressed_surplus_deficit = stressed_capital - stressed_requirement
            stressed_ratio = stressed_capital / stressed_requirement if stressed_requirement > 0 else float('inf')
            
            stress_results[scenario_name] = {
                'stressed_capital': stressed_capital,
                'stressed_requirement': stressed_requirement,
                'stressed_surplus_deficit': stressed_surplus_deficit,
                'stressed_adequacy_ratio': stressed_ratio,
                'passes_stress_test': stressed_ratio >= 1.0,
                'assessment_level': self._determine_assessment_level(stressed_ratio, stressed_surplus_deficit)
            }
        
        return stress_results
