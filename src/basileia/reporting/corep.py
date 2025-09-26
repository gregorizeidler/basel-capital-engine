"""COREP (Common Reporting) generator for European banking supervision."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from ..core.engine import BaselEngine
from ..core.exposure import Portfolio
from ..core.capital import Capital

logger = logging.getLogger(__name__)


class COREPTable(BaseModel):
    """Base class for COREP tables."""
    
    table_code: str
    table_name: str
    reporting_date: str
    institution_code: str
    data: Dict[str, Any]


class COREPReport(BaseModel):
    """Complete COREP report."""
    
    reporting_date: str
    institution_code: str
    institution_name: str
    consolidation_level: str = "Individual"  # Individual, Subconsolidated, Consolidated
    
    # Main COREP tables
    c_01_00_own_funds: Optional[COREPTable] = None
    c_02_00_own_funds_requirements: Optional[COREPTable] = None
    c_03_00_forbearance_npe: Optional[COREPTable] = None
    c_04_00_market_risk: Optional[COREPTable] = None
    c_05_00_credit_risk_sa: Optional[COREPTable] = None
    c_06_00_credit_risk_irb: Optional[COREPTable] = None
    c_07_00_operational_risk: Optional[COREPTable] = None
    c_08_00_large_exposures: Optional[COREPTable] = None
    c_09_00_leverage_ratio: Optional[COREPTable] = None
    
    # Validation status
    validation_status: str = "Draft"
    validation_errors: List[str] = []


class COREPGenerator:
    """
    COREP report generator for European banking supervision.
    
    Generates standardized regulatory reports based on Basel III calculations
    and additional supervisory requirements.
    """
    
    def __init__(self, basel_engine: BaselEngine):
        """Initialize COREP generator."""
        self.basel_engine = basel_engine
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def generate_corep_report(self, portfolio: Portfolio, capital: Capital,
                            institution_info: Dict[str, str],
                            reporting_date: str = None) -> COREPReport:
        """Generate complete COREP report."""
        
        self.logger.info("Generating COREP report")
        
        # Calculate Basel metrics
        basel_results = self.basel_engine.calculate_all_metrics(portfolio, capital)
        
        reporting_date = reporting_date or datetime.now().strftime("%Y-%m-%d")
        
        # Generate individual tables
        report = COREPReport(
            reporting_date=reporting_date,
            institution_code=institution_info.get("institution_code", "UNKNOWN"),
            institution_name=institution_info.get("institution_name", "Unknown Institution")
        )
        
        # C 01.00 - Own Funds
        report.c_01_00_own_funds = self._generate_c_01_00_own_funds(
            capital, basel_results, reporting_date, report.institution_code
        )
        
        # C 02.00 - Own Funds Requirements
        report.c_02_00_own_funds_requirements = self._generate_c_02_00_requirements(
            basel_results, reporting_date, report.institution_code
        )
        
        # C 03.00 - Forbearance and Non-performing exposures
        report.c_03_00_forbearance_npe = self._generate_c_03_00_forbearance(
            portfolio, reporting_date, report.institution_code
        )
        
        # C 07.00 - Operational Risk
        report.c_07_00_operational_risk = self._generate_c_07_00_operational(
            basel_results, reporting_date, report.institution_code
        )
        
        # C 09.00 - Leverage Ratio
        report.c_09_00_leverage_ratio = self._generate_c_09_00_leverage(
            basel_results, reporting_date, report.institution_code
        )
        
        return report
    
    def _generate_c_01_00_own_funds(self, capital: Capital, basel_results: Any,
                                  reporting_date: str, institution_code: str) -> COREPTable:
        """Generate C 01.00 - Own Funds table."""
        
        # Map capital components to COREP line items
        data = {
            # Common Equity Tier 1 capital: instruments and reserves
            "010": capital.common_shares,  # Capital instruments and related share premium accounts
            "020": capital.retained_earnings,  # Retained earnings
            "030": capital.accumulated_oci,  # Accumulated other comprehensive income
            "040": capital.minority_interests,  # Common Equity Tier 1 capital issued by subsidiaries
            
            # Common Equity Tier 1 capital: regulatory adjustments
            "050": capital.goodwill,  # Goodwill
            "060": capital.intangible_assets,  # Other intangible assets
            "070": capital.deferred_tax_assets,  # Deferred tax assets
            "080": capital.cash_flow_hedge_reserve,  # Cash-flow hedge reserve
            "090": capital.shortfall_provisions,  # Shortfall of provisions to expected losses
            "100": capital.investments_in_own_shares,  # Direct and indirect holdings of own instruments
            
            # Additional Tier 1 capital
            "110": capital.at1_instruments,  # Additional Tier 1 instruments
            
            # Tier 2 capital
            "120": capital.t2_instruments,  # Tier 2 instruments
            "130": capital.general_provisions,  # General provisions
            
            # Total capital ratios
            "140": basel_results.cet1_capital,  # Common Equity Tier 1 capital
            "150": basel_results.tier1_capital,  # Tier 1 capital
            "160": basel_results.total_capital,  # Total capital
            "170": basel_results.total_rwa,  # Total risk-weighted assets
            
            # Capital ratios
            "180": basel_results.cet1_ratio,  # Common Equity Tier 1 ratio
            "190": basel_results.tier1_ratio,  # Tier 1 ratio
            "200": basel_results.total_capital_ratio,  # Total capital ratio
        }
        
        return COREPTable(
            table_code="C 01.00",
            table_name="Own funds",
            reporting_date=reporting_date,
            institution_code=institution_code,
            data=data
        )
    
    def _generate_c_02_00_requirements(self, basel_results: Any,
                                     reporting_date: str, institution_code: str) -> COREPTable:
        """Generate C 02.00 - Own funds requirements table."""
        
        data = {
            # Credit risk
            "010": basel_results.credit_rwa,  # Credit risk RWA
            "020": basel_results.credit_rwa * 0.08,  # Credit risk capital requirement
            
            # Market risk
            "030": basel_results.market_rwa,  # Market risk RWA
            "040": basel_results.market_rwa * 0.08,  # Market risk capital requirement
            
            # Operational risk
            "050": basel_results.operational_rwa,  # Operational risk RWA
            "060": basel_results.operational_rwa * 0.08,  # Operational risk capital requirement
            
            # Total
            "070": basel_results.total_rwa,  # Total RWA
            "080": basel_results.total_rwa * 0.08,  # Total capital requirement
            
            # Capital ratios
            "090": basel_results.cet1_ratio,  # CET1 ratio
            "100": basel_results.tier1_ratio,  # Tier 1 ratio
            "110": basel_results.total_capital_ratio,  # Total capital ratio
        }
        
        return COREPTable(
            table_code="C 02.00",
            table_name="Own funds requirements",
            reporting_date=reporting_date,
            institution_code=institution_code,
            data=data
        )
    
    def _generate_c_03_00_forbearance(self, portfolio: Portfolio,
                                    reporting_date: str, institution_code: str) -> COREPTable:
        """Generate C 03.00 - Forbearance and non-performing exposures table."""
        
        # Analyze portfolio for NPE and forbearance
        total_exposures = sum(exp.current_exposure for exp in portfolio.exposures)
        
        # Simplified NPE identification (would be more sophisticated in practice)
        npe_exposures = [exp for exp in portfolio.exposures 
                        if getattr(exp, 'days_past_due', 0) > 90 
                        or getattr(exp, 'defaulted', False)]
        
        forborne_exposures = [exp for exp in portfolio.exposures 
                            if getattr(exp, 'forborne', False)]
        
        total_npe = sum(exp.current_exposure for exp in npe_exposures)
        total_forborne = sum(exp.current_exposure for exp in forborne_exposures)
        
        data = {
            "010": total_exposures,  # Gross carrying amount
            "020": total_npe,  # Non-performing exposures
            "030": total_npe / total_exposures if total_exposures > 0 else 0,  # NPE ratio
            "040": total_forborne,  # Forborne exposures
            "050": len(npe_exposures),  # Number of NPE
            "060": len(forborne_exposures),  # Number of forborne exposures
        }
        
        return COREPTable(
            table_code="C 03.00",
            table_name="Forbearance and non-performing exposures",
            reporting_date=reporting_date,
            institution_code=institution_code,
            data=data
        )
    
    def _generate_c_07_00_operational(self, basel_results: Any,
                                    reporting_date: str, institution_code: str) -> COREPTable:
        """Generate C 07.00 - Operational risk table."""
        
        data = {
            "010": basel_results.operational_rwa,  # Operational risk RWA
            "020": basel_results.operational_rwa * 0.08,  # Capital requirement
            "030": getattr(basel_results, 'business_indicator', 0),  # Business Indicator
            "040": getattr(basel_results, 'internal_loss_multiplier', 1.0),  # ILM
        }
        
        return COREPTable(
            table_code="C 07.00",
            table_name="Operational risk",
            reporting_date=reporting_date,
            institution_code=institution_code,
            data=data
        )
    
    def _generate_c_09_00_leverage(self, basel_results: Any,
                                 reporting_date: str, institution_code: str) -> COREPTable:
        """Generate C 09.00 - Leverage ratio table."""
        
        leverage_ratio = getattr(basel_results, 'leverage_ratio', 0)
        tier1_capital = basel_results.tier1_capital
        total_exposure = tier1_capital / leverage_ratio if leverage_ratio > 0 else 0
        
        data = {
            "010": total_exposure,  # Total exposure measure
            "020": tier1_capital,  # Tier 1 capital
            "030": leverage_ratio,  # Leverage ratio
            "040": max(0, 0.03 - leverage_ratio) * total_exposure,  # Leverage ratio buffer requirement
        }
        
        return COREPTable(
            table_code="C 09.00",
            table_name="Leverage ratio",
            reporting_date=reporting_date,
            institution_code=institution_code,
            data=data
        )
    
    def export_to_xbrl(self, report: COREPReport, output_path: str) -> str:
        """Export COREP report to XBRL format."""
        
        # This would generate proper XBRL taxonomy-compliant XML
        # For now, return a placeholder
        
        xbrl_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xmlns:corep="http://www.eba.europa.eu/xbrl/corep">
    <corep:ReportingDate>{report.reporting_date}</corep:ReportingDate>
    <corep:InstitutionCode>{report.institution_code}</corep:InstitutionCode>
    <corep:InstitutionName>{report.institution_name}</corep:InstitutionName>
    
    <!-- C 01.00 Own Funds -->
    <corep:C_01_00_010>{report.c_01_00_own_funds.data.get('010', 0)}</corep:C_01_00_010>
    <corep:C_01_00_020>{report.c_01_00_own_funds.data.get('020', 0)}</corep:C_01_00_020>
    <!-- Additional XBRL elements would be included here -->
    
</xbrl>"""
        
        with open(output_path, 'w') as f:
            f.write(xbrl_content)
        
        self.logger.info(f"COREP report exported to XBRL: {output_path}")
        return output_path
    
    def validate_report(self, report: COREPReport) -> List[str]:
        """Validate COREP report for completeness and consistency."""
        
        errors = []
        
        # Check required fields
        if not report.institution_code:
            errors.append("Institution code is required")
        
        if not report.reporting_date:
            errors.append("Reporting date is required")
        
        # Validate C 01.00 - Own Funds
        if report.c_01_00_own_funds:
            data = report.c_01_00_own_funds.data
            
            # Check that CET1 = Common shares + Retained earnings + OCI - Adjustments
            cet1_calculated = (
                data.get('010', 0) + data.get('020', 0) + data.get('030', 0) +
                data.get('040', 0) - data.get('050', 0) - data.get('060', 0) -
                data.get('070', 0) - data.get('080', 0) - data.get('090', 0) -
                data.get('100', 0)
            )
            
            cet1_reported = data.get('140', 0)
            if abs(cet1_calculated - cet1_reported) > 0.01:  # Allow small rounding differences
                errors.append(f"CET1 calculation mismatch: calculated {cet1_calculated}, reported {cet1_reported}")
        
        # Cross-table validation
        if report.c_01_00_own_funds and report.c_02_00_own_funds_requirements:
            own_funds_rwa = report.c_01_00_own_funds.data.get('170', 0)
            requirements_rwa = report.c_02_00_own_funds_requirements.data.get('070', 0)
            
            if abs(own_funds_rwa - requirements_rwa) > 0.01:
                errors.append(f"RWA mismatch between C 01.00 and C 02.00")
        
        return errors
