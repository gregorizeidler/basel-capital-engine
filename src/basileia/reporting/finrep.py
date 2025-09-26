"""FINREP (Financial Reporting) generator for European banking supervision."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FINREPTable(BaseModel):
    """Base class for FINREP tables."""
    
    table_code: str
    table_name: str
    reporting_date: str
    institution_code: str
    data: Dict[str, Any]


class FINREPReport(BaseModel):
    """Complete FINREP report."""
    
    reporting_date: str
    institution_code: str
    institution_name: str
    
    # Main FINREP tables
    f_01_01_balance_sheet: Optional[FINREPTable] = None
    f_02_00_profit_loss: Optional[FINREPTable] = None
    
    validation_status: str = "Draft"
    validation_errors: List[str] = []


class FINREPGenerator:
    """FINREP report generator."""
    
    def __init__(self):
        """Initialize FINREP generator."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def generate_finrep_report(self, financial_data: Dict[str, Any],
                              institution_info: Dict[str, str],
                              reporting_date: str = None) -> FINREPReport:
        """Generate FINREP report."""
        
        reporting_date = reporting_date or datetime.now().strftime("%Y-%m-%d")
        
        report = FINREPReport(
            reporting_date=reporting_date,
            institution_code=institution_info.get("institution_code", "UNKNOWN"),
            institution_name=institution_info.get("institution_name", "Unknown Institution")
        )
        
        # Generate balance sheet table
        report.f_01_01_balance_sheet = self._generate_balance_sheet(
            financial_data, reporting_date, report.institution_code
        )
        
        return report
    
    def _generate_balance_sheet(self, financial_data: Dict[str, Any],
                               reporting_date: str, institution_code: str) -> FINREPTable:
        """Generate F 01.01 - Balance sheet table."""
        
        data = {
            "010": financial_data.get('cash_balances', 0),
            "020": financial_data.get('loans_advances', 0),
            "030": financial_data.get('debt_securities', 0),
            "040": financial_data.get('total_assets', 0),
            "050": financial_data.get('deposits', 0),
            "060": financial_data.get('debt_issued', 0),
            "070": financial_data.get('total_liabilities', 0),
            "080": financial_data.get('total_equity', 0),
        }
        
        return FINREPTable(
            table_code="F 01.01",
            table_name="Balance sheet",
            reporting_date=reporting_date,
            institution_code=institution_code,
            data=data
        )
