"""
Comprehensive example showing integrated Basel III + IFRS 9 + ICAAP + Liquidity analysis.

This example demonstrates how to use all modules together for a complete
regulatory analysis of a bank's capital and liquidity position.
"""

from basileia import (
    BaselEngine, Capital, PortfolioGenerator,
    IFRS9Calculator, LCRCalculator, ICAAProcessor, COREPGenerator
)
from basileia.liquidity.lcr import LiquidAsset, CashFlowItem, HQLACategory


def main():
    """Run comprehensive regulatory analysis."""
    
    print("🏦 Basel Capital Engine - Integrated Regulatory Analysis")
    print("=" * 60)
    
    # 1. Generate synthetic portfolio
    print("\n📊 Generating synthetic portfolio...")
    generator = PortfolioGenerator()
    portfolio = generator.generate_bank_portfolio(size="large", risk_profile="balanced")
    print(f"Generated portfolio with {len(portfolio.exposures)} exposures")
    
    # 2. Define capital structure
    print("\n💰 Setting up capital structure...")
    capital = Capital(
        common_shares=2_000_000,
        retained_earnings=800_000,
        accumulated_oci=-50_000,
        at1_instruments=300_000,
        t2_instruments=400_000,
        goodwill=100_000,
        intangible_assets=50_000
    )
    print(f"Total regulatory capital: €{capital.total_capital:,.0f}")
    
    # 3. Basel III calculations
    print("\n⚖️ Calculating Basel III metrics...")
    basel_engine = BaselEngine()
    basel_results = basel_engine.calculate_all_metrics(portfolio, capital)
    
    print(f"  CET1 Ratio: {basel_results.cet1_ratio:.2%}")
    print(f"  Tier 1 Ratio: {basel_results.tier1_ratio:.2%}")
    print(f"  Total Capital Ratio: {basel_results.total_capital_ratio:.2%}")
    print(f"  Total RWA: €{basel_results.total_rwa:,.0f}")
    
    # 4. IFRS 9 Expected Credit Loss
    print("\n💳 Calculating IFRS 9 Expected Credit Loss...")
    ifrs9_calculator = IFRS9Calculator()
    ecl_results = ifrs9_calculator.calculate_portfolio_ecl(portfolio)
    ecl_summary = ifrs9_calculator.calculate_ecl_summary(portfolio)
    
    print(f"  Total ECL: €{ecl_summary['total_ecl']:,.0f}")
    print(f"  Overall Coverage Ratio: {ecl_summary['overall_coverage_ratio']:.2%}")
    print(f"  Stage 1 exposures: {ecl_summary['stage_breakdown']['stage_1']['count']}")
    print(f"  Stage 2 exposures: {ecl_summary['stage_breakdown']['stage_2']['count']}")
    print(f"  Stage 3 exposures: {ecl_summary['stage_breakdown']['stage_3']['count']}")
    
    # 5. Liquidity Coverage Ratio
    print("\n🌊 Calculating Liquidity Coverage Ratio...")
    
    # Create sample liquid assets
    liquid_assets = [
        LiquidAsset(
            asset_id="CASH_001",
            asset_type="Cash",
            market_value=500_000,
            hqla_category=HQLACategory.LEVEL_1,
            haircut_rate=0.0
        ),
        LiquidAsset(
            asset_id="BOND_001", 
            asset_type="Government Bond",
            market_value=1_000_000,
            hqla_category=HQLACategory.LEVEL_1,
            haircut_rate=0.0
        ),
        LiquidAsset(
            asset_id="CORP_001",
            asset_type="Corporate Bond",
            market_value=300_000,
            hqla_category=HQLACategory.LEVEL_2A,
            haircut_rate=0.15
        )
    ]
    
    # Create sample cash flows
    cash_flows = [
        CashFlowItem(
            item_id="DEP_001",
            item_type="outflow",
            counterparty_type="retail_stable",
            amount=2_000_000,
            runoff_rate=0.05,
            maturity_days=30
        ),
        CashFlowItem(
            item_id="LOAN_001",
            item_type="inflow", 
            counterparty_type="corporate",
            amount=500_000,
            runoff_rate=0.0,
            maturity_days=15
        )
    ]
    
    lcr_calculator = LCRCalculator()
    lcr_result = lcr_calculator.calculate_lcr(liquid_assets, cash_flows)
    
    print(f"  LCR Ratio: {lcr_result.lcr_ratio:.1%}")
    print(f"  Total HQLA: €{lcr_result.total_hqla:,.0f}")
    print(f"  Net Cash Outflows: €{lcr_result.net_cash_outflows:,.0f}")
    print(f"  LCR Compliant: {'✅ Yes' if lcr_result.compliant else '❌ No'}")
    
    # 6. ICAAP Assessment
    print("\n🔍 Performing ICAAP Assessment...")
    
    business_data = {
        'total_assets': 10_000_000,
        'asset_duration': 3.5,
        'liability_duration': 1.8,
        'revenue_breakdown': {
            'net_interest_income': 300_000,
            'fee_income': 150_000,
            'trading_income': 80_000
        }
    }
    
    icaap_processor = ICAAProcessor()
    icaap_result = icaap_processor.comprehensive_assessment(
        portfolio, capital, business_data
    )
    
    print(f"  Pillar 1 Capital Requirement: €{icaap_result.pillar1_capital_requirement:,.0f}")
    print(f"  Pillar 2 Add-on: €{icaap_result.pillar2_total_add_on:,.0f}")
    print(f"  Total Capital Requirement: €{icaap_result.total_capital_requirement:,.0f}")
    print(f"  Capital Adequacy Ratio: {icaap_result.capital_adequacy_ratio:.2f}")
    print(f"  Assessment Level: {icaap_result.assessment_level.value.upper()}")
    
    if icaap_result.limit_breaches:
        print("  ⚠️  Limit Breaches:")
        for breach in icaap_result.limit_breaches:
            print(f"    • {breach}")
    
    # 7. Regulatory Reporting
    print("\n📋 Generating COREP Report...")
    
    institution_info = {
        'institution_code': 'SAMPLE_BANK_001',
        'institution_name': 'Sample Bank AG'
    }
    
    corep_generator = COREPGenerator(basel_engine)
    corep_report = corep_generator.generate_corep_report(
        portfolio, capital, institution_info
    )
    
    print(f"  COREP Report generated for: {corep_report.institution_name}")
    print(f"  Reporting Date: {corep_report.reporting_date}")
    print(f"  Tables included: {len([t for t in [corep_report.c_01_00_own_funds, corep_report.c_02_00_own_funds_requirements] if t])}")
    
    # Validate report
    validation_errors = corep_generator.validate_report(corep_report)
    if validation_errors:
        print("  ⚠️  Validation Issues:")
        for error in validation_errors:
            print(f"    • {error}")
    else:
        print("  ✅ Report validation passed")
    
    # 8. Integrated Analysis Summary
    print("\n📈 Integrated Analysis Summary")
    print("=" * 40)
    
    # Capital adequacy vs accounting provisions
    regulatory_capital_ratio = basel_results.total_capital_ratio
    accounting_coverage_ratio = ecl_summary['overall_coverage_ratio']
    
    print(f"Regulatory Capital Ratio: {regulatory_capital_ratio:.2%}")
    print(f"Accounting Coverage Ratio: {accounting_coverage_ratio:.2%}")
    print(f"Liquidity Coverage Ratio: {lcr_result.lcr_ratio:.1%}")
    print(f"ICAAP Assessment: {icaap_result.assessment_level.value.upper()}")
    
    # Overall health score
    health_score = (
        min(regulatory_capital_ratio / 0.08, 1.5) * 0.4 +  # Basel ratio (40% weight)
        min(lcr_result.lcr_ratio, 2.0) * 0.3 +             # LCR (30% weight)  
        (1.0 if icaap_result.assessment_level.value == 'adequate' else 0.5) * 0.3  # ICAAP (30% weight)
    )
    
    print(f"\n🎯 Overall Regulatory Health Score: {health_score:.1f}/1.5")
    
    if health_score >= 1.2:
        print("✅ Strong regulatory position")
    elif health_score >= 1.0:
        print("⚠️  Adequate regulatory position") 
    else:
        print("❌ Regulatory concerns identified")
    
    print("\n🎉 Analysis complete!")


if __name__ == "__main__":
    main()
