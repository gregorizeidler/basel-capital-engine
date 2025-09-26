"""Credit Risk RWA calculations for Basel Capital Engine."""

from typing import Dict, Any, List, Optional
from enum import Enum
import math
import logging

from ..core.config import BaselConfig
from ..core.exposure import Portfolio, Exposure, ExposureClass

logger = logging.getLogger(__name__)


class CreditApproach(str, Enum):
    """Credit risk calculation approaches."""
    
    STANDARDIZED = "standardized"
    IRB_FOUNDATION = "irb_foundation"
    IRB_ADVANCED = "irb_advanced"


class CreditRiskCalculator:
    """Calculator for credit risk RWA using various approaches."""
    
    def __init__(self, config: BaselConfig):
        self.config = config
        
    def calculate_total_rwa(self, portfolio: Portfolio, 
                          approach: CreditApproach = CreditApproach.STANDARDIZED) -> float:
        """Calculate total credit RWA for portfolio."""
        if approach == CreditApproach.STANDARDIZED:
            return self.calculate_standardized_rwa(portfolio)
        elif approach in [CreditApproach.IRB_FOUNDATION, CreditApproach.IRB_ADVANCED]:
            return self.calculate_irb_rwa(portfolio, approach)
        else:
            raise ValueError(f"Unknown credit approach: {approach}")
    
    def calculate_standardized_rwa(self, portfolio: Portfolio) -> float:
        """Calculate RWA using Standardized Approach."""
        total_rwa = 0.0
        
        for exposure in portfolio.get_banking_book_exposures():
            # Skip trading book exposures for credit risk
            if exposure.is_trading_book():
                continue
            
            rwa = self._calculate_exposure_sa_rwa(exposure)
            total_rwa += rwa
            
        logger.info(f"Calculated Standardized Approach Credit RWA: {total_rwa:,.0f}")
        return total_rwa
    
    def _calculate_exposure_sa_rwa(self, exposure: Exposure) -> float:
        """Calculate RWA for single exposure using Standardized Approach."""
        # Get Exposure at Default
        ead = exposure.apply_credit_risk_mitigation(self.config)
        
        if ead <= 0:
            return 0.0
        
        # Get risk weight
        risk_weight = self._get_standardized_risk_weight(exposure)
        
        # Calculate RWA
        rwa = ead * risk_weight
        
        return rwa
    
    def _get_standardized_risk_weight(self, exposure: Exposure) -> float:
        """Get risk weight for exposure under Standardized Approach."""
        exposure_class = exposure.exposure_class
        rating = exposure.external_rating
        
        # Map exposure class to risk weight category
        if exposure_class == ExposureClass.SOVEREIGN:
            return self._get_sovereign_risk_weight(rating)
        elif exposure_class == ExposureClass.BANK:
            return self._get_bank_risk_weight(rating)
        elif exposure_class == ExposureClass.CORPORATE:
            return self._get_corporate_risk_weight(rating)
        elif exposure_class == ExposureClass.RETAIL_MORTGAGE:
            return self.config.get_risk_weight("retail_mortgage")
        elif exposure_class == ExposureClass.RETAIL_REVOLVING:
            return self.config.get_risk_weight("retail_qualifying_revolving")
        elif exposure_class == ExposureClass.RETAIL_OTHER:
            return self.config.get_risk_weight("retail_other")
        elif exposure_class == ExposureClass.REAL_ESTATE:
            return self._get_real_estate_risk_weight(exposure)
        elif exposure_class == ExposureClass.PAST_DUE:
            return self._get_past_due_risk_weight(exposure)
        else:
            return self.config.get_risk_weight("other_assets")
    
    def _get_sovereign_risk_weight(self, rating: Optional[str]) -> float:
        """Get sovereign risk weight based on rating."""
        if not rating:
            return self.config.get_risk_weight("sovereign_unrated")
        
        rating_lower = rating.lower()
        if rating_lower in ["aaa", "aa+"]:
            return self.config.get_risk_weight("sovereign_aaa_aa")
        elif rating_lower in ["aa", "aa-", "a+", "a", "a-"]:
            return self.config.get_risk_weight("sovereign_a")
        elif rating_lower in ["bbb+", "bbb", "bbb-", "bb+", "bb", "bb-"]:
            return self.config.get_risk_weight("sovereign_bbb_bb")
        else:
            return self.config.get_risk_weight("sovereign_b_below")
    
    def _get_bank_risk_weight(self, rating: Optional[str]) -> float:
        """Get bank risk weight based on rating."""
        if not rating:
            return self.config.get_risk_weight("bank_unrated")
        
        rating_lower = rating.lower()
        if rating_lower in ["aaa", "aa+", "aa", "aa-"]:
            return self.config.get_risk_weight("bank_aaa_aa")
        elif rating_lower in ["a+", "a", "a-"]:
            return self.config.get_risk_weight("bank_a")
        elif rating_lower in ["bbb+", "bbb", "bbb-", "bb+", "bb", "bb-"]:
            return self.config.get_risk_weight("bank_bbb_bb")
        else:
            return self.config.get_risk_weight("bank_b_below")
    
    def _get_corporate_risk_weight(self, rating: Optional[str]) -> float:
        """Get corporate risk weight based on rating."""
        if not rating:
            return self.config.get_risk_weight("corporate_unrated")
        
        rating_lower = rating.lower()
        if rating_lower in ["aaa", "aa+", "aa", "aa-"]:
            return self.config.get_risk_weight("corporate_aaa_aa")
        elif rating_lower in ["a+", "a", "a-"]:
            return self.config.get_risk_weight("corporate_a")
        elif rating_lower in ["bbb+", "bbb", "bbb-", "bb+", "bb", "bb-"]:
            return self.config.get_risk_weight("corporate_bbb_bb")
        else:
            return self.config.get_risk_weight("corporate_b_below")
    
    def _get_real_estate_risk_weight(self, exposure: Exposure) -> float:
        """Get real estate risk weight."""
        # Check for high volatility commercial real estate
        if exposure.sector and "commercial" in exposure.sector.lower():
            return self.config.get_risk_weight("hvcre", 1.5)
        
        # Residential vs commercial
        if exposure.exposure_class == ExposureClass.RETAIL_MORTGAGE:
            return self.config.get_risk_weight("real_estate_residential")
        else:
            return self.config.get_risk_weight("real_estate_commercial")
    
    def _get_past_due_risk_weight(self, exposure: Exposure) -> float:
        """Get past due risk weight based on collateral."""
        if exposure.crm and exposure.crm.collateral_value:
            return self.config.get_risk_weight("past_due_secured")
        else:
            return self.config.get_risk_weight("past_due_unsecured")
    
    def calculate_irb_rwa(self, portfolio: Portfolio, 
                         approach: CreditApproach) -> float:
        """Calculate RWA using IRB approach (mock implementation)."""
        total_rwa = 0.0
        
        for exposure in portfolio.get_banking_book_exposures():
            if exposure.is_trading_book():
                continue
            
            rwa = self._calculate_exposure_irb_rwa(exposure, approach)
            total_rwa += rwa
        
        logger.info(f"Calculated IRB Credit RWA: {total_rwa:,.0f}")
        return total_rwa
    
    def _calculate_exposure_irb_rwa(self, exposure: Exposure, 
                                  approach: CreditApproach) -> float:
        """Calculate IRB RWA for single exposure (educational mock)."""
        # This is a simplified mock implementation for educational purposes
        # Real IRB models are proprietary and highly complex
        
        pd = exposure.probability_of_default
        lgd = exposure.loss_given_default
        ead = exposure.get_exposure_at_default()
        maturity = exposure.get_effective_maturity()
        
        if not all([pd, lgd, ead]):
            # Fall back to standardized approach
            return self._calculate_exposure_sa_rwa(exposure)
        
        # Mock IRB risk weight calculation (simplified)
        if exposure.is_retail():
            rw = self._calculate_retail_irb_rw(pd, lgd)
        else:
            rw = self._calculate_corporate_irb_rw(pd, lgd, maturity)
        
        # Apply floor (typically 72.5% of SA RWA)
        sa_rwa = self._calculate_exposure_sa_rwa(exposure)
        irb_rwa = ead * rw
        
        return max(irb_rwa, sa_rwa * 0.725)
    
    def _calculate_retail_irb_rw(self, pd: float, lgd: float) -> float:
        """Calculate retail IRB risk weight (mock formula)."""
        # Simplified retail correlation
        correlation = 0.15
        
        # Mock risk weight formula
        n_inv_pd = self._normal_inverse(pd)
        n_inv_999 = self._normal_inverse(0.999)
        
        sqrt_corr = math.sqrt(correlation)
        sqrt_one_minus_corr = math.sqrt(1 - correlation)
        
        conditional_pd = self._normal_cdf(
            (sqrt_corr * n_inv_999 + sqrt_one_minus_corr * n_inv_pd) / sqrt_one_minus_corr
        )
        
        risk_weight = lgd * conditional_pd * 12.5  # 12.5 = 1/0.08
        
        return min(risk_weight, 12.5)  # Cap at 100%
    
    def _calculate_corporate_irb_rw(self, pd: float, lgd: float, maturity: float) -> float:
        """Calculate corporate IRB risk weight (mock formula)."""
        # Simplified corporate correlation
        correlation = 0.24 * (1 - math.exp(-50 * pd)) / (1 - math.exp(-50))
        
        # Maturity adjustment
        b_factor = (0.11852 - 0.05478 * math.log(pd)) ** 2
        maturity_adj = (1 + (maturity - 2.5) * b_factor) / (1 - 1.5 * b_factor)
        
        # Mock risk weight calculation
        n_inv_pd = self._normal_inverse(pd)
        n_inv_999 = self._normal_inverse(0.999)
        
        sqrt_corr = math.sqrt(correlation)
        sqrt_one_minus_corr = math.sqrt(1 - correlation)
        
        conditional_pd = self._normal_cdf(
            (sqrt_corr * n_inv_999 + sqrt_one_minus_corr * n_inv_pd) / sqrt_one_minus_corr
        )
        
        risk_weight = lgd * conditional_pd * maturity_adj * 12.5
        
        return min(risk_weight, 12.5)  # Cap at 100%
    
    def _normal_inverse(self, p: float) -> float:
        """Approximate inverse normal distribution."""
        # Simplified approximation - in practice use scipy.stats.norm.ppf
        if p <= 0:
            return -6.0
        if p >= 1:
            return 6.0
        
        # Beasley-Springer-Moro algorithm approximation
        a = [0, -3.969683028665376e+01, 2.209460984245205e+02,
             -2.759285104469687e+02, 1.383577518672690e+02,
             -3.066479806614716e+01, 2.506628277459239e+00]
        
        b = [0, -5.447609879822406e+01, 1.615858368580409e+02,
             -1.556989798598866e+02, 6.680131188771972e+01,
             -1.328068155288572e+01]
        
        if p < 0.5:
            q = p
        else:
            q = 1 - p
        
        if q > 1e-8:
            w = math.sqrt(-2.0 * math.log(q))
            x = (((((a[6] * w + a[5]) * w + a[4]) * w + a[3]) * w + a[2]) * w + a[1]) * w + a[0]
            x /= ((((b[5] * w + b[4]) * w + b[3]) * w + b[2]) * w + b[1]) * w + 1.0
        else:
            x = 6.0
        
        if p < 0.5:
            return -x
        else:
            return x
    
    def _normal_cdf(self, x: float) -> float:
        """Approximate normal cumulative distribution function."""
        # Simplified approximation - in practice use scipy.stats.norm.cdf
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
    
    def get_detailed_breakdown(self, portfolio: Portfolio) -> Dict[str, Any]:
        """Get detailed breakdown of credit RWA by various dimensions."""
        breakdown = {
            "by_exposure_class": {},
            "by_rating": {},
            "by_geography": {},
            "by_sector": {},
            "total_ead": 0,
            "total_rwa": 0,
            "average_risk_weight": 0
        }
        
        total_ead = 0
        total_rwa = 0
        
        for exposure in portfolio.get_banking_book_exposures():
            if exposure.is_trading_book():
                continue
            
            ead = exposure.apply_credit_risk_mitigation(self.config)
            rwa = self._calculate_exposure_sa_rwa(exposure)
            
            total_ead += ead
            total_rwa += rwa
            
            # Breakdown by exposure class
            exp_class = exposure.exposure_class.value
            if exp_class not in breakdown["by_exposure_class"]:
                breakdown["by_exposure_class"][exp_class] = {"ead": 0, "rwa": 0}
            breakdown["by_exposure_class"][exp_class]["ead"] += ead
            breakdown["by_exposure_class"][exp_class]["rwa"] += rwa
            
            # Breakdown by rating
            rating = exposure.external_rating or "unrated"
            if rating not in breakdown["by_rating"]:
                breakdown["by_rating"][rating] = {"ead": 0, "rwa": 0}
            breakdown["by_rating"][rating]["ead"] += ead
            breakdown["by_rating"][rating]["rwa"] += rwa
            
            # Breakdown by geography
            geography = exposure.geography or "unknown"
            if geography not in breakdown["by_geography"]:
                breakdown["by_geography"][geography] = {"ead": 0, "rwa": 0}
            breakdown["by_geography"][geography]["ead"] += ead
            breakdown["by_geography"][geography]["rwa"] += rwa
            
            # Breakdown by sector
            sector = exposure.sector or "unknown"
            if sector not in breakdown["by_sector"]:
                breakdown["by_sector"][sector] = {"ead": 0, "rwa": 0}
            breakdown["by_sector"][sector]["ead"] += ead
            breakdown["by_sector"][sector]["rwa"] += rwa
        
        breakdown["total_ead"] = total_ead
        breakdown["total_rwa"] = total_rwa
        breakdown["average_risk_weight"] = total_rwa / total_ead if total_ead > 0 else 0
        
        # Add risk weight percentages
        for category in ["by_exposure_class", "by_rating", "by_geography", "by_sector"]:
            for key, values in breakdown[category].items():
                values["risk_weight"] = values["rwa"] / values["ead"] if values["ead"] > 0 else 0
                values["ead_percentage"] = values["ead"] / total_ead if total_ead > 0 else 0
                values["rwa_percentage"] = values["rwa"] / total_rwa if total_rwa > 0 else 0
        
        return breakdown
    
    def calculate_concentration_adjustments(self, portfolio: Portfolio) -> Dict[str, float]:
        """Calculate concentration risk adjustments (Pillar 2)."""
        # This is a simplified concentration risk calculation
        # Real implementations would use more sophisticated models
        
        concentration_metrics = portfolio.get_concentration_metrics()
        
        # Single name concentration
        single_name_addon = 0.0
        if concentration_metrics.get("largest_counterparty_pct", 0) > 0.1:
            excess = concentration_metrics["largest_counterparty_pct"] - 0.1
            single_name_addon = excess * 0.5  # 50% risk weight on excess
        
        # Sector concentration
        sector_addon = 0.0
        if concentration_metrics.get("largest_sector_pct", 0) > 0.25:
            excess = concentration_metrics["largest_sector_pct"] - 0.25
            sector_addon = excess * 0.25  # 25% risk weight on excess
        
        total_exposure = concentration_metrics.get("total_exposure", 0)
        
        return {
            "single_name_addon": single_name_addon * total_exposure,
            "sector_addon": sector_addon * total_exposure,
            "total_concentration_addon": (single_name_addon + sector_addon) * total_exposure
        }
