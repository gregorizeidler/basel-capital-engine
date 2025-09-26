"""SREP (Supervisory Review and Evaluation Process) generator."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SREPReport(BaseModel):
    """SREP documentation report."""
    
    reporting_date: str
    institution_code: str
    institution_name: str
    
    # SREP components
    business_model_assessment: Dict[str, Any]
    governance_risk_management: Dict[str, Any]
    capital_adequacy: Dict[str, Any]
    liquidity_funding: Dict[str, Any]
    
    overall_srep_score: float = Field(ge=1, le=4)
    supervisory_measures: List[str] = []


class SREPGenerator:
    """SREP documentation generator."""
    
    def __init__(self):
        """Initialize SREP generator."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def generate_srep_report(self, icaap_data: Dict[str, Any],
                           institution_info: Dict[str, str],
                           reporting_date: str = None) -> SREPReport:
        """Generate SREP documentation."""
        
        reporting_date = reporting_date or datetime.now().strftime("%Y-%m-%d")
        
        # Calculate SREP score (simplified)
        srep_score = self._calculate_srep_score(icaap_data)
        
        return SREPReport(
            reporting_date=reporting_date,
            institution_code=institution_info.get("institution_code", "UNKNOWN"),
            institution_name=institution_info.get("institution_name", "Unknown Institution"),
            business_model_assessment={"score": 2.0, "assessment": "Satisfactory"},
            governance_risk_management={"score": 2.0, "assessment": "Satisfactory"},
            capital_adequacy=icaap_data.get('capital_assessment', {}),
            liquidity_funding=icaap_data.get('liquidity_assessment', {}),
            overall_srep_score=srep_score,
            supervisory_measures=self._determine_supervisory_measures(srep_score)
        )
    
    def _calculate_srep_score(self, icaap_data: Dict[str, Any]) -> float:
        """Calculate overall SREP score (1=low risk, 4=high risk)."""
        
        # Simplified SREP scoring
        capital_score = 2.0  # Default satisfactory
        if icaap_data.get('capital_adequacy_ratio', 1.0) < 1.0:
            capital_score = 3.0  # Weak
        elif icaap_data.get('capital_adequacy_ratio', 1.0) > 1.5:
            capital_score = 1.0  # Strong
        
        return capital_score
    
    def _determine_supervisory_measures(self, srep_score: float) -> List[str]:
        """Determine required supervisory measures."""
        
        measures = []
        
        if srep_score >= 3.0:
            measures.extend([
                "Enhanced monitoring required",
                "Capital action plan needed",
                "Quarterly reporting"
            ])
        elif srep_score >= 2.5:
            measures.append("Increased supervisory attention")
        
        return measures
