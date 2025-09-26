"""Market Risk RWA calculations for Basel Capital Engine."""

from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import math
import numpy as np
import logging

from ..core.config import BaselConfig
from ..core.exposure import Portfolio, Exposure, ExposureType

logger = logging.getLogger(__name__)


class MarketRiskApproach(str, Enum):
    """Market risk calculation approaches."""
    
    FRTB_SA = "frtb_sa"           # FRTB Sensitivities-Based Approach
    FRTB_IMA = "frtb_ima"         # FRTB Internal Models Approach
    STANDARDIZED = "standardized"  # Basel II Standardized Approach
    VAR = "var"                   # Value-at-Risk approach


class RiskClass(str, Enum):
    """FRTB risk classes."""
    
    GIRR = "girr"        # General Interest Rate Risk
    CSR_NS = "csr_ns"    # Credit Spread Risk - Non-Securitizations
    CSR_S = "csr_s"      # Credit Spread Risk - Securitizations
    EQ = "equity"        # Equity Risk
    FX = "fx"           # Foreign Exchange Risk
    COMM = "commodity"   # Commodity Risk


class MarketRiskCalculator:
    """Calculator for market risk RWA using FRTB and other approaches."""
    
    def __init__(self, config: BaselConfig):
        self.config = config
        
    def calculate_total_rwa(self, portfolio: Portfolio, 
                          approach: MarketRiskApproach = MarketRiskApproach.FRTB_SA) -> float:
        """Calculate total market risk RWA."""
        trading_exposures = portfolio.get_trading_book_exposures()
        
        if not trading_exposures:
            return 0.0
        
        if approach == MarketRiskApproach.FRTB_SA:
            return self.calculate_frtb_sa_rwa(trading_exposures)
        elif approach == MarketRiskApproach.VAR:
            return self.calculate_var_rwa(trading_exposures)
        elif approach == MarketRiskApproach.STANDARDIZED:
            return self.calculate_standardized_rwa(trading_exposures)
        else:
            raise ValueError(f"Unknown market risk approach: {approach}")
    
    def calculate_frtb_sa_rwa(self, exposures: List[Exposure]) -> float:
        """Calculate RWA using FRTB Sensitivities-Based Approach."""
        # Calculate capital requirement for each risk class
        girr_capital = self._calculate_girr_capital(exposures)
        csr_ns_capital = self._calculate_csr_ns_capital(exposures)
        csr_s_capital = self._calculate_csr_s_capital(exposures)
        eq_capital = self._calculate_equity_capital(exposures)
        fx_capital = self._calculate_fx_capital(exposures)
        comm_capital = self._calculate_commodity_capital(exposures)
        
        # Sum capital requirements
        total_capital = (
            girr_capital + csr_ns_capital + csr_s_capital +
            eq_capital + fx_capital + comm_capital
        )
        
        # Convert to RWA (multiply by 12.5)
        rwa = total_capital * 12.5
        
        logger.info(f"Calculated FRTB SA Market RWA: {rwa:,.0f}")
        return rwa
    
    def _calculate_girr_capital(self, exposures: List[Exposure]) -> float:
        """Calculate General Interest Rate Risk capital."""
        # Group sensitivities by currency and tenor
        sensitivities_by_currency = {}
        
        for exposure in exposures:
            if not self._has_interest_rate_risk(exposure):
                continue
            
            currency = exposure.currency
            if currency not in sensitivities_by_currency:
                sensitivities_by_currency[currency] = {}
            
            # Extract delta sensitivities by tenor
            ir_sensitivities = self._extract_ir_sensitivities(exposure)
            for tenor, sensitivity in ir_sensitivities.items():
                if tenor not in sensitivities_by_currency[currency]:
                    sensitivities_by_currency[currency][tenor] = 0
                sensitivities_by_currency[currency][tenor] += sensitivity
        
        # Calculate capital for each currency
        total_capital = 0
        for currency, tenors in sensitivities_by_currency.items():
            capital = self._calculate_currency_girr_capital(tenors)
            total_capital += capital
        
        return total_capital
    
    def _calculate_currency_girr_capital(self, tenor_sensitivities: Dict[str, float]) -> float:
        """Calculate GIRR capital for a single currency."""
        # Get risk weights
        risk_weights = self.config.risk_weights.get("market", {}).get("ir_risk_weights", {})
        
        # Calculate weighted sensitivities
        weighted_sensitivities = []
        for tenor, sensitivity in tenor_sensitivities.items():
            risk_weight = risk_weights.get(tenor, 1.0)
            weighted_sensitivity = sensitivity * risk_weight
            weighted_sensitivities.append(weighted_sensitivity)
        
        if not weighted_sensitivities:
            return 0
        
        # Apply correlation and aggregation
        # Simplified: sum of absolute weighted sensitivities with correlation adjustments
        correlations = self.config.correlations.get("ir_correlations", {})
        same_bucket_corr = correlations.get("same_bucket", 0.99)
        
        # For simplicity, assume all tenors are in the same bucket
        sum_ws = sum(weighted_sensitivities)
        sum_abs_ws = sum(abs(ws) for ws in weighted_sensitivities)
        
        # Capital charge with correlation
        capital = math.sqrt(same_bucket_corr * sum_ws**2 + (1 - same_bucket_corr) * sum_abs_ws**2)
        
        return capital
    
    def _calculate_csr_ns_capital(self, exposures: List[Exposure]) -> float:
        """Calculate Credit Spread Risk - Non-Securitizations capital."""
        # Group by issuer and rating
        sensitivities_by_issuer = {}
        
        for exposure in exposures:
            if not self._has_credit_spread_risk(exposure):
                continue
            
            issuer = exposure.counterparty_id or "unknown"
            if issuer not in sensitivities_by_issuer:
                sensitivities_by_issuer[issuer] = 0
            
            # Extract credit spread delta
            credit_delta = self._extract_credit_spread_delta(exposure)
            sensitivities_by_issuer[issuer] += credit_delta
        
        # Calculate capital
        risk_weight = self.config.risk_weights.get("market", {}).get("credit_spread_ig", 0.005)
        
        total_capital = 0
        for issuer, sensitivity in sensitivities_by_issuer.items():
            weighted_sensitivity = sensitivity * risk_weight
            total_capital += abs(weighted_sensitivity)  # Simplified aggregation
        
        return total_capital
    
    def _calculate_csr_s_capital(self, exposures: List[Exposure]) -> float:
        """Calculate Credit Spread Risk - Securitizations capital."""
        # Simplified - assume no securitizations for now
        return 0.0
    
    def _calculate_equity_capital(self, exposures: List[Exposure]) -> float:
        """Calculate Equity Risk capital."""
        sensitivities_by_name = {}
        
        for exposure in exposures:
            if not self._has_equity_risk(exposure):
                continue
            
            equity_name = exposure.counterparty_id or "unknown"
            if equity_name not in sensitivities_by_name:
                sensitivities_by_name[equity_name] = 0
            
            # Extract equity delta
            equity_delta = self._extract_equity_delta(exposure)
            sensitivities_by_name[equity_name] += equity_delta
        
        # Calculate capital with risk weights
        risk_weights = self.config.risk_weights.get("market", {})
        large_cap_rw = risk_weights.get("equity_large_cap", 0.25)
        
        total_capital = 0
        for name, sensitivity in sensitivities_by_name.items():
            # Assume large cap for simplicity
            weighted_sensitivity = sensitivity * large_cap_rw
            total_capital += abs(weighted_sensitivity)
        
        return total_capital
    
    def _calculate_fx_capital(self, exposures: List[Exposure]) -> float:
        """Calculate Foreign Exchange Risk capital."""
        sensitivities_by_currency = {}
        
        for exposure in exposures:
            if not self._has_fx_risk(exposure):
                continue
            
            currency = exposure.currency
            if currency not in sensitivities_by_currency:
                sensitivities_by_currency[currency] = 0
            
            # Extract FX delta
            fx_delta = self._extract_fx_delta(exposure)
            sensitivities_by_currency[currency] += fx_delta
        
        # Calculate capital
        fx_risk_weight = self.config.risk_weights.get("market", {}).get("fx_risk_weight", 0.15)
        
        total_capital = 0
        for currency, sensitivity in sensitivities_by_currency.items():
            weighted_sensitivity = sensitivity * fx_risk_weight
            total_capital += abs(weighted_sensitivity)
        
        return total_capital
    
    def _calculate_commodity_capital(self, exposures: List[Exposure]) -> float:
        """Calculate Commodity Risk capital."""
        # Simplified - assume no commodity exposures for now
        return 0.0
    
    def calculate_var_rwa(self, exposures: List[Exposure]) -> float:
        """Calculate RWA using Value-at-Risk approach."""
        # This is a simplified VaR calculation for demonstration
        # Real implementations would use historical simulation or Monte Carlo
        
        # Calculate portfolio value
        portfolio_value = sum(exp.market_value or exp.current_exposure for exp in exposures)
        
        if portfolio_value <= 0:
            return 0.0
        
        # Simplified VaR calculation (assume 2% daily VaR)
        daily_var = portfolio_value * 0.02
        
        # Scale to 10-day VaR (regulatory requirement)
        ten_day_var = daily_var * math.sqrt(10)
        
        # Apply multiplier (typically 3-4)
        multiplier = 3.0
        capital_requirement = ten_day_var * multiplier
        
        # Convert to RWA
        rwa = capital_requirement * 12.5
        
        logger.info(f"Calculated VaR Market RWA: {rwa:,.0f}")
        return rwa
    
    def calculate_standardized_rwa(self, exposures: List[Exposure]) -> float:
        """Calculate RWA using Basel II Standardized Approach."""
        # Simplified Basel II standardized approach
        total_capital = 0
        
        for exposure in exposures:
            # Interest rate risk
            if self._has_interest_rate_risk(exposure):
                ir_capital = self._calculate_basel2_interest_rate_risk(exposure)
                total_capital += ir_capital
            
            # Equity risk
            if self._has_equity_risk(exposure):
                eq_capital = self._calculate_basel2_equity_risk(exposure)
                total_capital += eq_capital
            
            # FX risk
            if self._has_fx_risk(exposure):
                fx_capital = self._calculate_basel2_fx_risk(exposure)
                total_capital += fx_capital
        
        # Convert to RWA
        rwa = total_capital * 12.5
        
        logger.info(f"Calculated Basel II Standardized Market RWA: {rwa:,.0f}")
        return rwa
    
    def _calculate_basel2_interest_rate_risk(self, exposure: Exposure) -> float:
        """Calculate Basel II interest rate risk capital."""
        # Simplified duration-based approach
        market_value = exposure.market_value or exposure.current_exposure
        duration = getattr(exposure, 'duration', 5.0)  # Default 5-year duration
        
        # Assume 200bp interest rate shock
        ir_shock = 0.02
        capital = market_value * duration * ir_shock
        
        return capital
    
    def _calculate_basel2_equity_risk(self, exposure: Exposure) -> float:
        """Calculate Basel II equity risk capital."""
        market_value = exposure.market_value or exposure.current_exposure
        
        # Basel II equity risk charge (typically 8% for specific risk)
        specific_risk_charge = 0.08
        
        return market_value * specific_risk_charge
    
    def _calculate_basel2_fx_risk(self, exposure: Exposure) -> float:
        """Calculate Basel II FX risk capital."""
        market_value = exposure.market_value or exposure.current_exposure
        
        # Basel II FX risk charge (typically 8%)
        fx_risk_charge = 0.08
        
        return market_value * fx_risk_charge
    
    # Helper methods for extracting sensitivities and risk identification
    
    def _has_interest_rate_risk(self, exposure: Exposure) -> bool:
        """Check if exposure has interest rate risk."""
        return (
            exposure.exposure_type in [ExposureType.SECURITIES, ExposureType.TRADING_SECURITIES] or
            (exposure.sensitivities and any("ir_" in key for key in exposure.sensitivities.keys()))
        )
    
    def _has_credit_spread_risk(self, exposure: Exposure) -> bool:
        """Check if exposure has credit spread risk."""
        return (
            exposure.exposure_class.value in ["corporate", "bank"] and
            exposure.exposure_type in [ExposureType.SECURITIES, ExposureType.TRADING_SECURITIES]
        )
    
    def _has_equity_risk(self, exposure: Exposure) -> bool:
        """Check if exposure has equity risk."""
        return (
            exposure.exposure_class.value == "equity" or
            (exposure.sensitivities and any("eq_" in key for key in exposure.sensitivities.keys()))
        )
    
    def _has_fx_risk(self, exposure: Exposure) -> bool:
        """Check if exposure has FX risk."""
        return (
            exposure.currency != "EUR" or  # Assuming EUR is base currency
            (exposure.sensitivities and any("fx_" in key for key in exposure.sensitivities.keys()))
        )
    
    def _extract_ir_sensitivities(self, exposure: Exposure) -> Dict[str, float]:
        """Extract interest rate sensitivities by tenor."""
        if not exposure.sensitivities:
            # Default sensitivity based on market value and assumed duration
            market_value = exposure.market_value or exposure.current_exposure
            duration = getattr(exposure, 'duration', 5.0)
            return {"5y": market_value * duration * 0.0001}  # 1bp sensitivity
        
        # Extract IR sensitivities
        ir_sensitivities = {}
        for key, value in exposure.sensitivities.items():
            if key.startswith("ir_"):
                tenor = key.replace("ir_", "")
                ir_sensitivities[tenor] = value
        
        return ir_sensitivities
    
    def _extract_credit_spread_delta(self, exposure: Exposure) -> float:
        """Extract credit spread delta sensitivity."""
        if exposure.sensitivities and "credit_spread" in exposure.sensitivities:
            return exposure.sensitivities["credit_spread"]
        
        # Default based on market value and spread duration
        market_value = exposure.market_value or exposure.current_exposure
        spread_duration = getattr(exposure, 'spread_duration', 3.0)
        return market_value * spread_duration * 0.0001  # 1bp sensitivity
    
    def _extract_equity_delta(self, exposure: Exposure) -> float:
        """Extract equity delta sensitivity."""
        if exposure.sensitivities and "equity_delta" in exposure.sensitivities:
            return exposure.sensitivities["equity_delta"]
        
        # Default: 1% move sensitivity
        market_value = exposure.market_value or exposure.current_exposure
        return market_value * 0.01
    
    def _extract_fx_delta(self, exposure: Exposure) -> float:
        """Extract FX delta sensitivity."""
        if exposure.sensitivities and "fx_delta" in exposure.sensitivities:
            return exposure.sensitivities["fx_delta"]
        
        # Default: 1% FX move sensitivity
        market_value = exposure.market_value or exposure.current_exposure
        return market_value * 0.01
    
    def get_detailed_breakdown(self, portfolio: Portfolio) -> Dict[str, Any]:
        """Get detailed breakdown of market RWA by risk class and desk."""
        trading_exposures = portfolio.get_trading_book_exposures()
        
        breakdown = {
            "by_risk_class": {
                "girr": 0,
                "csr_ns": 0, 
                "csr_s": 0,
                "equity": 0,
                "fx": 0,
                "commodity": 0
            },
            "by_currency": {},
            "by_desk": {},
            "total_market_value": 0,
            "total_rwa": 0
        }
        
        # Calculate by risk class
        breakdown["by_risk_class"]["girr"] = self._calculate_girr_capital(trading_exposures) * 12.5
        breakdown["by_risk_class"]["csr_ns"] = self._calculate_csr_ns_capital(trading_exposures) * 12.5
        breakdown["by_risk_class"]["csr_s"] = self._calculate_csr_s_capital(trading_exposures) * 12.5
        breakdown["by_risk_class"]["equity"] = self._calculate_equity_capital(trading_exposures) * 12.5
        breakdown["by_risk_class"]["fx"] = self._calculate_fx_capital(trading_exposures) * 12.5
        breakdown["by_risk_class"]["commodity"] = self._calculate_commodity_capital(trading_exposures) * 12.5
        
        # Calculate totals and other breakdowns
        total_market_value = 0
        total_rwa = sum(breakdown["by_risk_class"].values())
        
        for exposure in trading_exposures:
            market_value = exposure.market_value or exposure.current_exposure
            total_market_value += market_value
            
            # By currency
            currency = exposure.currency
            if currency not in breakdown["by_currency"]:
                breakdown["by_currency"][currency] = {"market_value": 0, "rwa": 0}
            breakdown["by_currency"][currency]["market_value"] += market_value
            # Simplified RWA allocation by market value
            rwa_allocation = (market_value / total_market_value * total_rwa) if total_market_value > 0 else 0
            breakdown["by_currency"][currency]["rwa"] += rwa_allocation
            
            # By desk/business line
            desk = exposure.business_line or "unknown"
            if desk not in breakdown["by_desk"]:
                breakdown["by_desk"][desk] = {"market_value": 0, "rwa": 0}
            breakdown["by_desk"][desk]["market_value"] += market_value
            breakdown["by_desk"][desk]["rwa"] += rwa_allocation
        
        breakdown["total_market_value"] = total_market_value
        breakdown["total_rwa"] = total_rwa
        
        return breakdown
    
    def calculate_stressed_var(self, exposures: List[Exposure], 
                             stress_scenario: Dict[str, float]) -> float:
        """Calculate Stressed VaR under specific scenario."""
        # This would implement stressed VaR calculation
        # For now, return a simple stressed version of base VaR
        
        base_var_rwa = self.calculate_var_rwa(exposures)
        
        # Apply stress multipliers
        stress_multiplier = 1.0
        for risk_factor, shock in stress_scenario.items():
            if risk_factor == "interest_rate":
                stress_multiplier *= (1 + abs(shock) / 100)  # Convert bps to decimal
            elif risk_factor in ["equity_shock", "fx_shock"]:
                stress_multiplier *= (1 + abs(shock))
        
        stressed_var_rwa = base_var_rwa * stress_multiplier
        
        logger.info(f"Calculated Stressed VaR RWA: {stressed_var_rwa:,.0f}")
        return stressed_var_rwa
