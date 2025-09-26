"""Liquidity gap analysis for maturity bucket analysis."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MaturityBucket(str, Enum):
    """Maturity buckets for liquidity gap analysis."""
    
    OVERNIGHT = "overnight"
    DAYS_7 = "7_days"
    DAYS_30 = "30_days"
    DAYS_90 = "90_days"
    DAYS_180 = "180_days"
    YEAR_1 = "1_year"
    YEAR_2 = "2_years"
    YEAR_5 = "5_years"
    OVER_5_YEARS = "over_5_years"


class LiquidityGapResult(BaseModel):
    """Liquidity gap analysis result."""
    
    maturity_gaps: Dict[str, float]
    cumulative_gaps: Dict[str, float]
    gap_ratios: Dict[str, float]
    risk_assessment: Dict[str, str]
    total_assets: float
    total_liabilities: float


class LiquidityGapAnalyzer:
    """Analyzer for liquidity gap by maturity buckets."""
    
    def __init__(self):
        """Initialize gap analyzer."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def analyze_liquidity_gaps(self, assets: Dict[str, float], 
                             liabilities: Dict[str, float]) -> LiquidityGapResult:
        """Analyze liquidity gaps across maturity buckets."""
        
        maturity_gaps = {}
        cumulative_gaps = {}
        gap_ratios = {}
        risk_assessment = {}
        
        cumulative_gap = 0.0
        
        for bucket in MaturityBucket:
            asset_amount = assets.get(bucket.value, 0.0)
            liability_amount = liabilities.get(bucket.value, 0.0)
            
            gap = asset_amount - liability_amount
            cumulative_gap += gap
            
            maturity_gaps[bucket.value] = gap
            cumulative_gaps[bucket.value] = cumulative_gap
            
            # Calculate gap ratio
            if liability_amount > 0:
                gap_ratios[bucket.value] = asset_amount / liability_amount
            else:
                gap_ratios[bucket.value] = float('inf') if asset_amount > 0 else 1.0
            
            # Risk assessment
            if cumulative_gap < 0:
                if abs(cumulative_gap) > 0.1 * sum(assets.values()):  # >10% of total assets
                    risk_assessment[bucket.value] = "HIGH"
                elif abs(cumulative_gap) > 0.05 * sum(assets.values()):  # >5% of total assets
                    risk_assessment[bucket.value] = "MEDIUM"
                else:
                    risk_assessment[bucket.value] = "LOW"
            else:
                risk_assessment[bucket.value] = "LOW"
        
        return LiquidityGapResult(
            maturity_gaps=maturity_gaps,
            cumulative_gaps=cumulative_gaps,
            gap_ratios=gap_ratios,
            risk_assessment=risk_assessment,
            total_assets=sum(assets.values()),
            total_liabilities=sum(liabilities.values())
        )
