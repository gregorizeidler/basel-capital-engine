"""Pillar 2 risk calculations for ICAAP."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum
import numpy as np
import logging

from ..core.exposure import Portfolio
from ..core.capital import Capital
from ..core.config import BaselConfig

logger = logging.getLogger(__name__)


class Pillar2Risk(str, Enum):
    """Types of Pillar 2 risks."""
    
    CONCENTRATION_RISK = "concentration_risk"
    INTEREST_RATE_RISK_BANKING_BOOK = "interest_rate_risk_banking_book"
    BUSINESS_MODEL_RISK = "business_model_risk"
    REPUTATIONAL_RISK = "reputational_risk"
    STRATEGIC_RISK = "strategic_risk"
    LIQUIDITY_RISK = "liquidity_risk"
    PENSION_OBLIGATION_RISK = "pension_obligation_risk"


class Pillar2Result(BaseModel):
    """Pillar 2 calculation result."""
    
    risk_breakdown: Dict[str, float]
    total_add_on: float = Field(ge=0)
    risk_appetite_utilization: Dict[str, float]


class Pillar2Calculator:
    """Calculator for Pillar 2 additional capital requirements."""
    
    def __init__(self, config: Optional[BaselConfig] = None):
        """Initialize Pillar 2 calculator."""
        self.config = config or BaselConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def calculate_pillar2_risks(self, portfolio: Portfolio, capital: Capital,
                              business_data: Dict[str, Any]) -> Pillar2Result:
        """Calculate all Pillar 2 risks."""
        
        risk_breakdown = {}
        
        # Concentration risk
        risk_breakdown[Pillar2Risk.CONCENTRATION_RISK] = self._calculate_concentration_risk(portfolio)
        
        # Interest rate risk in banking book
        risk_breakdown[Pillar2Risk.INTEREST_RATE_RISK_BANKING_BOOK] = self._calculate_irrbb(business_data)
        
        # Business model risk
        risk_breakdown[Pillar2Risk.BUSINESS_MODEL_RISK] = self._calculate_business_model_risk(business_data)
        
        # Other risks (simplified)
        risk_breakdown[Pillar2Risk.REPUTATIONAL_RISK] = capital.total_capital * 0.01  # 1% of capital
        risk_breakdown[Pillar2Risk.STRATEGIC_RISK] = capital.total_capital * 0.005    # 0.5% of capital
        
        total_add_on = sum(risk_breakdown.values())
        
        return Pillar2Result(
            risk_breakdown=risk_breakdown,
            total_add_on=total_add_on,
            risk_appetite_utilization=self._calculate_risk_appetite_utilization(risk_breakdown, capital)
        )
    
    def _calculate_concentration_risk(self, portfolio: Portfolio) -> float:
        """Calculate concentration risk capital add-on."""
        
        # Single name concentration
        exposures_by_counterparty = {}
        for exposure in portfolio.exposures:
            counterparty = getattr(exposure, 'counterparty_id', 'unknown')
            if counterparty not in exposures_by_counterparty:
                exposures_by_counterparty[counterparty] = 0
            exposures_by_counterparty[counterparty] += exposure.current_exposure
        
        total_exposure = sum(exp.current_exposure for exp in portfolio.exposures)
        
        # Calculate Herfindahl-Hirschman Index
        if total_exposure > 0:
            concentration_weights = [exp / total_exposure for exp in exposures_by_counterparty.values()]
            hhi = sum(weight ** 2 for weight in concentration_weights)
            
            # Convert HHI to capital charge (simplified approach)
            if hhi > 0.25:  # High concentration
                concentration_add_on = total_exposure * 0.02  # 2% add-on
            elif hhi > 0.15:  # Medium concentration
                concentration_add_on = total_exposure * 0.01  # 1% add-on
            else:
                concentration_add_on = 0.0
        else:
            concentration_add_on = 0.0
        
        self.logger.debug(f"Concentration risk add-on: {concentration_add_on}")
        return concentration_add_on
    
    def _calculate_irrbb(self, business_data: Dict[str, Any]) -> float:
        """Calculate Interest Rate Risk in Banking Book."""
        
        # Simplified IRRBB calculation
        # In practice, this would use duration gap analysis
        
        total_assets = business_data.get('total_assets', 0)
        asset_duration = business_data.get('asset_duration', 3.0)  # years
        liability_duration = business_data.get('liability_duration', 1.5)  # years
        
        # Duration gap
        duration_gap = abs(asset_duration - liability_duration)
        
        # Interest rate shock (200 bps)
        ir_shock = 0.02
        
        # Economic value impact
        economic_value_impact = total_assets * duration_gap * ir_shock
        
        # Convert to capital add-on (simplified)
        irrbb_add_on = economic_value_impact * 0.1  # 10% of economic impact
        
        self.logger.debug(f"IRRBB add-on: {irrbb_add_on}")
        return max(0, irrbb_add_on)
    
    def _calculate_business_model_risk(self, business_data: Dict[str, Any]) -> float:
        """Calculate business model and strategic risk."""
        
        # Revenue concentration risk
        revenue_streams = business_data.get('revenue_breakdown', {})
        total_revenue = sum(revenue_streams.values())
        
        if total_revenue > 0:
            revenue_weights = [rev / total_revenue for rev in revenue_streams.values()]
            revenue_hhi = sum(weight ** 2 for weight in revenue_weights)
            
            # High revenue concentration increases business model risk
            if revenue_hhi > 0.5:  # Single revenue stream dominance
                business_risk_add_on = total_revenue * 0.05  # 5% of revenue
            elif revenue_hhi > 0.3:
                business_risk_add_on = total_revenue * 0.02  # 2% of revenue
            else:
                business_risk_add_on = 0.0
        else:
            business_risk_add_on = 0.0
        
        self.logger.debug(f"Business model risk add-on: {business_risk_add_on}")
        return business_risk_add_on
    
    def _calculate_risk_appetite_utilization(self, risk_breakdown: Dict[str, float],
                                           capital: Capital) -> Dict[str, float]:
        """Calculate utilization against risk appetite limits."""
        
        # Default risk appetite limits (% of total capital)
        risk_appetite_limits = {
            Pillar2Risk.CONCENTRATION_RISK: 0.15,  # 15% of capital
            Pillar2Risk.INTEREST_RATE_RISK_BANKING_BOOK: 0.10,  # 10% of capital
            Pillar2Risk.BUSINESS_MODEL_RISK: 0.08,  # 8% of capital
            Pillar2Risk.REPUTATIONAL_RISK: 0.05,   # 5% of capital
            Pillar2Risk.STRATEGIC_RISK: 0.03       # 3% of capital
        }
        
        utilization = {}
        total_capital = capital.total_capital
        
        for risk_type, risk_amount in risk_breakdown.items():
            limit = risk_appetite_limits.get(risk_type, 0.05) * total_capital
            utilization[risk_type] = risk_amount / limit if limit > 0 else 0
        
        return utilization
