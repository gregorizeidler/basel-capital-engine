"""Regulatory buffers and breach calculations for Basel Capital Engine."""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime


class BufferType(str, Enum):
    """Types of regulatory capital buffers."""
    
    CONSERVATION = "conservation"           # Capital Conservation Buffer (2.5%)
    COUNTERCYCLICAL = "countercyclical"    # Countercyclical Buffer (0-2.5%)
    GSIB = "gsib"                          # Global Systemically Important Bank
    DSIB = "dsib"                          # Domestic Systemically Important Bank
    SYSTEMIC_RISK = "systemic_risk"        # Systemic Risk Buffer


class BufferBreach(BaseModel):
    """Represents a buffer breach with associated restrictions."""
    
    buffer_type: BufferType
    required_ratio: float = Field(ge=0, le=1, description="Required buffer ratio")
    actual_ratio: float = Field(ge=0, le=1, description="Actual capital ratio")
    shortfall_ratio: float = Field(ge=0, description="Shortfall in ratio terms")
    shortfall_amount: float = Field(ge=0, description="Shortfall in monetary terms")
    
    # Maximum Distributable Amount restrictions
    mda_applicable: bool = False
    mda_restriction_pct: float = Field(default=0, ge=0, le=1, description="MDA restriction percentage")
    
    def calculate_mda_restriction(self) -> float:
        """Calculate Maximum Distributable Amount restriction percentage."""
        if not self.mda_applicable or self.shortfall_ratio <= 0:
            return 0.0
        
        # MDA restrictions based on CET1 ratio shortfall
        # These are simplified rules - actual implementation may vary by jurisdiction
        if self.buffer_type == BufferType.CONSERVATION:
            if self.shortfall_ratio <= 0.00625:  # 0-62.5bp shortfall
                return 1.0  # 100% restriction
            elif self.shortfall_ratio <= 0.0125:  # 62.5-125bp shortfall
                return 0.8  # 80% restriction
            elif self.shortfall_ratio <= 0.01875:  # 125-187.5bp shortfall
                return 0.6  # 60% restriction
            elif self.shortfall_ratio <= 0.025:  # 187.5-250bp shortfall
                return 0.4  # 40% restriction
        
        return 0.0


class RegulatoryBuffers(BaseModel):
    """Regulatory capital buffers for a financial institution."""
    
    # Buffer requirements (as ratios)
    conservation_buffer: float = Field(default=0.025, ge=0, le=0.1, description="Conservation buffer (typically 2.5%)")
    countercyclical_buffer: float = Field(default=0.0, ge=0, le=0.025, description="CCyB (0-2.5%)")
    
    # SIFI buffers
    gsib_buffer: float = Field(default=0.0, ge=0, le=0.035, description="G-SIB buffer (0-3.5%)")
    dsib_buffer: float = Field(default=0.0, ge=0, le=0.02, description="D-SIB buffer (typically up to 2%)")
    
    # Other buffers
    systemic_risk_buffer: float = Field(default=0.0, ge=0, le=0.05, description="SRB (up to 5%)")
    
    # Jurisdiction and date
    jurisdiction: Optional[str] = None
    effective_date: Optional[str] = None
    
    # G-SIB specific
    gsib_bucket: Optional[int] = Field(None, ge=1, le=5, description="G-SIB bucket (1-5)")
    gsib_score: Optional[float] = Field(None, ge=0, description="G-SIB indicator score")
    
    def get_total_buffer_requirement(self) -> float:
        """Calculate total buffer requirement."""
        return (
            self.conservation_buffer +
            self.countercyclical_buffer + 
            max(self.gsib_buffer, self.dsib_buffer) +  # Take higher of G-SIB or D-SIB
            self.systemic_risk_buffer
        )
    
    def get_buffer_breakdown(self) -> Dict[str, float]:
        """Get breakdown of buffer requirements."""
        return {
            "conservation": self.conservation_buffer,
            "countercyclical": self.countercyclical_buffer,
            "gsib": self.gsib_buffer,
            "dsib": self.dsib_buffer,
            "systemic_risk": self.systemic_risk_buffer,
            "total": self.get_total_buffer_requirement()
        }
    
    def set_gsib_buffer_from_bucket(self, bucket: int) -> None:
        """Set G-SIB buffer based on bucket."""
        bucket_rates = {
            1: 0.01,   # 1.0%
            2: 0.015,  # 1.5%
            3: 0.02,   # 2.0%
            4: 0.025,  # 2.5%
            5: 0.035   # 3.5%
        }
        
        if bucket in bucket_rates:
            self.gsib_buffer = bucket_rates[bucket]
            self.gsib_bucket = bucket
    
    def calculate_ccyb_weighted_average(self, exposures_by_country: Dict[str, float], 
                                      ccyb_rates: Dict[str, float]) -> float:
        """Calculate weighted average countercyclical buffer rate."""
        if not exposures_by_country or not ccyb_rates:
            return 0.0
        
        total_exposure = sum(exposures_by_country.values())
        if total_exposure == 0:
            return 0.0
        
        weighted_sum = 0.0
        for country, exposure in exposures_by_country.items():
            ccyb_rate = ccyb_rates.get(country, 0.0)
            weighted_sum += (exposure / total_exposure) * ccyb_rate
        
        return weighted_sum
    
    def check_buffer_breaches(self, cet1_ratio: float, tier1_ratio: float, 
                            total_capital_ratio: float, total_rwa: float) -> List[BufferBreach]:
        """Check for buffer breaches and calculate restrictions."""
        breaches = []
        
        # Minimum requirements (before buffers)
        min_cet1 = 0.045  # 4.5%
        min_tier1 = 0.06  # 6.0%
        min_total = 0.08  # 8.0%
        
        # Required ratios including buffers
        required_cet1 = min_cet1 + self.get_total_buffer_requirement()
        required_tier1 = min_tier1 + self.get_total_buffer_requirement()
        required_total = min_total + self.get_total_buffer_requirement()
        
        # Check CET1 buffer breaches
        if cet1_ratio < required_cet1:
            shortfall_ratio = required_cet1 - cet1_ratio
            shortfall_amount = shortfall_ratio * total_rwa
            
            breach = BufferBreach(
                buffer_type=BufferType.CONSERVATION,  # Primary breach type
                required_ratio=required_cet1,
                actual_ratio=cet1_ratio,
                shortfall_ratio=shortfall_ratio,
                shortfall_amount=shortfall_amount,
                mda_applicable=True
            )
            breach.mda_restriction_pct = breach.calculate_mda_restriction()
            breaches.append(breach)
        
        # Check individual buffer breaches for detailed reporting
        buffer_components = self.get_buffer_breakdown()
        
        for buffer_name, buffer_rate in buffer_components.items():
            if buffer_name == "total" or buffer_rate == 0:
                continue
            
            buffer_type = BufferType(buffer_name)
            required_with_buffer = min_cet1 + buffer_rate
            
            if cet1_ratio < required_with_buffer:
                shortfall_ratio = required_with_buffer - cet1_ratio
                shortfall_amount = shortfall_ratio * total_rwa
                
                breach = BufferBreach(
                    buffer_type=buffer_type,
                    required_ratio=required_with_buffer,
                    actual_ratio=cet1_ratio,
                    shortfall_ratio=shortfall_ratio,
                    shortfall_amount=shortfall_amount,
                    mda_applicable=(buffer_type == BufferType.CONSERVATION)
                )
                
                # Only add if not already covered by main breach
                if not any(b.buffer_type == BufferType.CONSERVATION for b in breaches):
                    breaches.append(breach)
        
        return breaches
    
    def get_mda_restrictions(self, breaches: List[BufferBreach]) -> Dict[str, Any]:
        """Calculate Maximum Distributable Amount restrictions."""
        if not breaches:
            return {"applicable": False, "restriction_pct": 0.0}
        
        # Find the most restrictive MDA
        max_restriction = 0.0
        applicable_breach = None
        
        for breach in breaches:
            if breach.mda_applicable and breach.mda_restriction_pct > max_restriction:
                max_restriction = breach.mda_restriction_pct
                applicable_breach = breach
        
        return {
            "applicable": max_restriction > 0,
            "restriction_pct": max_restriction,
            "breach_type": applicable_breach.buffer_type if applicable_breach else None,
            "shortfall_amount": applicable_breach.shortfall_amount if applicable_breach else 0,
            "description": f"MDA restriction of {max_restriction:.1%} due to {applicable_breach.buffer_type.value} buffer breach" if applicable_breach else "No MDA restrictions"
        }
    
    def simulate_buffer_impact(self, base_cet1_ratio: float, total_rwa: float, 
                              scenario_name: str = "base") -> Dict[str, Any]:
        """Simulate impact of different buffer scenarios."""
        current_breaches = self.check_buffer_breaches(base_cet1_ratio, base_cet1_ratio, base_cet1_ratio, total_rwa)
        
        # Calculate required capital to meet all buffers
        required_cet1_ratio = 0.045 + self.get_total_buffer_requirement()
        capital_shortfall = max(0, (required_cet1_ratio - base_cet1_ratio) * total_rwa)
        
        return {
            "scenario": scenario_name,
            "current_cet1_ratio": base_cet1_ratio,
            "required_cet1_ratio": required_cet1_ratio,
            "buffer_requirement": self.get_total_buffer_requirement(),
            "capital_shortfall": capital_shortfall,
            "breaches": len(current_breaches),
            "mda_restrictions": self.get_mda_restrictions(current_breaches),
            "buffer_breakdown": self.get_buffer_breakdown()
        }
