"""Provisioning engine for IFRS 9 integration."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import logging

from .ifrs9 import IFRS9Calculator, ECLResult

logger = logging.getLogger(__name__)


class ProvisionResult(BaseModel):
    """Provisioning calculation result."""
    
    total_provisions: float = Field(ge=0)
    stage_1_provisions: float = Field(ge=0)
    stage_2_provisions: float = Field(ge=0)
    stage_3_provisions: float = Field(ge=0)
    
    provision_coverage_ratio: float = Field(ge=0)
    provision_to_loans_ratio: float = Field(ge=0)


class ProvisioningEngine:
    """Engine for calculating and managing provisions."""
    
    def __init__(self, ifrs9_calculator: IFRS9Calculator):
        """Initialize provisioning engine."""
        self.ifrs9_calculator = ifrs9_calculator
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def calculate_provisions(self, ecl_results: Dict[str, ECLResult]) -> ProvisionResult:
        """Calculate total provisions from ECL results."""
        
        stage_provisions = {
            'stage_1': 0.0,
            'stage_2': 0.0, 
            'stage_3': 0.0
        }
        
        total_ead = 0.0
        
        for result in ecl_results.values():
            stage_provisions[result.stage.value] += result.ecl_amount
            total_ead += result.ead
        
        total_provisions = sum(stage_provisions.values())
        
        return ProvisionResult(
            total_provisions=total_provisions,
            stage_1_provisions=stage_provisions['stage_1'],
            stage_2_provisions=stage_provisions['stage_2'],
            stage_3_provisions=stage_provisions['stage_3'],
            provision_coverage_ratio=total_provisions / total_ead if total_ead > 0 else 0,
            provision_to_loans_ratio=total_provisions / total_ead if total_ead > 0 else 0
        )
