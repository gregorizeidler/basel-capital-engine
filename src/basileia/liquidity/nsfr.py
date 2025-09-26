"""Net Stable Funding Ratio (NSFR) calculation for Basel III liquidity framework."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum
import logging

from ..core.config import BaselConfig

logger = logging.getLogger(__name__)


class FundingCategory(str, Enum):
    """Categories of stable funding sources."""
    
    REGULATORY_CAPITAL = "regulatory_capital"
    RETAIL_DEPOSITS_STABLE = "retail_deposits_stable"
    RETAIL_DEPOSITS_LESS_STABLE = "retail_deposits_less_stable"
    WHOLESALE_OPERATIONAL = "wholesale_operational"
    WHOLESALE_NON_OPERATIONAL = "wholesale_non_operational"
    SECURED_FUNDING = "secured_funding"
    OTHER_LIABILITIES = "other_liabilities"


class AssetCategory(str, Enum):
    """Categories of assets requiring stable funding."""
    
    CASH_CENTRAL_BANK = "cash_central_bank"
    HQLA_LEVEL_1 = "hqla_level_1"
    HQLA_LEVEL_2A = "hqla_level_2a"
    HQLA_LEVEL_2B = "hqla_level_2b"
    PERFORMING_LOANS = "performing_loans"
    NON_PERFORMING_LOANS = "non_performing_loans"
    UNENCUMBERED_NON_HQLA = "unencumbered_non_hqla"
    OTHER_ASSETS = "other_assets"


class FundingSource(BaseModel):
    """Individual funding source for NSFR calculation."""
    
    source_id: str
    source_type: str
    amount: float = Field(gt=0)
    category: FundingCategory
    maturity_days: int = Field(ge=0)
    asf_factor: float = Field(ge=0, le=1)  # Available Stable Funding factor


class RequiredAsset(BaseModel):
    """Individual asset requiring stable funding."""
    
    asset_id: str
    asset_type: str
    amount: float = Field(gt=0)
    category: AssetCategory
    maturity_days: int = Field(ge=0)
    rsf_factor: float = Field(ge=0, le=1)  # Required Stable Funding factor
    encumbered: bool = False


class NSFRResult(BaseModel):
    """NSFR calculation result."""
    
    # Available Stable Funding components
    total_asf: float = Field(ge=0)
    regulatory_capital_asf: float = Field(ge=0)
    retail_deposits_asf: float = Field(ge=0)
    wholesale_deposits_asf: float = Field(ge=0)
    other_funding_asf: float = Field(ge=0)
    
    # Required Stable Funding components
    total_rsf: float = Field(ge=0)
    cash_rsf: float = Field(ge=0)
    hqla_rsf: float = Field(ge=0)
    loans_rsf: float = Field(ge=0)
    other_assets_rsf: float = Field(ge=0)
    
    # Final ratio
    nsfr_ratio: float = Field(ge=0)
    compliant: bool
    
    # Detailed breakdowns
    asf_breakdown: Dict[str, float]
    rsf_breakdown: Dict[str, float]
    
    calculation_date: str


class NSFRCalculator:
    """
    Net Stable Funding Ratio calculator following Basel III liquidity standards.
    
    NSFR = Available Stable Funding / Required Stable Funding ≥ 100%
    """
    
    def __init__(self, config: Optional[BaselConfig] = None):
        """Initialize NSFR calculator."""
        self.config = config or BaselConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Default ASF factors from Basel III
        self.default_asf_factors = {
            FundingCategory.REGULATORY_CAPITAL: 1.00,
            FundingCategory.RETAIL_DEPOSITS_STABLE: 0.95,
            FundingCategory.RETAIL_DEPOSITS_LESS_STABLE: 0.90,
            FundingCategory.WHOLESALE_OPERATIONAL: 0.50,
            FundingCategory.WHOLESALE_NON_OPERATIONAL: 0.00,  # <1 year maturity
            FundingCategory.SECURED_FUNDING: 0.00,
            FundingCategory.OTHER_LIABILITIES: 0.00
        }
        
        # Default RSF factors from Basel III
        self.default_rsf_factors = {
            AssetCategory.CASH_CENTRAL_BANK: 0.00,
            AssetCategory.HQLA_LEVEL_1: 0.05,
            AssetCategory.HQLA_LEVEL_2A: 0.15,
            AssetCategory.HQLA_LEVEL_2B: 0.50,
            AssetCategory.PERFORMING_LOANS: 0.85,  # >1 year maturity
            AssetCategory.NON_PERFORMING_LOANS: 1.00,
            AssetCategory.UNENCUMBERED_NON_HQLA: 1.00,
            AssetCategory.OTHER_ASSETS: 1.00
        }
    
    def calculate_nsfr(self, funding_sources: List[FundingSource],
                       required_assets: List[RequiredAsset],
                       calculation_date: str = None) -> NSFRResult:
        """Calculate NSFR for given funding sources and assets."""
        
        self.logger.info("Calculating NSFR")
        
        # Calculate Available Stable Funding
        asf_result = self._calculate_asf(funding_sources)
        
        # Calculate Required Stable Funding
        rsf_result = self._calculate_rsf(required_assets)
        
        # Calculate NSFR
        nsfr_ratio = asf_result['total'] / rsf_result['total'] if rsf_result['total'] > 0 else float('inf')
        compliant = nsfr_ratio >= 1.00
        
        return NSFRResult(
            total_asf=asf_result['total'],
            regulatory_capital_asf=asf_result.get('regulatory_capital', 0),
            retail_deposits_asf=asf_result.get('retail_deposits', 0),
            wholesale_deposits_asf=asf_result.get('wholesale_deposits', 0),
            other_funding_asf=asf_result.get('other_funding', 0),
            total_rsf=rsf_result['total'],
            cash_rsf=rsf_result.get('cash', 0),
            hqla_rsf=rsf_result.get('hqla', 0),
            loans_rsf=rsf_result.get('loans', 0),
            other_assets_rsf=rsf_result.get('other_assets', 0),
            nsfr_ratio=nsfr_ratio,
            compliant=compliant,
            asf_breakdown=asf_result,
            rsf_breakdown=rsf_result,
            calculation_date=calculation_date or "2024-01-01"
        )
    
    def _calculate_asf(self, funding_sources: List[FundingSource]) -> Dict[str, float]:
        """Calculate Available Stable Funding."""
        
        asf_breakdown = {
            'regulatory_capital': 0.0,
            'retail_deposits': 0.0,
            'wholesale_deposits': 0.0,
            'other_funding': 0.0,
            'total': 0.0
        }
        
        for source in funding_sources:
            # Get ASF factor
            asf_factor = source.asf_factor or self._get_default_asf_factor(source)
            
            # Apply maturity adjustment for wholesale funding
            if source.category in [FundingCategory.WHOLESALE_NON_OPERATIONAL, 
                                 FundingCategory.SECURED_FUNDING]:
                if source.maturity_days >= 365:  # ≥1 year gets higher ASF factor
                    asf_factor = min(1.0, asf_factor + 0.50)
            
            asf_value = source.amount * asf_factor
            
            # Categorize for reporting
            if source.category == FundingCategory.REGULATORY_CAPITAL:
                asf_breakdown['regulatory_capital'] += asf_value
            elif source.category in [FundingCategory.RETAIL_DEPOSITS_STABLE, 
                                   FundingCategory.RETAIL_DEPOSITS_LESS_STABLE]:
                asf_breakdown['retail_deposits'] += asf_value
            elif source.category in [FundingCategory.WHOLESALE_OPERATIONAL,
                                   FundingCategory.WHOLESALE_NON_OPERATIONAL]:
                asf_breakdown['wholesale_deposits'] += asf_value
            else:
                asf_breakdown['other_funding'] += asf_value
        
        asf_breakdown['total'] = sum(v for k, v in asf_breakdown.items() if k != 'total')
        
        self.logger.debug(f"ASF calculated: {asf_breakdown}")
        return asf_breakdown
    
    def _calculate_rsf(self, required_assets: List[RequiredAsset]) -> Dict[str, float]:
        """Calculate Required Stable Funding."""
        
        rsf_breakdown = {
            'cash': 0.0,
            'hqla': 0.0,
            'loans': 0.0,
            'other_assets': 0.0,
            'total': 0.0
        }
        
        for asset in required_assets:
            if asset.encumbered:
                continue  # Skip encumbered assets (generally 0% RSF)
            
            # Get RSF factor
            rsf_factor = asset.rsf_factor or self._get_default_rsf_factor(asset)
            
            # Apply maturity adjustment for loans
            if asset.category == AssetCategory.PERFORMING_LOANS:
                if asset.maturity_days < 365:  # <1 year gets lower RSF factor
                    rsf_factor = 0.50
                else:
                    rsf_factor = 0.85
            
            rsf_value = asset.amount * rsf_factor
            
            # Categorize for reporting
            if asset.category == AssetCategory.CASH_CENTRAL_BANK:
                rsf_breakdown['cash'] += rsf_value
            elif asset.category in [AssetCategory.HQLA_LEVEL_1, AssetCategory.HQLA_LEVEL_2A, 
                                  AssetCategory.HQLA_LEVEL_2B]:
                rsf_breakdown['hqla'] += rsf_value
            elif asset.category in [AssetCategory.PERFORMING_LOANS, AssetCategory.NON_PERFORMING_LOANS]:
                rsf_breakdown['loans'] += rsf_value
            else:
                rsf_breakdown['other_assets'] += rsf_value
        
        rsf_breakdown['total'] = sum(v for k, v in rsf_breakdown.items() if k != 'total')
        
        self.logger.debug(f"RSF calculated: {rsf_breakdown}")
        return rsf_breakdown
    
    def _get_default_asf_factor(self, source: FundingSource) -> float:
        """Get default ASF factor based on funding category."""
        return self.default_asf_factors.get(source.category, 0.0)
    
    def _get_default_rsf_factor(self, asset: RequiredAsset) -> float:
        """Get default RSF factor based on asset category."""
        return self.default_rsf_factors.get(asset.category, 1.0)  # Default to 100%
    
    def stress_test_nsfr(self, base_result: NSFRResult, 
                        stress_scenarios: Dict[str, Dict]) -> Dict[str, NSFRResult]:
        """Apply stress scenarios to NSFR calculation."""
        
        stress_results = {}
        
        for scenario_name, scenario_params in stress_scenarios.items():
            # Apply stress to ASF (funding runoff)
            asf_stress = scenario_params.get('asf_decline', 0.0)
            stressed_asf = base_result.total_asf * (1 - asf_stress)
            
            # Apply stress to RSF (asset growth or quality deterioration)
            rsf_stress = scenario_params.get('rsf_increase', 0.0)
            stressed_rsf = base_result.total_rsf * (1 + rsf_stress)
            
            # Calculate stressed NSFR
            stressed_nsfr = stressed_asf / stressed_rsf if stressed_rsf > 0 else float('inf')
            
            # Create stressed result
            stressed_result = base_result.model_copy()
            stressed_result.total_asf = stressed_asf
            stressed_result.total_rsf = stressed_rsf
            stressed_result.nsfr_ratio = stressed_nsfr
            stressed_result.compliant = stressed_nsfr >= 1.00
            
            stress_results[scenario_name] = stressed_result
        
        return stress_results
