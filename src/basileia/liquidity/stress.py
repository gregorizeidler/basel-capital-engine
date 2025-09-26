"""Liquidity stress testing engine."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel
import logging

from .lcr import LCRCalculator, LCRResult
from .nsfr import NSFRCalculator, NSFRResult

logger = logging.getLogger(__name__)


class LiquidityStressEngine:
    """Engine for liquidity stress testing."""
    
    def __init__(self):
        """Initialize stress engine."""
        self.lcr_calculator = LCRCalculator()
        self.nsfr_calculator = NSFRCalculator()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def run_liquidity_stress_test(self, base_lcr: LCRResult, base_nsfr: NSFRResult,
                                 stress_scenarios: Dict[str, Dict]) -> Dict[str, Any]:
        """Run comprehensive liquidity stress test."""
        
        results = {}
        
        # LCR stress testing
        lcr_stress_results = self.lcr_calculator.stress_test_lcr(base_lcr, stress_scenarios)
        
        # NSFR stress testing  
        nsfr_stress_results = self.nsfr_calculator.stress_test_nsfr(base_nsfr, stress_scenarios)
        
        for scenario_name in stress_scenarios.keys():
            results[scenario_name] = {
                'lcr_result': lcr_stress_results[scenario_name],
                'nsfr_result': nsfr_stress_results[scenario_name],
                'overall_assessment': self._assess_liquidity_position(
                    lcr_stress_results[scenario_name],
                    nsfr_stress_results[scenario_name]
                )
            }
        
        return results
    
    def _assess_liquidity_position(self, lcr_result: LCRResult, nsfr_result: NSFRResult) -> str:
        """Assess overall liquidity position."""
        
        if lcr_result.compliant and nsfr_result.compliant:
            return "STRONG"
        elif lcr_result.lcr_ratio >= 0.9 and nsfr_result.nsfr_ratio >= 0.9:
            return "ADEQUATE"
        else:
            return "WEAK"
