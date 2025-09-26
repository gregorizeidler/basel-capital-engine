"""Services for Basel Capital Engine API."""

from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import asyncio

from basileia.core.engine import BaselEngine
from basileia.core.exposure import Portfolio, Exposure, ExposureType, ExposureClass, CreditRiskMitigation
from basileia.core.capital import Capital, CapitalComponents
from basileia.core.buffers import RegulatoryBuffers
from basileia.core.config import BaselConfig
from basileia.stress.engine import StressTestEngine
from basileia.stress.scenarios import get_scenario, list_available_scenarios, create_custom_scenario
from .models import (
    PortfolioData, CapitalData, BufferData, OperationalRiskData,
    CapitalRatiosResponse, RWABreakdownResponse, BufferAnalysisResponse
)

logger = logging.getLogger(__name__)


class BaselCalculationService:
    """Service for Basel capital calculations."""
    
    def __init__(self):
        self.basel_engine = None
        self.config = None
    
    async def initialize(self):
        """Initialize the service."""
        try:
            self.config = BaselConfig.load_default()
            self.basel_engine = BaselEngine(self.config)
            logger.info("Basel calculation service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Basel calculation service: {str(e)}")
            raise
    
    async def calculate_basel_metrics(self, portfolio_data: PortfolioData, 
                                    capital_data: CapitalData,
                                    buffers_data: Optional[BufferData] = None,
                                    operational_risk_data: Optional[OperationalRiskData] = None,
                                    config_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Calculate Basel metrics for portfolio."""
        try:
            # Convert API models to core models
            portfolio = self._convert_portfolio_data(portfolio_data)
            capital = self._convert_capital_data(capital_data)
            buffers = self._convert_buffer_data(buffers_data) if buffers_data else RegulatoryBuffers()
            
            # Apply config overrides if provided
            if config_overrides:
                # Create modified config (simplified - would need proper deep merge)
                config = self.config.model_copy()
                # Apply overrides - this is simplified
                for key, value in config_overrides.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
                
                # Create new engine with modified config
                engine = BaselEngine(config)
            else:
                engine = self.basel_engine
            
            # Add operational risk data if provided
            op_risk_financial_data = None
            if operational_risk_data:
                op_risk_financial_data = {
                    "interest_income": operational_risk_data.interest_income,
                    "interest_expense": operational_risk_data.interest_expense,
                    "dividend_income": operational_risk_data.dividend_income,
                    "fee_income": operational_risk_data.fee_income,
                    "fee_expense": operational_risk_data.fee_expense,
                    "trading_income": operational_risk_data.trading_income,
                    "other_income": operational_risk_data.other_income,
                    "other_expense": operational_risk_data.other_expense,
                    "historical_losses": operational_risk_data.historical_losses,
                    "gross_income_year_1": operational_risk_data.gross_income_year_1,
                    "gross_income_year_2": operational_risk_data.gross_income_year_2,
                    "gross_income_year_3": operational_risk_data.gross_income_year_3
                }
            
            # Calculate operational RWA separately if we have financial data
            if op_risk_financial_data:
                operational_rwa = engine.operational_calculator.calculate_rwa(
                    portfolio, op_risk_financial_data
                )
            else:
                operational_rwa = engine.operational_calculator.calculate_rwa(portfolio)
            
            # Calculate other RWAs
            credit_rwa = engine.credit_calculator.calculate_total_rwa(portfolio)
            market_rwa = engine.market_calculator.calculate_total_rwa(portfolio)
            total_rwa = credit_rwa + market_rwa + operational_rwa
            
            # Calculate capital amounts
            cet1_capital = capital.calculate_cet1_capital()
            tier1_capital = capital.calculate_tier1_capital()
            total_capital = capital.calculate_total_capital()
            
            # Calculate ratios
            cet1_ratio = cet1_capital / total_rwa if total_rwa > 0 else 0
            tier1_ratio = tier1_capital / total_rwa if total_rwa > 0 else 0
            basel_ratio = total_capital / total_rwa if total_rwa > 0 else 0
            
            # Calculate leverage ratio
            from ..metrics.ratios import LeverageRatio
            leverage_calculator = LeverageRatio(self.config)
            leverage_results = leverage_calculator.calculate(portfolio, capital)
            
            # Buffer analysis
            buffer_breaches = buffers.check_buffer_breaches(
                cet1_ratio, tier1_ratio, basel_ratio, total_rwa
            )
            mda_restrictions = buffers.get_mda_restrictions(buffer_breaches)
            capital_shortfall = sum(breach.shortfall_amount for breach in buffer_breaches)
            
            # Get detailed breakdowns
            credit_breakdown = engine.credit_calculator.get_detailed_breakdown(portfolio)
            market_breakdown = engine.market_calculator.get_detailed_breakdown(portfolio)
            operational_breakdown = engine.operational_calculator.get_detailed_breakdown(
                portfolio, op_risk_financial_data
            )
            
            # Create response data
            results = {
                "cet1_capital": cet1_capital,
                "tier1_capital": tier1_capital,
                "total_capital": total_capital,
                "ratios": CapitalRatiosResponse(
                    cet1_ratio=cet1_ratio,
                    tier1_ratio=tier1_ratio,
                    total_capital_ratio=basel_ratio,
                    leverage_ratio=leverage_results.leverage_ratio,
                    cet1_excess_bps=(cet1_ratio - self.config.get_minimum_ratio("cet1_minimum")) * 10000,
                    tier1_excess_bps=(tier1_ratio - self.config.get_minimum_ratio("tier1_minimum")) * 10000,
                    total_excess_bps=(basel_ratio - self.config.get_minimum_ratio("total_capital_minimum")) * 10000,
                    leverage_excess_bps=(leverage_results.leverage_ratio - self.config.get_minimum_ratio("leverage_minimum")) * 10000
                ),
                "rwa": RWABreakdownResponse(
                    credit_rwa=credit_rwa,
                    market_rwa=market_rwa,
                    operational_rwa=operational_rwa,
                    total_rwa=total_rwa,
                    credit_breakdown=credit_breakdown,
                    market_breakdown=market_breakdown,
                    operational_breakdown=operational_breakdown
                ),
                "buffers": BufferAnalysisResponse(
                    buffer_requirements=buffers.get_buffer_breakdown(),
                    buffer_breaches=[{
                        "buffer_type": breach.buffer_type.value,
                        "required_ratio": breach.required_ratio,
                        "actual_ratio": breach.actual_ratio,
                        "shortfall_amount": breach.shortfall_amount,
                        "shortfall_bps": breach.shortfall_ratio * 10000
                    } for breach in buffer_breaches],
                    mda_restrictions=mda_restrictions,
                    capital_shortfall=capital_shortfall
                ),
                "meets_minimum_requirements": (
                    cet1_ratio >= self.config.get_minimum_ratio("cet1_minimum") and
                    tier1_ratio >= self.config.get_minimum_ratio("tier1_minimum") and
                    basel_ratio >= self.config.get_minimum_ratio("total_capital_minimum") and
                    leverage_results.leverage_ratio >= self.config.get_minimum_ratio("leverage_minimum")
                ),
                "bank_name": portfolio_data.bank_name,
                "portfolio_summary": {
                    "total_exposures": len(portfolio_data.exposures),
                    "total_exposure_amount": sum(exp.current_exposure for exp in portfolio_data.exposures),
                    "currencies": list(set(exp.currency for exp in portfolio_data.exposures)),
                    "exposure_types": list(set(exp.exposure_type for exp in portfolio_data.exposures)),
                    "sectors": list(set(exp.sector for exp in portfolio_data.exposures if exp.sector)),
                    "average_risk_weight": total_rwa / sum(exp.current_exposure for exp in portfolio_data.exposures) if portfolio_data.exposures else 0
                }
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Basel calculation failed: {str(e)}")
            raise
    
    async def validate_portfolio_data(self, portfolio_data: PortfolioData, 
                                    capital_data: CapitalData) -> Dict[str, Any]:
        """Validate portfolio and capital data."""
        issues = []
        warnings = []
        
        try:
            # Validate portfolio
            if not portfolio_data.exposures:
                issues.append("Portfolio must contain at least one exposure")
            
            total_exposure = sum(exp.current_exposure for exp in portfolio_data.exposures)
            if total_exposure <= 0:
                issues.append("Total portfolio exposure must be positive")
            
            # Validate individual exposures
            for i, exp in enumerate(portfolio_data.exposures):
                if exp.current_exposure <= 0:
                    issues.append(f"Exposure {i+1} has non-positive amount")
                
                if exp.probability_of_default is not None:
                    if not (0 <= exp.probability_of_default <= 1):
                        issues.append(f"Exposure {i+1} has invalid PD: {exp.probability_of_default}")
                
                if exp.loss_given_default is not None:
                    if not (0 <= exp.loss_given_default <= 1):
                        issues.append(f"Exposure {i+1} has invalid LGD: {exp.loss_given_default}")
                
                if exp.maturity is not None and exp.maturity <= 0:
                    issues.append(f"Exposure {i+1} has non-positive maturity")
            
            # Validate capital
            cet1_before_adj = (
                capital_data.common_shares + 
                capital_data.retained_earnings + 
                capital_data.accumulated_oci + 
                capital_data.minority_interests
            )
            
            if cet1_before_adj <= 0:
                warnings.append("CET1 capital before adjustments is non-positive")
            
            # Check for unusual values
            if capital_data.goodwill > cet1_before_adj * 0.5:
                warnings.append("Goodwill is unusually high relative to CET1")
            
            if capital_data.at1_instruments > cet1_before_adj:
                warnings.append("AT1 instruments exceed CET1 capital")
            
            # Concentration checks
            if len(portfolio_data.exposures) > 1:
                largest_exposure = max(exp.current_exposure for exp in portfolio_data.exposures)
                if largest_exposure / total_exposure > 0.25:
                    warnings.append("High single-name concentration detected")
            
            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "warnings": warnings,
                "summary": {
                    "total_exposures": len(portfolio_data.exposures),
                    "total_exposure_amount": total_exposure,
                    "estimated_cet1": cet1_before_adj,
                    "validation_timestamp": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Validation failed: {str(e)}")
            return {
                "valid": False,
                "issues": [f"Validation error: {str(e)}"],
                "warnings": [],
                "summary": {}
            }
    
    async def generate_explanation(self, request_data: Dict[str, Any], 
                                 results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate detailed explanation of calculations."""
        try:
            explanation = {
                "calculation_methodology": {
                    "credit_rwa": "Standardized Approach with risk weights by asset class and rating",
                    "market_rwa": "FRTB Sensitivities-Based Approach for trading book exposures",
                    "operational_rwa": "Standardized Measurement Approach (SMA) based on Business Indicator",
                    "capital_ratios": "Basel III definitions with regulatory adjustments"
                },
                "key_assumptions": [
                    "Risk weights applied according to Basel III standardized approach",
                    "Credit risk mitigation applied where collateral is present",
                    "Market risk calculated for trading book exposures only",
                    "Operational risk estimated from portfolio characteristics if financial data not provided"
                ],
                "calculation_steps": {
                    "step_1": "Convert API data to internal exposure and capital models",
                    "step_2": "Calculate RWA for each risk type (credit, market, operational)",
                    "step_3": "Apply regulatory adjustments to capital components",
                    "step_4": "Calculate capital ratios and check buffer requirements",
                    "step_5": "Identify any buffer breaches and MDA restrictions"
                },
                "risk_weight_summary": {
                    "sovereign_range": "0% - 100% based on rating",
                    "bank_range": "20% - 150% based on rating",
                    "corporate_range": "20% - 150% based on rating",
                    "retail_mortgage": "35% for qualifying residential mortgages",
                    "retail_other": "75% for other retail exposures"
                },
                "buffer_requirements": {
                    "conservation_buffer": "2.5% above minimum CET1",
                    "countercyclical_buffer": "0-2.5% based on jurisdiction settings",
                    "sifi_buffers": "1.0-3.5% for systemically important institutions"
                }
            }
            
            # Add specific calculation details
            if "rwa" in results:
                rwa_data = results["rwa"]
                explanation["rwa_composition"] = {
                    "credit_rwa_pct": rwa_data.credit_rwa / rwa_data.total_rwa * 100 if rwa_data.total_rwa > 0 else 0,
                    "market_rwa_pct": rwa_data.market_rwa / rwa_data.total_rwa * 100 if rwa_data.total_rwa > 0 else 0,
                    "operational_rwa_pct": rwa_data.operational_rwa / rwa_data.total_rwa * 100 if rwa_data.total_rwa > 0 else 0
                }
            
            if "ratios" in results:
                ratios_data = results["ratios"]
                explanation["capital_adequacy_assessment"] = {
                    "cet1_status": "PASS" if ratios_data.cet1_excess_bps >= 0 else "FAIL",
                    "tier1_status": "PASS" if ratios_data.tier1_excess_bps >= 0 else "FAIL",
                    "total_capital_status": "PASS" if ratios_data.total_excess_bps >= 0 else "FAIL",
                    "leverage_status": "PASS" if ratios_data.leverage_excess_bps >= 0 else "FAIL"
                }
            
            return explanation
            
        except Exception as e:
            logger.error(f"Explanation generation failed: {str(e)}")
            return {"error": f"Failed to generate explanation: {str(e)}"}
    
    async def compare_portfolios(self, portfolio_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compare multiple portfolio results."""
        try:
            if len(portfolio_results) < 2:
                return {"error": "At least 2 portfolios required for comparison"}
            
            comparison = {
                "summary_comparison": {},
                "ratio_comparison": {},
                "rwa_comparison": {},
                "risk_profile_comparison": {},
                "ranking": {}
            }
            
            # Summary comparison
            for i, result in enumerate(portfolio_results):
                portfolio_name = result.get("portfolio_name", f"Portfolio {i+1}")
                comparison["summary_comparison"][portfolio_name] = {
                    "cet1_ratio": result["ratios"].cet1_ratio,
                    "total_rwa": result["rwa"].total_rwa,
                    "total_exposures": result["portfolio_summary"]["total_exposures"],
                    "meets_requirements": result["meets_minimum_requirements"]
                }
            
            # Ratio comparison
            cet1_ratios = [r["ratios"].cet1_ratio for r in portfolio_results]
            tier1_ratios = [r["ratios"].tier1_ratio for r in portfolio_results]
            total_ratios = [r["ratios"].total_capital_ratio for r in portfolio_results]
            
            comparison["ratio_comparison"] = {
                "cet1_range": {"min": min(cet1_ratios), "max": max(cet1_ratios), "avg": sum(cet1_ratios) / len(cet1_ratios)},
                "tier1_range": {"min": min(tier1_ratios), "max": max(tier1_ratios), "avg": sum(tier1_ratios) / len(tier1_ratios)},
                "total_range": {"min": min(total_ratios), "max": max(total_ratios), "avg": sum(total_ratios) / len(total_ratios)}
            }
            
            # RWA comparison
            total_rwas = [r["rwa"].total_rwa for r in portfolio_results]
            comparison["rwa_comparison"] = {
                "total_rwa_range": {"min": min(total_rwas), "max": max(total_rwas), "avg": sum(total_rwas) / len(total_rwas)},
                "rwa_efficiency": [
                    {
                        "portfolio": result.get("portfolio_name", f"Portfolio {i+1}"),
                        "rwa_per_exposure": result["rwa"].total_rwa / result["portfolio_summary"]["total_exposure_amount"]
                    }
                    for i, result in enumerate(portfolio_results)
                ]
            }
            
            # Risk profile comparison
            comparison["risk_profile_comparison"] = {
                "credit_risk_dominance": [
                    {
                        "portfolio": result.get("portfolio_name", f"Portfolio {i+1}"),
                        "credit_rwa_pct": result["rwa"].credit_rwa / result["rwa"].total_rwa * 100
                    }
                    for i, result in enumerate(portfolio_results)
                ],
                "market_risk_exposure": [
                    {
                        "portfolio": result.get("portfolio_name", f"Portfolio {i+1}"),
                        "market_rwa_pct": result["rwa"].market_rwa / result["rwa"].total_rwa * 100
                    }
                    for i, result in enumerate(portfolio_results)
                ]
            }
            
            # Ranking by capital efficiency
            portfolio_scores = []
            for i, result in enumerate(portfolio_results):
                portfolio_name = result.get("portfolio_name", f"Portfolio {i+1}")
                # Score based on CET1 ratio and RWA efficiency
                score = result["ratios"].cet1_ratio * 100 - (result["rwa"].total_rwa / result["portfolio_summary"]["total_exposure_amount"] * 10)
                portfolio_scores.append((portfolio_name, score))
            
            comparison["ranking"]["by_capital_efficiency"] = sorted(portfolio_scores, key=lambda x: x[1], reverse=True)
            
            return comparison
            
        except Exception as e:
            logger.error(f"Portfolio comparison failed: {str(e)}")
            return {"error": f"Comparison failed: {str(e)}"}
    
    def get_configuration(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config.model_dump() if self.config else {}
    
    def _convert_portfolio_data(self, portfolio_data: PortfolioData) -> Portfolio:
        """Convert API portfolio data to core Portfolio model."""
        portfolio = Portfolio(
            portfolio_id=portfolio_data.portfolio_id,
            bank_name=portfolio_data.bank_name,
            reporting_date=portfolio_data.reporting_date
        )
        
        for exp_data in portfolio_data.exposures:
            # Create CRM if collateral data provided
            crm = None
            if exp_data.collateral_type or exp_data.guarantee_provider:
                crm = CreditRiskMitigation(
                    collateral_type=exp_data.collateral_type,
                    collateral_value=exp_data.collateral_value,
                    guarantee_provider=exp_data.guarantee_provider,
                    guarantee_amount=exp_data.guarantee_amount
                )
            
            exposure = Exposure(
                exposure_id=exp_data.exposure_id,
                counterparty_id=exp_data.counterparty_id,
                exposure_type=ExposureType(exp_data.exposure_type),
                exposure_class=ExposureClass(exp_data.exposure_class),
                original_exposure=exp_data.original_exposure,
                current_exposure=exp_data.current_exposure,
                probability_of_default=exp_data.probability_of_default,
                loss_given_default=exp_data.loss_given_default,
                maturity=exp_data.maturity,
                external_rating=exp_data.external_rating,
                internal_rating=exp_data.internal_rating,
                credit_conversion_factor=exp_data.credit_conversion_factor,
                market_value=exp_data.market_value,
                sensitivities=exp_data.sensitivities or {},
                crm=crm,
                currency=exp_data.currency,
                business_line=exp_data.business_line,
                geography=exp_data.geography,
                sector=exp_data.sector
            )
            
            portfolio.add_exposure(exposure)
        
        return portfolio
    
    def _convert_capital_data(self, capital_data: CapitalData) -> Capital:
        """Convert API capital data to core Capital model."""
        components = CapitalComponents(
            common_shares=capital_data.common_shares,
            retained_earnings=capital_data.retained_earnings,
            accumulated_oci=capital_data.accumulated_oci,
            minority_interests=capital_data.minority_interests,
            at1_instruments=capital_data.at1_instruments,
            t2_instruments=capital_data.t2_instruments,
            general_provisions=capital_data.general_provisions,
            goodwill=capital_data.goodwill,
            intangible_assets=capital_data.intangible_assets,
            deferred_tax_assets=capital_data.deferred_tax_assets,
            cash_flow_hedge_reserve=capital_data.cash_flow_hedge_reserve,
            shortfall_provisions=capital_data.shortfall_provisions,
            securitization_exposures=capital_data.securitization_exposures,
            investments_in_own_shares=capital_data.investments_in_own_shares,
            reciprocal_cross_holdings=capital_data.reciprocal_cross_holdings,
            investments_in_financial_institutions=capital_data.investments_in_financial_institutions,
            mortgage_servicing_rights=capital_data.mortgage_servicing_rights,
            significant_investments_threshold=capital_data.significant_investments_threshold,
            dta_threshold=capital_data.dta_threshold,
            mortgage_servicing_threshold=capital_data.mortgage_servicing_threshold
        )
        
        return Capital(
            bank_name=capital_data.bank_name,
            reporting_date=capital_data.reporting_date,
            base_currency=capital_data.base_currency,
            components=components
        )
    
    def _convert_buffer_data(self, buffer_data: BufferData) -> RegulatoryBuffers:
        """Convert API buffer data to core RegulatoryBuffers model."""
        return RegulatoryBuffers(
            conservation_buffer=buffer_data.conservation_buffer,
            countercyclical_buffer=buffer_data.countercyclical_buffer,
            gsib_buffer=buffer_data.gsib_buffer,
            dsib_buffer=buffer_data.dsib_buffer,
            systemic_risk_buffer=buffer_data.systemic_risk_buffer,
            jurisdiction=buffer_data.jurisdiction,
            effective_date=buffer_data.effective_date,
            gsib_bucket=buffer_data.gsib_bucket
        )


class StressTestService:
    """Service for stress testing."""
    
    def __init__(self):
        self.stress_engine = None
        self.calculation_service = None
    
    async def initialize(self):
        """Initialize the service."""
        try:
            self.calculation_service = BaselCalculationService()
            await self.calculation_service.initialize()
            self.stress_engine = StressTestEngine(self.calculation_service.basel_engine)
            logger.info("Stress test service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize stress test service: {str(e)}")
            raise
    
    async def run_stress_tests(self, portfolio_data: PortfolioData,
                             capital_data: CapitalData,
                             scenarios: List[str],
                             buffers_data: Optional[BufferData] = None,
                             operational_risk_data: Optional[OperationalRiskData] = None,
                             custom_scenarios: Optional[Dict[str, Dict[str, float]]] = None,
                             config_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run stress tests for multiple scenarios."""
        try:
            # Convert data models
            portfolio = self.calculation_service._convert_portfolio_data(portfolio_data)
            capital = self.calculation_service._convert_capital_data(capital_data)
            buffers = self.calculation_service._convert_buffer_data(buffers_data) if buffers_data else RegulatoryBuffers()
            
            # Calculate baseline
            baseline_results = await self.calculation_service.calculate_basel_metrics(
                portfolio_data, capital_data, buffers_data, operational_risk_data, config_overrides
            )
            
            # Run stress tests
            stress_results = {}
            worst_cet1 = baseline_results["ratios"].cet1_ratio
            worst_scenario = "baseline"
            max_shortfall = 0.0
            scenarios_with_breaches = 0
            
            for scenario_name in scenarios:
                try:
                    # Get or create scenario
                    if scenario_name.startswith("custom_") and custom_scenarios:
                        custom_name = scenario_name.replace("custom_", "")
                        if custom_name in custom_scenarios:
                            scenario = create_custom_scenario(custom_name, custom_scenarios[custom_name])
                        else:
                            logger.warning(f"Custom scenario {custom_name} not found, skipping")
                            continue
                    else:
                        scenario = get_scenario(scenario_name)
                    
                    # Run stress test
                    stress_result = self.stress_engine.run_stress_test(portfolio, capital, scenario, buffers)
                    
                    # Convert to API response format
                    api_result = {
                        "scenario_name": stress_result.scenario_name,
                        "scenario_description": stress_result.scenario_description,
                        "baseline_ratios": CapitalRatiosResponse(
                            cet1_ratio=stress_result.baseline_results.cet1_ratio,
                            tier1_ratio=stress_result.baseline_results.tier1_ratio,
                            total_capital_ratio=stress_result.baseline_results.basel_ratio,
                            leverage_ratio=stress_result.baseline_results.leverage_ratio,
                            cet1_excess_bps=(stress_result.baseline_results.cet1_ratio - 0.045) * 10000,
                            tier1_excess_bps=(stress_result.baseline_results.tier1_ratio - 0.06) * 10000,
                            total_excess_bps=(stress_result.baseline_results.basel_ratio - 0.08) * 10000,
                            leverage_excess_bps=(stress_result.baseline_results.leverage_ratio - 0.03) * 10000
                        ),
                        "stressed_ratios": CapitalRatiosResponse(
                            cet1_ratio=stress_result.stressed_results.cet1_ratio,
                            tier1_ratio=stress_result.stressed_results.tier1_ratio,
                            total_capital_ratio=stress_result.stressed_results.basel_ratio,
                            leverage_ratio=stress_result.stressed_results.leverage_ratio,
                            cet1_excess_bps=(stress_result.stressed_results.cet1_ratio - 0.045) * 10000,
                            tier1_excess_bps=(stress_result.stressed_results.tier1_ratio - 0.06) * 10000,
                            total_excess_bps=(stress_result.stressed_results.basel_ratio - 0.08) * 10000,
                            leverage_excess_bps=(stress_result.stressed_results.leverage_ratio - 0.03) * 10000
                        ),
                        "capital_impact": stress_result.capital_impact,
                        "rwa_impact": stress_result.rwa_impact,
                        "ratio_impact": stress_result.ratio_impact,
                        "buffer_breaches": stress_result.buffer_breaches,
                        "capital_shortfall": stress_result.capital_shortfall,
                        "passes_minimum": stress_result.stressed_results.meets_minimum_requirements()
                    }
                    
                    stress_results[scenario_name] = api_result
                    
                    # Track worst case
                    if stress_result.stressed_results.cet1_ratio < worst_cet1:
                        worst_cet1 = stress_result.stressed_results.cet1_ratio
                        worst_scenario = scenario_name
                    
                    if stress_result.capital_shortfall > max_shortfall:
                        max_shortfall = stress_result.capital_shortfall
                    
                    if stress_result.buffer_breaches:
                        scenarios_with_breaches += 1
                    
                except Exception as e:
                    logger.error(f"Failed to run scenario {scenario_name}: {str(e)}")
                    continue
            
            # Overall assessment
            overall_assessment = "PASS" if worst_cet1 >= 0.045 else "FAIL"
            
            return {
                "results": stress_results,
                "worst_case_cet1": worst_cet1,
                "worst_case_scenario": worst_scenario,
                "max_capital_shortfall": max_shortfall,
                "scenarios_tested": len(stress_results),
                "scenarios_with_breaches": scenarios_with_breaches,
                "overall_assessment": overall_assessment
            }
            
        except Exception as e:
            logger.error(f"Stress testing failed: {str(e)}")
            raise
    
    def list_available_scenarios(self) -> List[Dict[str, Any]]:
        """List available stress scenarios."""
        try:
            scenario_names = list_available_scenarios()
            scenarios = []
            
            for name in scenario_names:
                scenario = get_scenario(name)
                scenarios.append({
                    "scenario_id": scenario.macro_scenario.scenario_id,
                    "scenario_name": scenario.macro_scenario.scenario_name,
                    "scenario_type": scenario.macro_scenario.scenario_type.value,
                    "description": scenario.macro_scenario.description,
                    "time_horizon": scenario.macro_scenario.time_horizon,
                    "gdp_growth": scenario.macro_scenario.gdp_growth,
                    "unemployment_rate": scenario.macro_scenario.unemployment_rate,
                    "inflation_rate": scenario.macro_scenario.inflation_rate,
                    "num_shocks": len(scenario.macro_scenario.shocks)
                })
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Failed to list scenarios: {str(e)}")
            return []
