"""Operational Risk RWA calculations for Basel Capital Engine."""

from typing import Dict, Any, List, Optional
from enum import Enum
import math
import logging

from ..core.config import BaselConfig
from ..core.exposure import Portfolio

logger = logging.getLogger(__name__)


class OperationalRiskApproach(str, Enum):
    """Operational risk calculation approaches."""
    
    SMA = "sma"                    # Standardized Measurement Approach
    AMA = "ama"                    # Advanced Measurement Approach (legacy)
    BASIC_INDICATOR = "basic"      # Basic Indicator Approach (legacy)


class BusinessLine(str, Enum):
    """Business lines for operational risk."""
    
    CORPORATE_FINANCE = "corporate_finance"
    TRADING_SALES = "trading_sales"
    RETAIL_BANKING = "retail_banking"
    COMMERCIAL_BANKING = "commercial_banking"
    PAYMENT_SETTLEMENT = "payment_settlement"
    AGENCY_SERVICES = "agency_services"
    ASSET_MANAGEMENT = "asset_management"
    RETAIL_BROKERAGE = "retail_brokerage"


class OperationalRiskCalculator:
    """Calculator for operational risk RWA using SMA and other approaches."""
    
    def __init__(self, config: BaselConfig):
        self.config = config
    
    def calculate_rwa(self, portfolio: Portfolio, 
                     financial_data: Optional[Dict[str, float]] = None,
                     approach: OperationalRiskApproach = OperationalRiskApproach.SMA) -> float:
        """Calculate operational risk RWA."""
        if approach == OperationalRiskApproach.SMA:
            return self.calculate_sma_rwa(portfolio, financial_data)
        elif approach == OperationalRiskApproach.BASIC_INDICATOR:
            return self.calculate_basic_indicator_rwa(financial_data)
        elif approach == OperationalRiskApproach.AMA:
            return self.calculate_ama_rwa(portfolio, financial_data)
        else:
            raise ValueError(f"Unknown operational risk approach: {approach}")
    
    def calculate_sma_rwa(self, portfolio: Portfolio, 
                         financial_data: Optional[Dict[str, float]] = None) -> float:
        """Calculate RWA using Standardized Measurement Approach (SMA)."""
        # Calculate Business Indicator Component (BIC)
        bic = self.calculate_business_indicator_component(portfolio, financial_data)
        
        # Calculate Internal Loss Multiplier (ILM)
        ilm = self.calculate_internal_loss_multiplier(financial_data)
        
        # Calculate SMA capital requirement
        sma_capital = bic * ilm
        
        # Convert to RWA (multiply by 12.5)
        rwa = sma_capital * 12.5
        
        logger.info(f"Calculated SMA Operational RWA: {rwa:,.0f} (BIC: {bic:,.0f}, ILM: {ilm:.3f})")
        return rwa
    
    def calculate_business_indicator_component(self, portfolio: Portfolio,
                                            financial_data: Optional[Dict[str, float]] = None) -> float:
        """Calculate Business Indicator Component (BIC)."""
        # Calculate Business Indicator (BI)
        bi = self.calculate_business_indicator(portfolio, financial_data)
        
        # Get BIC thresholds and coefficients from config
        op_risk_config = self.config.operational_risk
        bucket_1_threshold = op_risk_config.get("bic_thresholds", {}).get("bucket_1", 1000) * 1e6  # €1bn
        bucket_2_threshold = op_risk_config.get("bic_thresholds", {}).get("bucket_2", 30000) * 1e6  # €30bn
        
        marginal_coeffs = op_risk_config.get("marginal_coefficients", {})
        alpha_1 = marginal_coeffs.get("bucket_1", 0.12)
        alpha_2 = marginal_coeffs.get("bucket_2", 0.15)
        alpha_3 = marginal_coeffs.get("bucket_3", 0.18)
        
        # Calculate BIC using marginal approach
        if bi <= bucket_1_threshold:
            bic = bi * alpha_1
        elif bi <= bucket_2_threshold:
            bic = bucket_1_threshold * alpha_1 + (bi - bucket_1_threshold) * alpha_2
        else:
            bic = (bucket_1_threshold * alpha_1 + 
                   (bucket_2_threshold - bucket_1_threshold) * alpha_2 +
                   (bi - bucket_2_threshold) * alpha_3)
        
        return bic
    
    def calculate_business_indicator(self, portfolio: Portfolio,
                                   financial_data: Optional[Dict[str, float]] = None) -> float:
        """Calculate Business Indicator (BI) from financial data."""
        if financial_data:
            # Use provided financial data
            interest_income = financial_data.get("interest_income", 0)
            interest_expense = financial_data.get("interest_expense", 0)
            dividend_income = financial_data.get("dividend_income", 0)
            fee_income = financial_data.get("fee_income", 0)
            fee_expense = financial_data.get("fee_expense", 0)
            trading_income = financial_data.get("trading_income", 0)
            other_income = financial_data.get("other_income", 0)
            other_expense = financial_data.get("other_expense", 0)
            
            # BI calculation according to Basel III
            ildc = interest_income + dividend_income  # Interest, lease and dividend component
            sctb = max(0, fee_income - fee_expense)   # Services component
            fb = abs(trading_income) + abs(other_income - other_expense)  # Financial component
            
            bi = ildc + sctb + fb
        else:
            # Estimate BI from portfolio data (simplified approach)
            bi = self._estimate_bi_from_portfolio(portfolio)
        
        return max(0, bi)
    
    def _estimate_bi_from_portfolio(self, portfolio: Portfolio) -> float:
        """Estimate Business Indicator from portfolio characteristics."""
        # This is a simplified estimation - real implementation would use actual P&L data
        
        total_exposure = portfolio.get_total_exposure()
        
        # Rough estimates based on typical bank metrics
        estimated_net_interest_margin = 0.025  # 2.5%
        estimated_fee_ratio = 0.01  # 1% of assets
        estimated_trading_ratio = 0.005  # 0.5% of assets
        
        estimated_bi = total_exposure * (
            estimated_net_interest_margin + 
            estimated_fee_ratio + 
            estimated_trading_ratio
        )
        
        return estimated_bi
    
    def calculate_internal_loss_multiplier(self, financial_data: Optional[Dict[str, float]] = None) -> float:
        """Calculate Internal Loss Multiplier (ILM)."""
        if not financial_data or "historical_losses" not in financial_data:
            # Return default ILM of 1.0 if no loss data
            return 1.0
        
        historical_losses = financial_data["historical_losses"]
        
        # Get Loss Component threshold from config
        op_risk_config = self.config.operational_risk
        loss_threshold = op_risk_config.get("ilm", {}).get("loss_component_threshold", 20) * 1e6  # €20m
        
        if historical_losses <= loss_threshold:
            return 1.0
        
        # Calculate Loss Component (LC)
        lc = historical_losses
        
        # Calculate BIC for ILM calculation (simplified - should use same BI as BIC calculation)
        bi = financial_data.get("business_indicator", 0)
        if bi <= 0:
            return 1.0
        
        # Calculate ILM
        alpha = op_risk_config.get("ilm", {}).get("alpha", 0.2)
        ilm = math.log(math.exp(1) - 1 + (lc / bi) ** alpha)
        
        # ILM is bounded between 1 and 5
        return max(1.0, min(5.0, ilm))
    
    def calculate_basic_indicator_rwa(self, financial_data: Optional[Dict[str, float]] = None) -> float:
        """Calculate RWA using Basic Indicator Approach (legacy Basel II)."""
        if not financial_data:
            logger.warning("No financial data provided for Basic Indicator Approach")
            return 0.0
        
        # Average gross income over 3 years
        gross_incomes = []
        for year in ["year_1", "year_2", "year_3"]:
            gross_income = financial_data.get(f"gross_income_{year}", 0)
            if gross_income > 0:  # Only include positive years
                gross_incomes.append(gross_income)
        
        if not gross_incomes:
            return 0.0
        
        average_gross_income = sum(gross_incomes) / len(gross_incomes)
        
        # Basic Indicator coefficient (15%)
        alpha = 0.15
        
        # Calculate capital requirement
        capital_requirement = average_gross_income * alpha
        
        # Convert to RWA
        rwa = capital_requirement * 12.5
        
        logger.info(f"Calculated Basic Indicator Operational RWA: {rwa:,.0f}")
        return rwa
    
    def calculate_ama_rwa(self, portfolio: Portfolio, 
                         financial_data: Optional[Dict[str, float]] = None) -> float:
        """Calculate RWA using Advanced Measurement Approach (simplified mock)."""
        # AMA is highly bank-specific and uses internal models
        # This is a simplified mock implementation
        
        total_exposure = portfolio.get_total_exposure()
        
        # Mock AMA calculation based on exposure and loss history
        base_capital_ratio = 0.015  # 1.5% of total exposure as base
        
        if financial_data and "historical_losses" in financial_data:
            # Adjust based on loss history
            historical_losses = financial_data["historical_losses"]
            loss_ratio = historical_losses / total_exposure if total_exposure > 0 else 0
            
            # Scale capital requirement based on loss experience
            capital_ratio = base_capital_ratio * (1 + loss_ratio * 10)  # Amplify loss impact
        else:
            capital_ratio = base_capital_ratio
        
        capital_requirement = total_exposure * capital_ratio
        rwa = capital_requirement * 12.5
        
        logger.info(f"Calculated AMA Operational RWA: {rwa:,.0f}")
        return rwa
    
    def get_detailed_breakdown(self, portfolio: Portfolio, 
                             financial_data: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """Get detailed breakdown of operational risk calculation."""
        # Calculate main components
        bi = self.calculate_business_indicator(portfolio, financial_data)
        bic = self.calculate_business_indicator_component(portfolio, financial_data)
        ilm = self.calculate_internal_loss_multiplier(financial_data)
        sma_capital = bic * ilm
        rwa = sma_capital * 12.5
        
        # BIC bucket analysis
        op_risk_config = self.config.operational_risk
        bucket_1_threshold = op_risk_config.get("bic_thresholds", {}).get("bucket_1", 1000) * 1e6
        bucket_2_threshold = op_risk_config.get("bic_thresholds", {}).get("bucket_2", 30000) * 1e6
        
        if bi <= bucket_1_threshold:
            bucket = "Bucket 1"
            marginal_rate = op_risk_config.get("marginal_coefficients", {}).get("bucket_1", 0.12)
        elif bi <= bucket_2_threshold:
            bucket = "Bucket 2"
            marginal_rate = op_risk_config.get("marginal_coefficients", {}).get("bucket_2", 0.15)
        else:
            bucket = "Bucket 3"
            marginal_rate = op_risk_config.get("marginal_coefficients", {}).get("bucket_3", 0.18)
        
        breakdown = {
            "business_indicator": bi,
            "bic_bucket": bucket,
            "marginal_coefficient": marginal_rate,
            "business_indicator_component": bic,
            "internal_loss_multiplier": ilm,
            "sma_capital_requirement": sma_capital,
            "operational_rwa": rwa,
            "bi_components": self._get_bi_components(portfolio, financial_data),
            "ilm_details": self._get_ilm_details(financial_data)
        }
        
        return breakdown
    
    def _get_bi_components(self, portfolio: Portfolio, 
                          financial_data: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        """Get breakdown of Business Indicator components."""
        if financial_data:
            interest_income = financial_data.get("interest_income", 0)
            dividend_income = financial_data.get("dividend_income", 0)
            fee_income = financial_data.get("fee_income", 0)
            fee_expense = financial_data.get("fee_expense", 0)
            trading_income = financial_data.get("trading_income", 0)
            other_income = financial_data.get("other_income", 0)
            other_expense = financial_data.get("other_expense", 0)
            
            return {
                "interest_lease_dividend_component": interest_income + dividend_income,
                "services_component": max(0, fee_income - fee_expense),
                "financial_component": abs(trading_income) + abs(other_income - other_expense),
                "total_business_indicator": (
                    interest_income + dividend_income + 
                    max(0, fee_income - fee_expense) +
                    abs(trading_income) + abs(other_income - other_expense)
                )
            }
        else:
            # Estimated components
            total_exposure = portfolio.get_total_exposure()
            return {
                "interest_lease_dividend_component": total_exposure * 0.025,
                "services_component": total_exposure * 0.01,
                "financial_component": total_exposure * 0.005,
                "total_business_indicator": total_exposure * 0.04
            }
    
    def _get_ilm_details(self, financial_data: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """Get details of Internal Loss Multiplier calculation."""
        if not financial_data or "historical_losses" not in financial_data:
            return {
                "historical_losses": 0,
                "loss_component_threshold": self.config.operational_risk.get("ilm", {}).get("loss_component_threshold", 20) * 1e6,
                "ilm_applicable": False,
                "ilm_value": 1.0
            }
        
        historical_losses = financial_data["historical_losses"]
        threshold = self.config.operational_risk.get("ilm", {}).get("loss_component_threshold", 20) * 1e6
        
        return {
            "historical_losses": historical_losses,
            "loss_component_threshold": threshold,
            "ilm_applicable": historical_losses > threshold,
            "ilm_value": self.calculate_internal_loss_multiplier(financial_data),
            "alpha_parameter": self.config.operational_risk.get("ilm", {}).get("alpha", 0.2)
        }
    
    def simulate_bi_scenarios(self, portfolio: Portfolio, 
                            scenario_adjustments: Dict[str, float]) -> Dict[str, Any]:
        """Simulate operational RWA under different Business Indicator scenarios."""
        base_bi = self._estimate_bi_from_portfolio(portfolio)
        
        scenarios = {}
        for scenario_name, adjustment in scenario_adjustments.items():
            adjusted_bi = base_bi * (1 + adjustment)
            adjusted_bic = self.calculate_business_indicator_component(
                portfolio, {"business_indicator": adjusted_bi}
            )
            adjusted_rwa = adjusted_bic * 12.5  # Assuming ILM = 1
            
            scenarios[scenario_name] = {
                "business_indicator": adjusted_bi,
                "bic": adjusted_bic,
                "rwa": adjusted_rwa,
                "rwa_change": adjusted_rwa - (self.calculate_business_indicator_component(
                    portfolio, {"business_indicator": base_bi}
                ) * 12.5)
            }
        
        return {
            "base_scenario": {
                "business_indicator": base_bi,
                "bic": self.calculate_business_indicator_component(
                    portfolio, {"business_indicator": base_bi}
                ),
                "rwa": self.calculate_business_indicator_component(
                    portfolio, {"business_indicator": base_bi}
                ) * 12.5
            },
            "scenarios": scenarios
        }
