"""Liquidity Coverage Ratio (LCR) calculation for Basel III liquidity framework."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum
import logging

from ..core.config import BaselConfig

logger = logging.getLogger(__name__)


class HQLACategory(str, Enum):
    """High Quality Liquid Assets categories."""
    
    LEVEL_1 = "level_1"      # 0% haircut (cash, central bank reserves, sovereign bonds)
    LEVEL_2A = "level_2a"    # 15% haircut (sovereign, PSE, corporate bonds)
    LEVEL_2B = "level_2b"    # 25-50% haircut (lower-rated corporate bonds, equities)


class LiquidAsset(BaseModel):
    """Individual liquid asset for HQLA calculation."""
    
    asset_id: str
    asset_type: str
    market_value: float = Field(gt=0)
    hqla_category: HQLACategory
    haircut_rate: float = Field(ge=0, le=1)
    encumbered: bool = False
    central_bank_eligible: bool = False


class CashFlowItem(BaseModel):
    """Cash flow item for LCR calculation."""
    
    item_id: str
    item_type: str  # 'inflow' or 'outflow'
    counterparty_type: str
    amount: float = Field(gt=0)
    runoff_rate: float = Field(ge=0, le=1)
    maturity_days: int = Field(ge=0, le=30)  # Within 30 days
    secured: bool = False
    operational: bool = False


class LCRResult(BaseModel):
    """LCR calculation result."""
    
    # HQLA components
    total_hqla: float = Field(ge=0)
    level_1_hqla: float = Field(ge=0)
    level_2a_hqla: float = Field(ge=0) 
    level_2b_hqla: float = Field(ge=0)
    
    # Cash flow components
    total_outflows: float = Field(ge=0)
    total_inflows: float = Field(ge=0)
    net_cash_outflows: float = Field(ge=0)
    
    # Final ratio
    lcr_ratio: float = Field(ge=0)
    compliant: bool
    
    # Detailed breakdowns
    hqla_breakdown: Dict[str, float]
    outflow_breakdown: Dict[str, float]
    inflow_breakdown: Dict[str, float]
    
    calculation_date: str


class LCRCalculator:
    """
    Liquidity Coverage Ratio calculator following Basel III liquidity standards.
    
    LCR = High Quality Liquid Assets / Net Cash Outflows (30 days) ≥ 100%
    """
    
    def __init__(self, config: Optional[BaselConfig] = None):
        """Initialize LCR calculator."""
        self.config = config or BaselConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Default runoff rates from Basel III
        self.default_runoff_rates = {
            'retail_deposits_stable': 0.05,
            'retail_deposits_less_stable': 0.10,
            'small_business_deposits_stable': 0.05,
            'small_business_deposits_less_stable': 0.10,
            'operational_deposits': 0.25,
            'non_operational_deposits': 1.00,
            'unsecured_wholesale': 1.00,
            'secured_funding': 0.00,
            'additional_requirements': 1.00,
            'credit_facilities': 0.10,
            'liquidity_facilities': 1.00
        }
        
        # HQLA haircuts
        self.hqla_haircuts = {
            HQLACategory.LEVEL_1: 0.00,
            HQLACategory.LEVEL_2A: 0.15,
            HQLACategory.LEVEL_2B: 0.25  # Can be up to 0.50 for some assets
        }
    
    def calculate_lcr(self, liquid_assets: List[LiquidAsset], 
                      cash_flows: List[CashFlowItem],
                      calculation_date: str = None) -> LCRResult:
        """Calculate LCR for given assets and cash flows."""
        
        self.logger.info("Calculating LCR")
        
        # Calculate HQLA
        hqla_result = self._calculate_hqla(liquid_assets)
        
        # Calculate cash outflows and inflows
        outflows = self._calculate_cash_outflows(cash_flows)
        inflows = self._calculate_cash_inflows(cash_flows)
        
        # Net cash outflows (inflows capped at 75% of outflows)
        capped_inflows = min(inflows['total'], 0.75 * outflows['total'])
        net_outflows = max(outflows['total'] - capped_inflows, 
                          0.25 * outflows['total'])  # Minimum 25% of gross outflows
        
        # Calculate LCR
        lcr_ratio = hqla_result['total'] / net_outflows if net_outflows > 0 else float('inf')
        compliant = lcr_ratio >= 1.00
        
        return LCRResult(
            total_hqla=hqla_result['total'],
            level_1_hqla=hqla_result['level_1'],
            level_2a_hqla=hqla_result['level_2a'],
            level_2b_hqla=hqla_result['level_2b'],
            total_outflows=outflows['total'],
            total_inflows=inflows['total'],
            net_cash_outflows=net_outflows,
            lcr_ratio=lcr_ratio,
            compliant=compliant,
            hqla_breakdown=hqla_result,
            outflow_breakdown=outflows,
            inflow_breakdown=inflows,
            calculation_date=calculation_date or "2024-01-01"
        )
    
    def _calculate_hqla(self, assets: List[LiquidAsset]) -> Dict[str, float]:
        """Calculate High Quality Liquid Assets."""
        
        hqla_breakdown = {
            'level_1': 0.0,
            'level_2a': 0.0,
            'level_2b': 0.0,
            'total': 0.0
        }
        
        level_2_total = 0.0
        
        for asset in assets:
            if asset.encumbered:
                continue  # Skip encumbered assets
            
            # Apply haircut
            haircut = self.hqla_haircuts.get(asset.hqla_category, 0.0)
            hqla_value = asset.market_value * (1 - haircut)
            
            if asset.hqla_category == HQLACategory.LEVEL_1:
                hqla_breakdown['level_1'] += hqla_value
            elif asset.hqla_category == HQLACategory.LEVEL_2A:
                hqla_breakdown['level_2a'] += hqla_value
                level_2_total += hqla_value
            elif asset.hqla_category == HQLACategory.LEVEL_2B:
                hqla_breakdown['level_2b'] += hqla_value
                level_2_total += hqla_value
        
        # Apply Level 2 caps
        # Level 2 assets cannot exceed 40% of total HQLA
        total_before_caps = hqla_breakdown['level_1'] + level_2_total
        max_level_2 = total_before_caps * 0.40 / 0.60  # Solve for max Level 2
        
        if level_2_total > max_level_2:
            # Scale down Level 2 assets proportionally
            scale_factor = max_level_2 / level_2_total
            hqla_breakdown['level_2a'] *= scale_factor
            hqla_breakdown['level_2b'] *= scale_factor
            level_2_total = max_level_2
        
        # Level 2B cannot exceed 15% of total HQLA (i.e., 37.5% of Level 2)
        max_level_2b = (hqla_breakdown['level_1'] + level_2_total) * 0.15
        if hqla_breakdown['level_2b'] > max_level_2b:
            excess_2b = hqla_breakdown['level_2b'] - max_level_2b
            hqla_breakdown['level_2b'] = max_level_2b
            # Remove excess from total
            level_2_total -= excess_2b
        
        hqla_breakdown['total'] = hqla_breakdown['level_1'] + level_2_total
        
        self.logger.debug(f"HQLA calculated: {hqla_breakdown}")
        return hqla_breakdown
    
    def _calculate_cash_outflows(self, cash_flows: List[CashFlowItem]) -> Dict[str, float]:
        """Calculate 30-day cash outflows."""
        
        outflow_breakdown = {
            'retail_deposits': 0.0,
            'small_business_deposits': 0.0,
            'operational_deposits': 0.0,
            'non_operational_deposits': 0.0,
            'unsecured_wholesale': 0.0,
            'secured_funding': 0.0,
            'additional_requirements': 0.0,
            'credit_facilities': 0.0,
            'liquidity_facilities': 0.0,
            'other': 0.0,
            'total': 0.0
        }
        
        for flow in cash_flows:
            if flow.item_type != 'outflow':
                continue
            
            # Apply runoff rate
            runoff_rate = flow.runoff_rate or self._get_default_runoff_rate(flow)
            outflow_amount = flow.amount * runoff_rate
            
            # Categorize outflow
            category = self._categorize_outflow(flow)
            if category in outflow_breakdown:
                outflow_breakdown[category] += outflow_amount
            else:
                outflow_breakdown['other'] += outflow_amount
        
        outflow_breakdown['total'] = sum(outflow_breakdown.values()) - outflow_breakdown['total']
        
        self.logger.debug(f"Cash outflows calculated: {outflow_breakdown}")
        return outflow_breakdown
    
    def _calculate_cash_inflows(self, cash_flows: List[CashFlowItem]) -> Dict[str, float]:
        """Calculate 30-day cash inflows."""
        
        inflow_breakdown = {
            'secured_lending': 0.0,
            'unsecured_lending': 0.0,
            'operational_inflows': 0.0,
            'other': 0.0,
            'total': 0.0
        }
        
        for flow in cash_flows:
            if flow.item_type != 'inflow':
                continue
            
            # Inflows generally taken at 100% unless specified otherwise
            inflow_rate = 1.0 - (flow.runoff_rate or 0.0)  # Runoff rate for inflows means non-performance
            inflow_amount = flow.amount * inflow_rate
            
            # Categorize inflow
            category = self._categorize_inflow(flow)
            if category in inflow_breakdown:
                inflow_breakdown[category] += inflow_amount
            else:
                inflow_breakdown['other'] += inflow_amount
        
        inflow_breakdown['total'] = sum(inflow_breakdown.values()) - inflow_breakdown['total']
        
        self.logger.debug(f"Cash inflows calculated: {inflow_breakdown}")
        return inflow_breakdown
    
    def _get_default_runoff_rate(self, flow: CashFlowItem) -> float:
        """Get default runoff rate based on counterparty type."""
        
        # Map counterparty types to runoff rates
        runoff_mapping = {
            'retail_stable': 0.05,
            'retail_less_stable': 0.10,
            'small_business_stable': 0.05,
            'small_business_less_stable': 0.10,
            'operational': 0.25,
            'non_operational': 1.00,
            'wholesale_unsecured': 1.00,
            'wholesale_secured': 0.00
        }
        
        return runoff_mapping.get(flow.counterparty_type, 1.00)  # Default to 100%
    
    def _categorize_outflow(self, flow: CashFlowItem) -> str:
        """Categorize cash outflow for reporting."""
        
        if 'retail' in flow.counterparty_type.lower():
            return 'retail_deposits'
        elif 'small_business' in flow.counterparty_type.lower():
            return 'small_business_deposits'
        elif flow.operational:
            return 'operational_deposits'
        elif 'wholesale' in flow.counterparty_type.lower():
            if flow.secured:
                return 'secured_funding'
            else:
                return 'unsecured_wholesale'
        elif 'credit_facility' in flow.item_type.lower():
            return 'credit_facilities'
        elif 'liquidity_facility' in flow.item_type.lower():
            return 'liquidity_facilities'
        else:
            return 'other'
    
    def _categorize_inflow(self, flow: CashFlowItem) -> str:
        """Categorize cash inflow for reporting."""
        
        if flow.secured:
            return 'secured_lending'
        elif flow.operational:
            return 'operational_inflows'
        else:
            return 'unsecured_lending'
    
    def stress_test_lcr(self, base_result: LCRResult, stress_scenarios: Dict[str, Dict]) -> Dict[str, LCRResult]:
        """Apply stress scenarios to LCR calculation."""
        
        stress_results = {}
        
        for scenario_name, scenario_params in stress_scenarios.items():
            # Apply stress to HQLA (market value decline)
            hqla_stress = scenario_params.get('hqla_decline', 0.0)
            stressed_hqla = base_result.total_hqla * (1 - hqla_stress)
            
            # Apply stress to outflows (increased runoff rates)
            outflow_stress = scenario_params.get('outflow_increase', 0.0)
            stressed_outflows = base_result.total_outflows * (1 + outflow_stress)
            
            # Apply stress to inflows (reduced inflows)
            inflow_stress = scenario_params.get('inflow_decrease', 0.0)
            stressed_inflows = base_result.total_inflows * (1 - inflow_stress)
            
            # Recalculate net outflows
            capped_inflows = min(stressed_inflows, 0.75 * stressed_outflows)
            net_outflows = max(stressed_outflows - capped_inflows, 
                             0.25 * stressed_outflows)
            
            # Calculate stressed LCR
            stressed_lcr = stressed_hqla / net_outflows if net_outflows > 0 else float('inf')
            
            # Create stressed result
            stressed_result = base_result.model_copy()
            stressed_result.total_hqla = stressed_hqla
            stressed_result.total_outflows = stressed_outflows
            stressed_result.total_inflows = stressed_inflows
            stressed_result.net_cash_outflows = net_outflows
            stressed_result.lcr_ratio = stressed_lcr
            stressed_result.compliant = stressed_lcr >= 1.00
            
            stress_results[scenario_name] = stressed_result
        
        return stress_results
