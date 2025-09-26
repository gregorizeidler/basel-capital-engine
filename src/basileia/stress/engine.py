"""Stress testing engine for Basel Capital Engine."""

from typing import Dict, Any, List, Optional, Tuple
import logging
from datetime import datetime
import copy
from pydantic import BaseModel

from .scenarios import StressScenario, MacroScenario, get_scenario
from ..core.engine import BaselEngine, BaselResults
from ..core.exposure import Portfolio, Exposure
from ..core.capital import Capital
from ..core.buffers import RegulatoryBuffers

logger = logging.getLogger(__name__)


class StressTestResults(BaseModel):
    """Results from stress testing analysis."""
    
    scenario_name: str
    scenario_description: str
    
    # Pre-stress results
    baseline_results: BaselResults
    
    # Post-stress results
    stressed_results: BaselResults
    
    # Impact analysis
    capital_impact: Dict[str, float]
    rwa_impact: Dict[str, float]
    ratio_impact: Dict[str, float]
    
    # Buffer analysis
    buffer_breaches: List[str]
    capital_shortfall: float
    
    # Detailed breakdowns
    exposure_impacts: Dict[str, Any]
    waterfall_analysis: Dict[str, Any]
    
    # Metadata
    test_date: str
    time_horizon: int


class StressTestEngine:
    """Engine for conducting comprehensive stress tests."""
    
    def __init__(self, basel_engine: Optional[BaselEngine] = None):
        """Initialize stress testing engine."""
        self.basel_engine = basel_engine or BaselEngine()
        
    def run_stress_test(self, portfolio: Portfolio, capital: Capital,
                       scenario: StressScenario,
                       buffers: Optional[RegulatoryBuffers] = None) -> StressTestResults:
        """Run complete stress test for given scenario."""
        logger.info(f"Running stress test: {scenario.macro_scenario.scenario_name}")
        
        # Calculate baseline metrics
        baseline_results = self.basel_engine.calculate_all_metrics(portfolio, capital, buffers)
        
        # Apply stress to portfolio and capital
        stressed_portfolio = self._apply_portfolio_stress(portfolio, scenario)
        stressed_capital = self._apply_capital_stress(capital, scenario)
        
        # Calculate stressed metrics
        stressed_results = self.basel_engine.calculate_all_metrics(
            stressed_portfolio, stressed_capital, buffers
        )
        
        # Calculate impacts
        capital_impact = self._calculate_capital_impact(baseline_results, stressed_results)
        rwa_impact = self._calculate_rwa_impact(baseline_results, stressed_results)
        ratio_impact = self._calculate_ratio_impact(baseline_results, stressed_results)
        
        # Analyze buffer breaches
        buffer_breaches = [breach.buffer_type.value for breach in stressed_results.buffer_breaches]
        capital_shortfall = sum(breach.shortfall_amount for breach in stressed_results.buffer_breaches)
        
        # Detailed analysis
        exposure_impacts = self._analyze_exposure_impacts(portfolio, stressed_portfolio)
        waterfall_analysis = self._create_waterfall_analysis(baseline_results, stressed_results)
        
        return StressTestResults(
            scenario_name=scenario.macro_scenario.scenario_name,
            scenario_description=scenario.macro_scenario.description,
            baseline_results=baseline_results,
            stressed_results=stressed_results,
            capital_impact=capital_impact,
            rwa_impact=rwa_impact,
            ratio_impact=ratio_impact,
            buffer_breaches=buffer_breaches,
            capital_shortfall=capital_shortfall,
            exposure_impacts=exposure_impacts,
            waterfall_analysis=waterfall_analysis,
            test_date=datetime.now().strftime("%Y-%m-%d"),
            time_horizon=scenario.macro_scenario.time_horizon
        )
    
    def _apply_portfolio_stress(self, portfolio: Portfolio, scenario: StressScenario) -> Portfolio:
        """Apply stress scenario to portfolio exposures."""
        stressed_portfolio = Portfolio(
            portfolio_id=f"{portfolio.portfolio_id}_stressed",
            bank_name=portfolio.bank_name,
            reporting_date=portfolio.reporting_date,
            exposures=[]
        )
        
        for exposure in portfolio.exposures:
            stressed_exposure = self._apply_exposure_stress(exposure, scenario)
            stressed_portfolio.add_exposure(stressed_exposure)
        
        return stressed_portfolio
    
    def _apply_exposure_stress(self, exposure: Exposure, scenario: StressScenario) -> Exposure:
        """Apply stress to individual exposure."""
        # Create copy of exposure
        stressed_exposure = exposure.model_copy(deep=True)
        
        # Apply credit risk stress
        if exposure.probability_of_default is not None:
            stressed_exposure.probability_of_default = scenario.calculate_pd_stress(
                exposure.probability_of_default,
                sector=exposure.sector,
                geography=exposure.geography
            )
        
        if exposure.loss_given_default is not None:
            stressed_exposure.loss_given_default = scenario.calculate_lgd_stress(
                exposure.loss_given_default,
                sector=exposure.sector
            )
        
        # Apply market risk stress to trading book
        if exposure.is_trading_book() and exposure.market_value is not None:
            asset_class = self._determine_asset_class(exposure)
            stressed_exposure.market_value = scenario.calculate_market_value_stress(
                exposure.market_value,
                asset_class,
                exposure.currency
            )
        
        # Apply exposure stress (EAD changes)
        if exposure.exposure_type.value in ["commitments", "guarantees"]:
            exposure_type = exposure.exposure_type.value
            stressed_ead = scenario.calculate_exposure_stress(
                exposure.current_exposure, exposure_type
            )
            stressed_exposure.current_exposure = stressed_ead
        
        # Stress collateral values
        if exposure.crm and exposure.crm.collateral_value:
            # Real estate collateral affected by property price shocks
            if exposure.crm.collateral_type in ["residential_property", "commercial_property"]:
                re_shock = scenario.macro_scenario.get_shock_value("real_estate_prices")
                if re_shock != 0:
                    stressed_exposure.crm.collateral_value = max(
                        0, exposure.crm.collateral_value * (1 + re_shock)
                    )
        
        return stressed_exposure
    
    def _apply_capital_stress(self, capital: Capital, scenario: StressScenario) -> Capital:
        """Apply stress to capital structure."""
        # For most stress tests, capital structure remains unchanged
        # In practice, this might include:
        # - Dividend restrictions under stress
        # - AT1/CoCo conversions if triggers hit
        # - Retained earnings impact from P&L stress
        
        stressed_capital = capital.model_copy(deep=True)
        
        # Simple example: reduce retained earnings by estimated P&L impact
        gdp_shock = scenario.macro_scenario.get_shock_value("gdp_growth")
        if gdp_shock < 0:
            # Estimate P&L impact as % of capital (simplified)
            pl_impact_ratio = abs(gdp_shock) * 0.5  # 50% of GDP shock
            pl_impact = capital.calculate_cet1_capital() * pl_impact_ratio
            
            # Reduce retained earnings
            stressed_capital.components.retained_earnings = max(
                capital.components.retained_earnings - pl_impact,
                -capital.components.common_shares * 0.5  # Limit negative RE
            )
        
        return stressed_capital
    
    def _determine_asset_class(self, exposure: Exposure) -> str:
        """Determine asset class for market risk stress."""
        if exposure.exposure_class.value == "sovereign":
            return "bond"
        elif exposure.exposure_class.value in ["corporate", "bank"]:
            if exposure.exposure_type.value == "securities":
                return "corporate_bond"
            else:
                return "equity"
        elif exposure.exposure_class.value == "equity":
            return "equity"
        else:
            return "other"
    
    def _calculate_capital_impact(self, baseline: BaselResults, stressed: BaselResults) -> Dict[str, float]:
        """Calculate capital impact from stress."""
        return {
            "cet1_change": stressed.cet1_capital - baseline.cet1_capital,
            "tier1_change": stressed.tier1_capital - baseline.tier1_capital,
            "total_change": stressed.total_capital - baseline.total_capital,
            "cet1_change_pct": (stressed.cet1_capital / baseline.cet1_capital - 1) if baseline.cet1_capital > 0 else 0,
            "tier1_change_pct": (stressed.tier1_capital / baseline.tier1_capital - 1) if baseline.tier1_capital > 0 else 0,
            "total_change_pct": (stressed.total_capital / baseline.total_capital - 1) if baseline.total_capital > 0 else 0
        }
    
    def _calculate_rwa_impact(self, baseline: BaselResults, stressed: BaselResults) -> Dict[str, float]:
        """Calculate RWA impact from stress."""
        return {
            "total_rwa_change": stressed.total_rwa - baseline.total_rwa,
            "credit_rwa_change": stressed.credit_rwa - baseline.credit_rwa,
            "market_rwa_change": stressed.market_rwa - baseline.market_rwa,
            "operational_rwa_change": stressed.operational_rwa - baseline.operational_rwa,
            "total_rwa_change_pct": (stressed.total_rwa / baseline.total_rwa - 1) if baseline.total_rwa > 0 else 0,
            "credit_rwa_change_pct": (stressed.credit_rwa / baseline.credit_rwa - 1) if baseline.credit_rwa > 0 else 0,
            "market_rwa_change_pct": (stressed.market_rwa / baseline.market_rwa - 1) if baseline.market_rwa > 0 else 0,
            "operational_rwa_change_pct": (stressed.operational_rwa / baseline.operational_rwa - 1) if baseline.operational_rwa > 0 else 0
        }
    
    def _calculate_ratio_impact(self, baseline: BaselResults, stressed: BaselResults) -> Dict[str, float]:
        """Calculate capital ratio impact from stress."""
        return {
            "cet1_ratio_change": stressed.cet1_ratio - baseline.cet1_ratio,
            "tier1_ratio_change": stressed.tier1_ratio - baseline.tier1_ratio,
            "basel_ratio_change": stressed.basel_ratio - baseline.basel_ratio,
            "leverage_ratio_change": stressed.leverage_ratio - baseline.leverage_ratio,
            "cet1_ratio_change_bps": (stressed.cet1_ratio - baseline.cet1_ratio) * 10000,
            "tier1_ratio_change_bps": (stressed.tier1_ratio - baseline.tier1_ratio) * 10000,
            "basel_ratio_change_bps": (stressed.basel_ratio - baseline.basel_ratio) * 10000,
            "leverage_ratio_change_bps": (stressed.leverage_ratio - baseline.leverage_ratio) * 10000
        }
    
    def _analyze_exposure_impacts(self, baseline_portfolio: Portfolio, 
                                stressed_portfolio: Portfolio) -> Dict[str, Any]:
        """Analyze impact on individual exposures."""
        impacts = {
            "by_exposure_class": {},
            "by_sector": {},
            "by_geography": {},
            "largest_impacts": []
        }
        
        # Create mapping of exposures
        baseline_map = {exp.exposure_id: exp for exp in baseline_portfolio.exposures}
        stressed_map = {exp.exposure_id: exp for exp in stressed_portfolio.exposures}
        
        individual_impacts = []
        
        for exp_id in baseline_map:
            baseline_exp = baseline_map[exp_id]
            stressed_exp = stressed_map.get(exp_id)
            
            if not stressed_exp:
                continue
            
            # Calculate impact for this exposure
            impact = self._calculate_single_exposure_impact(baseline_exp, stressed_exp)
            impact["exposure_id"] = exp_id
            impact["exposure_class"] = baseline_exp.exposure_class.value
            impact["sector"] = baseline_exp.sector or "unknown"
            impact["geography"] = baseline_exp.geography or "unknown"
            
            individual_impacts.append(impact)
            
            # Aggregate by dimensions
            exp_class = baseline_exp.exposure_class.value
            if exp_class not in impacts["by_exposure_class"]:
                impacts["by_exposure_class"][exp_class] = {"count": 0, "total_impact": 0}
            impacts["by_exposure_class"][exp_class]["count"] += 1
            impacts["by_exposure_class"][exp_class]["total_impact"] += impact["total_impact"]
            
            sector = baseline_exp.sector or "unknown"
            if sector not in impacts["by_sector"]:
                impacts["by_sector"][sector] = {"count": 0, "total_impact": 0}
            impacts["by_sector"][sector]["count"] += 1
            impacts["by_sector"][sector]["total_impact"] += impact["total_impact"]
            
            geography = baseline_exp.geography or "unknown"
            if geography not in impacts["by_geography"]:
                impacts["by_geography"][geography] = {"count": 0, "total_impact": 0}
            impacts["by_geography"][geography]["count"] += 1
            impacts["by_geography"][geography]["total_impact"] += impact["total_impact"]
        
        # Find largest impacts
        impacts["largest_impacts"] = sorted(
            individual_impacts, 
            key=lambda x: abs(x["total_impact"]), 
            reverse=True
        )[:20]  # Top 20 impacts
        
        return impacts
    
    def _calculate_single_exposure_impact(self, baseline: Exposure, stressed: Exposure) -> Dict[str, float]:
        """Calculate impact for single exposure."""
        impact = {
            "baseline_exposure": baseline.current_exposure,
            "stressed_exposure": stressed.current_exposure,
            "exposure_change": stressed.current_exposure - baseline.current_exposure,
            "pd_change": 0,
            "lgd_change": 0,
            "market_value_change": 0,
            "total_impact": 0
        }
        
        # PD impact
        if baseline.probability_of_default and stressed.probability_of_default:
            impact["pd_change"] = stressed.probability_of_default - baseline.probability_of_default
        
        # LGD impact
        if baseline.loss_given_default and stressed.loss_given_default:
            impact["lgd_change"] = stressed.loss_given_default - baseline.loss_given_default
        
        # Market value impact
        if baseline.market_value and stressed.market_value:
            impact["market_value_change"] = stressed.market_value - baseline.market_value
        
        # Total impact (simplified - would need RWA calculation for precision)
        impact["total_impact"] = (
            impact["exposure_change"] +
            impact["market_value_change"] +
            baseline.current_exposure * (impact["pd_change"] + impact["lgd_change"])
        )
        
        return impact
    
    def _create_waterfall_analysis(self, baseline: BaselResults, stressed: BaselResults) -> Dict[str, Any]:
        """Create waterfall analysis of RWA and capital changes."""
        return {
            "rwa_waterfall": {
                "baseline_rwa": baseline.total_rwa,
                "credit_rwa_change": stressed.credit_rwa - baseline.credit_rwa,
                "market_rwa_change": stressed.market_rwa - baseline.market_rwa,
                "operational_rwa_change": stressed.operational_rwa - baseline.operational_rwa,
                "stressed_rwa": stressed.total_rwa,
                "total_change": stressed.total_rwa - baseline.total_rwa
            },
            "capital_waterfall": {
                "baseline_cet1": baseline.cet1_capital,
                "pl_impact": stressed.cet1_capital - baseline.cet1_capital,
                "stressed_cet1": stressed.cet1_capital,
                "total_change": stressed.cet1_capital - baseline.cet1_capital
            },
            "ratio_waterfall": {
                "baseline_cet1_ratio": baseline.cet1_ratio,
                "numerator_effect": (stressed.cet1_capital - baseline.cet1_capital) / baseline.total_rwa if baseline.total_rwa > 0 else 0,
                "denominator_effect": -baseline.cet1_capital * (stressed.total_rwa - baseline.total_rwa) / (baseline.total_rwa ** 2) if baseline.total_rwa > 0 else 0,
                "stressed_cet1_ratio": stressed.cet1_ratio,
                "total_change": stressed.cet1_ratio - baseline.cet1_ratio
            }
        }
    
    def run_multiple_scenarios(self, portfolio: Portfolio, capital: Capital,
                             scenario_names: List[str],
                             buffers: Optional[RegulatoryBuffers] = None) -> Dict[str, StressTestResults]:
        """Run stress tests for multiple scenarios."""
        results = {}
        
        for scenario_name in scenario_names:
            try:
                scenario = get_scenario(scenario_name)
                results[scenario_name] = self.run_stress_test(portfolio, capital, scenario, buffers)
                logger.info(f"Completed stress test: {scenario_name}")
            except Exception as e:
                logger.error(f"Failed to run scenario {scenario_name}: {str(e)}")
                continue
        
        return results
    
    def compare_scenarios(self, results: Dict[str, StressTestResults]) -> Dict[str, Any]:
        """Compare results across multiple scenarios."""
        if not results:
            return {}
        
        comparison = {
            "scenario_summary": {},
            "worst_case_metrics": {},
            "ranking": {}
        }
        
        # Summarize each scenario
        for scenario_name, result in results.items():
            comparison["scenario_summary"][scenario_name] = {
                "cet1_ratio_final": result.stressed_results.cet1_ratio,
                "cet1_ratio_change_bps": result.ratio_impact["cet1_ratio_change_bps"],
                "total_rwa_change_pct": result.rwa_impact["total_rwa_change_pct"],
                "capital_shortfall": result.capital_shortfall,
                "buffer_breaches": len(result.buffer_breaches),
                "passes_minimum": result.stressed_results.meets_minimum_requirements()
            }
        
        # Find worst case metrics
        if results:
            worst_cet1 = min(r.stressed_results.cet1_ratio for r in results.values())
            worst_leverage = min(r.stressed_results.leverage_ratio for r in results.values())
            max_shortfall = max(r.capital_shortfall for r in results.values())
            
            comparison["worst_case_metrics"] = {
                "worst_cet1_ratio": worst_cet1,
                "worst_leverage_ratio": worst_leverage,
                "max_capital_shortfall": max_shortfall
            }
        
        # Rank scenarios by severity
        scenario_severity = []
        for scenario_name, result in results.items():
            severity_score = (
                -result.ratio_impact["cet1_ratio_change_bps"] +  # More negative = worse
                result.capital_shortfall / 1e6 +  # Shortfall in millions
                len(result.buffer_breaches) * 50  # Breach penalty
            )
            scenario_severity.append((scenario_name, severity_score))
        
        comparison["ranking"] = sorted(scenario_severity, key=lambda x: x[1], reverse=True)
        
        return comparison
    
    def generate_stress_report(self, results: Dict[str, StressTestResults]) -> Dict[str, Any]:
        """Generate comprehensive stress test report."""
        report = {
            "executive_summary": {},
            "detailed_results": results,
            "scenario_comparison": self.compare_scenarios(results),
            "recommendations": [],
            "report_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Executive summary
        if results:
            baseline_result = next(iter(results.values()))
            baseline_cet1 = baseline_result.baseline_results.cet1_ratio
            
            worst_cet1 = min(r.stressed_results.cet1_ratio for r in results.values())
            max_shortfall = max(r.capital_shortfall for r in results.values())
            
            report["executive_summary"] = {
                "baseline_cet1_ratio": f"{baseline_cet1:.2%}",
                "worst_case_cet1_ratio": f"{worst_cet1:.2%}",
                "maximum_capital_shortfall": f"€{max_shortfall:,.0f}",
                "scenarios_tested": len(results),
                "scenarios_with_breaches": sum(1 for r in results.values() if r.buffer_breaches),
                "overall_assessment": "PASS" if worst_cet1 > 0.045 else "FAIL"
            }
        
        # Generate recommendations
        report["recommendations"] = self._generate_recommendations(results)
        
        return report
    
    def _generate_recommendations(self, results: Dict[str, StressTestResults]) -> List[str]:
        """Generate recommendations based on stress test results."""
        recommendations = []
        
        if not results:
            return recommendations
        
        # Analyze results for recommendations
        worst_result = min(results.values(), key=lambda r: r.stressed_results.cet1_ratio)
        
        if worst_result.stressed_results.cet1_ratio < 0.045:
            recommendations.append(
                f"CET1 ratio falls below minimum requirement in {worst_result.scenario_name}. "
                f"Consider raising €{worst_result.capital_shortfall:,.0f} in additional capital."
            )
        
        if worst_result.capital_shortfall > 0:
            recommendations.append(
                "Buffer breaches detected. Review capital planning and consider pre-emptive actions."
            )
        
        # Concentration analysis
        max_sector_impact = 0
        worst_sector = ""
        for result in results.values():
            for sector, impact_data in result.exposure_impacts.get("by_sector", {}).items():
                if abs(impact_data.get("total_impact", 0)) > max_sector_impact:
                    max_sector_impact = abs(impact_data["total_impact"])
                    worst_sector = sector
        
        if max_sector_impact > 0 and worst_sector:
            recommendations.append(
                f"High concentration risk detected in {worst_sector} sector. "
                "Consider portfolio diversification strategies."
            )
        
        return recommendations
