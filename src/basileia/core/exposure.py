"""Exposure definitions and calculations for Basel Capital Engine."""

from enum import Enum
from typing import Optional, Dict, Any, List
from decimal import Decimal
from pydantic import BaseModel, Field, validator
import numpy as np


class ExposureType(str, Enum):
    """Types of exposures for regulatory capital calculations."""
    
    # On-balance sheet
    LOANS = "loans"
    SECURITIES = "securities"
    CASH = "cash"
    
    # Off-balance sheet
    COMMITMENTS = "commitments"
    GUARANTEES = "guarantees"
    DERIVATIVES = "derivatives"
    
    # Trading book
    TRADING_SECURITIES = "trading_securities"
    TRADING_DERIVATIVES = "trading_derivatives"


class ExposureClass(str, Enum):
    """Asset classes for risk weight determination."""
    
    # Credit risk classes
    SOVEREIGN = "sovereign"
    BANK = "bank"
    CORPORATE = "corporate"
    RETAIL_MORTGAGE = "retail_mortgage"
    RETAIL_REVOLVING = "retail_revolving"
    RETAIL_OTHER = "retail_other"
    REAL_ESTATE = "real_estate"
    PAST_DUE = "past_due"
    OTHER_ASSETS = "other_assets"
    
    # Market risk classes
    INTEREST_RATE = "interest_rate"
    EQUITY = "equity"
    FX = "fx"
    CREDIT_SPREAD = "credit_spread"
    COMMODITY = "commodity"


class CreditRiskMitigation(BaseModel):
    """Credit risk mitigation techniques."""
    
    collateral_type: Optional[str] = None
    collateral_value: Optional[float] = None
    guarantee_provider: Optional[str] = None
    guarantee_amount: Optional[float] = None
    netting_agreement: bool = False
    
    def get_haircut(self, config: "BaselConfig") -> float:
        """Calculate haircut for collateral."""
        if not self.collateral_type:
            return 0.0
        
        haircuts = config.crm.get("haircuts", {})
        return haircuts.get(self.collateral_type, 0.0)
    
    def get_effective_collateral(self, config: "BaselConfig") -> float:
        """Calculate effective collateral value after haircuts."""
        if not self.collateral_value:
            return 0.0
        
        haircut = self.get_haircut(config)
        return self.collateral_value * (1 - haircut)


class Exposure(BaseModel):
    """Individual exposure for capital calculation."""
    
    # Identification
    exposure_id: str
    counterparty_id: Optional[str] = None
    
    # Basic attributes
    exposure_type: ExposureType
    exposure_class: ExposureClass
    original_exposure: float = Field(gt=0, description="Original exposure amount")
    current_exposure: float = Field(gt=0, description="Current exposure amount")
    
    # Credit risk parameters
    probability_of_default: Optional[float] = Field(None, ge=0, le=1, description="PD as decimal")
    loss_given_default: Optional[float] = Field(None, ge=0, le=1, description="LGD as decimal")
    maturity: Optional[float] = Field(None, gt=0, description="Maturity in years")
    
    # Rating and classification
    external_rating: Optional[str] = None
    internal_rating: Optional[str] = None
    
    # Off-balance sheet specific
    credit_conversion_factor: Optional[float] = Field(None, ge=0, le=1)
    
    # Market risk specific
    market_value: Optional[float] = None
    sensitivities: Optional[Dict[str, float]] = Field(default_factory=dict)
    
    # Credit risk mitigation
    crm: Optional[CreditRiskMitigation] = None
    
    # Additional metadata
    currency: str = "EUR"
    business_line: Optional[str] = None
    geography: Optional[str] = None
    sector: Optional[str] = None
    
    @validator("probability_of_default")
    def validate_pd(cls, v: Optional[float]) -> Optional[float]:
        """Ensure PD is within reasonable bounds."""
        if v is not None and (v < 0.0001 or v > 0.99):
            raise ValueError("PD must be between 0.01% and 99%")
        return v
    
    @validator("loss_given_default")  
    def validate_lgd(cls, v: Optional[float]) -> Optional[float]:
        """Ensure LGD is within reasonable bounds."""
        if v is not None and (v < 0.01 or v > 1.0):
            raise ValueError("LGD must be between 1% and 100%")
        return v
    
    def get_exposure_at_default(self) -> float:
        """Calculate Exposure at Default (EAD)."""
        if self.exposure_type in [ExposureType.COMMITMENTS, ExposureType.GUARANTEES]:
            ccf = self.credit_conversion_factor or 0.0
            return self.current_exposure * ccf
        return self.current_exposure
    
    def get_effective_maturity(self) -> float:
        """Get effective maturity with regulatory floors and caps."""
        if self.maturity is None:
            return 2.5  # Default maturity
        return max(1.0, min(5.0, self.maturity))  # Floor at 1y, cap at 5y
    
    def apply_credit_risk_mitigation(self, config: "BaselConfig") -> float:
        """Apply credit risk mitigation to reduce exposure."""
        if not self.crm:
            return self.get_exposure_at_default()
        
        ead = self.get_exposure_at_default()
        effective_collateral = self.crm.get_effective_collateral(config)
        
        # Simple approach: reduce EAD by effective collateral
        return max(0, ead - effective_collateral)
    
    def is_retail(self) -> bool:
        """Check if exposure qualifies as retail."""
        return self.exposure_class in [
            ExposureClass.RETAIL_MORTGAGE,
            ExposureClass.RETAIL_REVOLVING, 
            ExposureClass.RETAIL_OTHER
        ]
    
    def is_trading_book(self) -> bool:
        """Check if exposure is in trading book."""
        return self.exposure_type in [
            ExposureType.TRADING_SECURITIES,
            ExposureType.TRADING_DERIVATIVES
        ]


class Portfolio(BaseModel):
    """Collection of exposures representing a bank's portfolio."""
    
    portfolio_id: str
    bank_name: Optional[str] = None
    reporting_date: Optional[str] = None
    exposures: List[Exposure] = Field(default_factory=list)
    
    def add_exposure(self, exposure: Exposure) -> None:
        """Add an exposure to the portfolio."""
        self.exposures.append(exposure)
    
    def get_total_exposure(self) -> float:
        """Get total exposure amount."""
        return sum(exp.current_exposure for exp in self.exposures)
    
    def get_exposures_by_class(self, exposure_class: ExposureClass) -> List[Exposure]:
        """Get all exposures of a specific class."""
        return [exp for exp in self.exposures if exp.exposure_class == exposure_class]
    
    def get_exposures_by_type(self, exposure_type: ExposureType) -> List[Exposure]:
        """Get all exposures of a specific type."""
        return [exp for exp in self.exposures if exp.exposure_type == exposure_type]
    
    def get_trading_book_exposures(self) -> List[Exposure]:
        """Get all trading book exposures."""
        return [exp for exp in self.exposures if exp.is_trading_book()]
    
    def get_banking_book_exposures(self) -> List[Exposure]:
        """Get all banking book exposures."""
        return [exp for exp in self.exposures if not exp.is_trading_book()]
    
    def get_concentration_metrics(self) -> Dict[str, Any]:
        """Calculate portfolio concentration metrics."""
        if not self.exposures:
            return {}
        
        total_exposure = self.get_total_exposure()
        
        # Concentration by counterparty
        counterparty_exposures = {}
        for exp in self.exposures:
            if exp.counterparty_id:
                counterparty_exposures[exp.counterparty_id] = (
                    counterparty_exposures.get(exp.counterparty_id, 0) + exp.current_exposure
                )
        
        # Concentration by sector
        sector_exposures = {}
        for exp in self.exposures:
            if exp.sector:
                sector_exposures[exp.sector] = (
                    sector_exposures.get(exp.sector, 0) + exp.current_exposure
                )
        
        # Calculate concentration ratios
        largest_counterparty = max(counterparty_exposures.values()) if counterparty_exposures else 0
        largest_sector = max(sector_exposures.values()) if sector_exposures else 0
        
        return {
            "total_exposure": total_exposure,
            "num_exposures": len(self.exposures),
            "largest_counterparty_pct": largest_counterparty / total_exposure if total_exposure > 0 else 0,
            "largest_sector_pct": largest_sector / total_exposure if total_exposure > 0 else 0,
            "counterparty_hhi": self._calculate_hhi(list(counterparty_exposures.values())),
            "sector_hhi": self._calculate_hhi(list(sector_exposures.values())),
        }
    
    def _calculate_hhi(self, exposures: List[float]) -> float:
        """Calculate Herfindahl-Hirschman Index for concentration."""
        if not exposures:
            return 0.0
        
        total = sum(exposures)
        if total == 0:
            return 0.0
        
        return sum((exp / total) ** 2 for exp in exposures)
