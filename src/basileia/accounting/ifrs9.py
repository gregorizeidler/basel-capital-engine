"""IFRS 9 Expected Credit Loss calculations integrated with Basel III framework."""

from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import logging

from ..core.exposure import Portfolio, Exposure
from ..core.config import BaselConfig

logger = logging.getLogger(__name__)


class ECLStage(str, Enum):
    """IFRS 9 ECL staging classification."""
    
    STAGE_1 = "stage_1"  # 12-month ECL
    STAGE_2 = "stage_2"  # Lifetime ECL (not credit-impaired)
    STAGE_3 = "stage_3"  # Lifetime ECL (credit-impaired)


class ECLResult(BaseModel):
    """Expected Credit Loss calculation result."""
    
    exposure_id: str
    stage: ECLStage
    ecl_amount: float = Field(ge=0, description="Expected Credit Loss amount")
    ead: float = Field(ge=0, description="Exposure at Default")
    pd_12m: Optional[float] = Field(None, ge=0, le=1, description="12-month PD")
    pd_lifetime: Optional[float] = Field(None, ge=0, le=1, description="Lifetime PD")
    lgd: float = Field(ge=0, le=1, description="Loss Given Default")
    
    # Stage determination factors
    significant_increase_risk: bool = False
    credit_impaired: bool = False
    days_past_due: int = Field(default=0, ge=0)
    
    # Additional metrics
    coverage_ratio: float = Field(description="ECL / EAD ratio")
    
    def __post_init__(self):
        """Calculate derived metrics."""
        if self.ead > 0:
            self.coverage_ratio = self.ecl_amount / self.ead
        else:
            self.coverage_ratio = 0.0


class IFRS9Calculator:
    """
    IFRS 9 Expected Credit Loss calculator integrated with Basel III.
    
    Calculates provisions using the same PD/LGD/EAD parameters as Basel calculations
    for consistency and efficiency.
    """
    
    def __init__(self, config: Optional[BaselConfig] = None):
        """Initialize IFRS 9 calculator."""
        self.config = config or BaselConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def calculate_portfolio_ecl(self, portfolio: Portfolio) -> Dict[str, ECLResult]:
        """Calculate ECL for entire portfolio."""
        self.logger.info(f"Calculating IFRS 9 ECL for portfolio with {len(portfolio.exposures)} exposures")
        
        results = {}
        for exposure in portfolio.exposures:
            ecl_result = self.calculate_exposure_ecl(exposure)
            results[exposure.exposure_id] = ecl_result
        
        return results
    
    def calculate_exposure_ecl(self, exposure: Exposure) -> ECLResult:
        """Calculate ECL for individual exposure."""
        
        # Determine IFRS 9 stage
        stage = self._determine_stage(exposure)
        
        # Calculate ECL based on stage
        if stage == ECLStage.STAGE_1:
            ecl_amount = self._calculate_stage_1_ecl(exposure)
            pd_used = exposure.probability_of_default  # 12-month PD
        elif stage == ECLStage.STAGE_2:
            ecl_amount = self._calculate_stage_2_ecl(exposure)
            pd_used = self._calculate_lifetime_pd(exposure)
        else:  # Stage 3
            ecl_amount = self._calculate_stage_3_ecl(exposure)
            pd_used = 1.0  # Already defaulted
        
        return ECLResult(
            exposure_id=exposure.exposure_id,
            stage=stage,
            ecl_amount=ecl_amount,
            ead=exposure.current_exposure,
            pd_12m=exposure.probability_of_default,
            pd_lifetime=pd_used if stage != ECLStage.STAGE_1 else None,
            lgd=exposure.loss_given_default or 0.45,  # Default LGD if not specified
            significant_increase_risk=self._has_significant_increase_risk(exposure),
            credit_impaired=self._is_credit_impaired(exposure),
            days_past_due=getattr(exposure, 'days_past_due', 0)
        )
    
    def _determine_stage(self, exposure: Exposure) -> ECLStage:
        """Determine IFRS 9 stage for exposure."""
        
        # Stage 3: Credit-impaired (defaulted)
        if self._is_credit_impaired(exposure):
            return ECLStage.STAGE_3
        
        # Stage 2: Significant increase in credit risk
        if self._has_significant_increase_risk(exposure):
            return ECLStage.STAGE_2
        
        # Stage 1: Performing (no significant increase in risk)
        return ECLStage.STAGE_1
    
    def _is_credit_impaired(self, exposure: Exposure) -> bool:
        """Check if exposure is credit-impaired (Stage 3)."""
        
        # Check days past due (>90 days typically indicates default)
        days_past_due = getattr(exposure, 'days_past_due', 0)
        if days_past_due > 90:
            return True
        
        # Check if explicitly marked as defaulted
        if hasattr(exposure, 'defaulted') and exposure.defaulted:
            return True
        
        # Check PD threshold (very high PD indicates near-certain default)
        if exposure.probability_of_default and exposure.probability_of_default > 0.95:
            return True
        
        return False
    
    def _has_significant_increase_risk(self, exposure: Exposure) -> bool:
        """Check if there's significant increase in credit risk (Stage 2)."""
        
        # 30+ days past due (rebuttable presumption)
        days_past_due = getattr(exposure, 'days_past_due', 0)
        if days_past_due >= 30:
            return True
        
        # Compare current PD with origination PD
        if hasattr(exposure, 'origination_pd') and exposure.origination_pd:
            current_pd = exposure.probability_of_default or 0
            origination_pd = exposure.origination_pd
            
            # Relative threshold (e.g., PD doubled)
            if current_pd > 2.0 * origination_pd:
                return True
            
            # Absolute threshold for low-risk exposures
            if origination_pd < 0.01 and current_pd > 0.005:
                return True
        
        # Rating downgrade (if available)
        if hasattr(exposure, 'rating_downgrade_notches'):
            if exposure.rating_downgrade_notches >= 3:  # 3+ notches downgrade
                return True
        
        return False
    
    def _calculate_stage_1_ecl(self, exposure: Exposure) -> float:
        """Calculate 12-month ECL (Stage 1)."""
        ead = exposure.current_exposure
        pd_12m = exposure.probability_of_default or 0.01  # Default 1% if not specified
        lgd = exposure.loss_given_default or 0.45
        
        # 12-month ECL = EAD × PD(12m) × LGD
        ecl = ead * pd_12m * lgd
        
        self.logger.debug(f"Stage 1 ECL for {exposure.exposure_id}: {ecl:.2f} "
                         f"(EAD: {ead:.2f}, PD: {pd_12m:.4f}, LGD: {lgd:.4f})")
        
        return ecl
    
    def _calculate_stage_2_ecl(self, exposure: Exposure) -> float:
        """Calculate lifetime ECL (Stage 2)."""
        ead = exposure.current_exposure
        pd_lifetime = self._calculate_lifetime_pd(exposure)
        lgd = exposure.loss_given_default or 0.45
        
        # Lifetime ECL = EAD × PD(Lifetime) × LGD
        ecl = ead * pd_lifetime * lgd
        
        self.logger.debug(f"Stage 2 ECL for {exposure.exposure_id}: {ecl:.2f} "
                         f"(EAD: {ead:.2f}, PD_LT: {pd_lifetime:.4f}, LGD: {lgd:.4f})")
        
        return ecl
    
    def _calculate_stage_3_ecl(self, exposure: Exposure) -> float:
        """Calculate lifetime ECL for credit-impaired exposures (Stage 3)."""
        ead = exposure.current_exposure
        lgd = exposure.loss_given_default or 0.45
        
        # For defaulted exposures, PD = 1.0
        # May need to consider partial recovery expectations
        recovery_rate = getattr(exposure, 'expected_recovery_rate', 1 - lgd)
        
        ecl = ead * (1 - recovery_rate)
        
        self.logger.debug(f"Stage 3 ECL for {exposure.exposure_id}: {ecl:.2f} "
                         f"(EAD: {ead:.2f}, Recovery: {recovery_rate:.4f})")
        
        return ecl
    
    def _calculate_lifetime_pd(self, exposure: Exposure) -> float:
        """Calculate lifetime PD from 12-month PD."""
        pd_12m = exposure.probability_of_default or 0.01
        maturity = exposure.maturity or 5.0  # Default 5 years if not specified
        
        # Simple approximation: Lifetime PD ≈ 1 - (1 - PD_12m)^maturity
        # This assumes constant hazard rate
        lifetime_pd = 1 - (1 - pd_12m) ** maturity
        
        # Cap at reasonable maximum
        return min(lifetime_pd, 0.99)
    
    def calculate_ecl_summary(self, portfolio: Portfolio) -> Dict[str, Any]:
        """Calculate portfolio-level ECL summary."""
        ecl_results = self.calculate_portfolio_ecl(portfolio)
        
        # Aggregate by stage
        stage_summary = {
            ECLStage.STAGE_1: {'count': 0, 'ead': 0, 'ecl': 0},
            ECLStage.STAGE_2: {'count': 0, 'ead': 0, 'ecl': 0},
            ECLStage.STAGE_3: {'count': 0, 'ead': 0, 'ecl': 0}
        }
        
        for result in ecl_results.values():
            stage_summary[result.stage]['count'] += 1
            stage_summary[result.stage]['ead'] += result.ead
            stage_summary[result.stage]['ecl'] += result.ecl_amount
        
        # Calculate coverage ratios
        total_ead = sum(s['ead'] for s in stage_summary.values())
        total_ecl = sum(s['ecl'] for s in stage_summary.values())
        overall_coverage = total_ecl / total_ead if total_ead > 0 else 0
        
        return {
            'total_exposures': len(ecl_results),
            'total_ead': total_ead,
            'total_ecl': total_ecl,
            'overall_coverage_ratio': overall_coverage,
            'stage_breakdown': {
                stage.value: {
                    'count': data['count'],
                    'ead': data['ead'],
                    'ecl': data['ecl'],
                    'coverage_ratio': data['ecl'] / data['ead'] if data['ead'] > 0 else 0,
                    'percentage_of_portfolio': data['ead'] / total_ead if total_ead > 0 else 0
                }
                for stage, data in stage_summary.items()
            }
        }
    
    def generate_stage_transition_matrix(self, historical_data: List[Dict]) -> np.ndarray:
        """Generate transition matrix for stage migrations (for model validation)."""
        # This would be implemented with historical portfolio data
        # For now, return a simple example matrix
        
        # Transition probabilities [Stage1->Stage1, Stage1->Stage2, Stage1->Stage3, ...]
        transition_matrix = np.array([
            [0.95, 0.04, 0.01],  # From Stage 1
            [0.20, 0.70, 0.10],  # From Stage 2  
            [0.05, 0.15, 0.80]   # From Stage 3
        ])
        
        return transition_matrix
    
    def validate_ecl_model(self, historical_results: List[ECLResult], 
                          actual_losses: List[float]) -> Dict[str, float]:
        """Validate ECL model performance against actual losses."""
        
        if len(historical_results) != len(actual_losses):
            raise ValueError("Historical results and actual losses must have same length")
        
        predicted_ecl = [r.ecl_amount for r in historical_results]
        
        # Calculate validation metrics
        mae = np.mean(np.abs(np.array(predicted_ecl) - np.array(actual_losses)))
        mse = np.mean((np.array(predicted_ecl) - np.array(actual_losses)) ** 2)
        rmse = np.sqrt(mse)
        
        # Coverage ratio (predicted vs actual)
        total_predicted = sum(predicted_ecl)
        total_actual = sum(actual_losses)
        coverage_ratio = total_predicted / total_actual if total_actual > 0 else float('inf')
        
        return {
            'mean_absolute_error': mae,
            'mean_squared_error': mse,
            'root_mean_squared_error': rmse,
            'coverage_ratio': coverage_ratio,
            'total_predicted_ecl': total_predicted,
            'total_actual_losses': total_actual
        }
