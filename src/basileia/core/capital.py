"""Capital definitions and calculations for Basel Capital Engine."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
from enum import Enum


class CapitalTier(str, Enum):
    """Capital tiers according to Basel III."""
    
    CET1 = "cet1"  # Common Equity Tier 1
    AT1 = "at1"    # Additional Tier 1
    T2 = "t2"      # Tier 2


class CapitalInstrument(BaseModel):
    """Individual capital instrument."""
    
    instrument_id: str
    instrument_name: str
    tier: CapitalTier
    amount: float = Field(gt=0, description="Amount in base currency")
    currency: str = "EUR"
    
    # Instrument characteristics
    is_perpetual: bool = False
    has_step_up: bool = False
    has_call_option: bool = False
    conversion_trigger: Optional[float] = None  # CET1 ratio trigger for contingent convertible
    
    # Regulatory treatment
    phased_out_amount: Optional[float] = None  # Amount being phased out
    grandfathered: bool = False
    
    def get_eligible_amount(self, reporting_date: Optional[str] = None) -> float:
        """Get amount eligible for regulatory capital."""
        eligible = self.amount
        
        # Apply phase-out if applicable
        if self.phased_out_amount:
            eligible -= self.phased_out_amount
        
        return max(0, eligible)


class RegulatoryDeduction(BaseModel):
    """Regulatory deductions from capital."""
    
    deduction_type: str
    amount: float = Field(ge=0)
    tier_applied: CapitalTier
    description: Optional[str] = None


class CapitalComponents(BaseModel):
    """Components of regulatory capital."""
    
    # Common Equity Tier 1
    common_shares: float = Field(default=0, ge=0)
    retained_earnings: float = Field(default=0)  # Can be negative
    accumulated_oci: float = Field(default=0)    # Accumulated other comprehensive income
    minority_interests: float = Field(default=0, ge=0)
    
    # Additional Tier 1
    at1_instruments: float = Field(default=0, ge=0)
    
    # Tier 2
    t2_instruments: float = Field(default=0, ge=0)
    general_provisions: float = Field(default=0, ge=0)
    
    # Regulatory adjustments and deductions
    goodwill: float = Field(default=0, ge=0)
    intangible_assets: float = Field(default=0, ge=0)
    deferred_tax_assets: float = Field(default=0, ge=0)
    cash_flow_hedge_reserve: float = Field(default=0)
    shortfall_provisions: float = Field(default=0, ge=0)
    securitization_exposures: float = Field(default=0, ge=0)
    investments_in_own_shares: float = Field(default=0, ge=0)
    reciprocal_cross_holdings: float = Field(default=0, ge=0)
    investments_in_financial_institutions: float = Field(default=0, ge=0)
    mortgage_servicing_rights: float = Field(default=0, ge=0)
    
    # Threshold deductions
    significant_investments_threshold: float = Field(default=0, ge=0)
    dta_threshold: float = Field(default=0, ge=0)
    mortgage_servicing_threshold: float = Field(default=0, ge=0)
    
    def calculate_cet1_before_adjustments(self) -> float:
        """Calculate CET1 before regulatory adjustments."""
        return (
            self.common_shares +
            self.retained_earnings + 
            self.accumulated_oci +
            self.minority_interests
        )
    
    def calculate_cet1_adjustments(self) -> float:
        """Calculate total CET1 regulatory adjustments (deductions)."""
        # Full deductions
        full_deductions = (
            self.goodwill +
            self.intangible_assets +
            self.investments_in_own_shares +
            self.reciprocal_cross_holdings +
            self.shortfall_provisions +
            self.securitization_exposures
        )
        
        # Threshold deductions (amounts above 10% individually or 15% in aggregate)
        threshold_deductions = (
            self.significant_investments_threshold +
            self.dta_threshold + 
            self.mortgage_servicing_threshold
        )
        
        # Cash flow hedge reserve (add back if negative, deduct if positive)
        hedge_adjustment = max(0, self.cash_flow_hedge_reserve)
        
        return full_deductions + threshold_deductions + hedge_adjustment
    
    def calculate_cet1(self) -> float:
        """Calculate final CET1 capital."""
        cet1_before = self.calculate_cet1_before_adjustments()
        adjustments = self.calculate_cet1_adjustments()
        return max(0, cet1_before - adjustments)
    
    def calculate_tier1(self) -> float:
        """Calculate Tier 1 capital (CET1 + AT1)."""
        return self.calculate_cet1() + self.at1_instruments
    
    def calculate_total_capital(self) -> float:
        """Calculate total regulatory capital."""
        tier1 = self.calculate_tier1()
        
        # Tier 2 is limited to 100% of Tier 1
        eligible_t2 = min(self.t2_instruments + self.general_provisions, tier1)
        
        return tier1 + eligible_t2


class Capital(BaseModel):
    """Complete capital structure of a financial institution."""
    
    bank_name: Optional[str] = None
    reporting_date: Optional[str] = None
    base_currency: str = "EUR"
    
    # Capital components
    components: CapitalComponents = Field(default_factory=CapitalComponents)
    
    # Individual instruments (detailed view)
    instruments: List[CapitalInstrument] = Field(default_factory=list)
    
    # Regulatory deductions (detailed view)
    deductions: List[RegulatoryDeduction] = Field(default_factory=list)
    
    def add_instrument(self, instrument: CapitalInstrument) -> None:
        """Add a capital instrument."""
        self.instruments.append(instrument)
    
    def add_deduction(self, deduction: RegulatoryDeduction) -> None:
        """Add a regulatory deduction."""
        self.deductions.append(deduction)
    
    def get_instruments_by_tier(self, tier: CapitalTier) -> List[CapitalInstrument]:
        """Get all instruments of a specific tier."""
        return [inst for inst in self.instruments if inst.tier == tier]
    
    def get_total_instrument_amount(self, tier: CapitalTier) -> float:
        """Get total amount of instruments for a specific tier."""
        instruments = self.get_instruments_by_tier(tier)
        return sum(inst.get_eligible_amount() for inst in instruments)
    
    def get_deductions_by_tier(self, tier: CapitalTier) -> List[RegulatoryDeduction]:
        """Get all deductions applied to a specific tier."""
        return [ded for ded in self.deductions if ded.tier_applied == tier]
    
    def get_total_deduction_amount(self, tier: CapitalTier) -> float:
        """Get total deduction amount for a specific tier."""
        deductions = self.get_deductions_by_tier(tier)
        return sum(ded.amount for ded in deductions)
    
    def calculate_cet1_capital(self) -> float:
        """Calculate CET1 capital."""
        return self.components.calculate_cet1()
    
    def calculate_tier1_capital(self) -> float:
        """Calculate Tier 1 capital."""
        return self.components.calculate_tier1()
    
    def calculate_total_capital(self) -> float:
        """Calculate total regulatory capital."""
        return self.components.calculate_total_capital()
    
    def get_capital_summary(self) -> Dict[str, Any]:
        """Get summary of capital calculations."""
        cet1 = self.calculate_cet1_capital()
        tier1 = self.calculate_tier1_capital()
        total = self.calculate_total_capital()
        
        return {
            "cet1_capital": cet1,
            "at1_capital": tier1 - cet1,
            "tier1_capital": tier1,
            "tier2_capital": total - tier1,
            "total_capital": total,
            "cet1_before_adjustments": self.components.calculate_cet1_before_adjustments(),
            "cet1_adjustments": self.components.calculate_cet1_adjustments(),
            "instrument_breakdown": {
                "cet1_instruments": self.get_total_instrument_amount(CapitalTier.CET1),
                "at1_instruments": self.get_total_instrument_amount(CapitalTier.AT1),
                "t2_instruments": self.get_total_instrument_amount(CapitalTier.T2),
            },
            "deduction_breakdown": {
                "cet1_deductions": self.get_total_deduction_amount(CapitalTier.CET1),
                "at1_deductions": self.get_total_deduction_amount(CapitalTier.AT1),
                "t2_deductions": self.get_total_deduction_amount(CapitalTier.T2),
            }
        }
    
    def validate_capital_structure(self) -> List[str]:
        """Validate capital structure and return list of issues."""
        issues = []
        
        cet1 = self.calculate_cet1_capital()
        tier1 = self.calculate_tier1_capital()
        total = self.calculate_total_capital()
        
        # Basic validations
        if cet1 < 0:
            issues.append("CET1 capital is negative")
        
        if tier1 < cet1:
            issues.append("Tier 1 capital is less than CET1 capital")
        
        if total < tier1:
            issues.append("Total capital is less than Tier 1 capital")
        
        # Check for excessive AT1
        at1_amount = tier1 - cet1
        if at1_amount > cet1:
            issues.append("AT1 capital exceeds CET1 capital (may indicate regulatory issue)")
        
        # Check for excessive T2
        t2_amount = total - tier1
        if t2_amount > tier1:
            issues.append("Tier 2 capital exceeds Tier 1 capital (regulatory limit)")
        
        return issues
