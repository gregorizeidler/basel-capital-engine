"""Streamlit dashboard for Basel Capital Engine."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from typing import Dict, Any, List, Optional
import json
from datetime import datetime
import io

# Import Basel Engine components
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.basileia import BaselEngine, PortfolioGenerator, Capital, RegulatoryBuffers
from src.basileia.stress import StressTestEngine, get_scenario, list_available_scenarios
from src.basileia.simulator.portfolio import BankSize


# Page configuration
st.set_page_config(
    page_title="Basel Capital Engine",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f4e79;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #1f4e79;
        margin: 0.5rem 0;
    }
    .status-pass {
        color: #28a745;
        font-weight: bold;
    }
    .status-fail {
        color: #dc3545;
        font-weight: bold;
    }
    .status-warning {
        color: #ffc107;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_sample_data():
    """Load sample portfolio data."""
    generator = PortfolioGenerator(seed=42)
    portfolio, capital = generator.generate_bank_portfolio(BankSize.MEDIUM, "Sample Bank")
    return portfolio, capital


@st.cache_data
def calculate_basel_metrics(portfolio_data, capital_data, buffer_data=None):
    """Calculate Basel metrics with caching."""
    try:
        engine = BaselEngine()
        
        # Create buffers if provided
        buffers = None
        if buffer_data:
            buffers = RegulatoryBuffers(**buffer_data)
        
        results = engine.calculate_all_metrics(portfolio_data, capital_data, buffers)
        return results
    except Exception as e:
        st.error(f"Calculation failed: {str(e)}")
        return None


def create_ratio_gauge(ratio_value: float, ratio_name: str, minimum: float, 
                      buffer_requirement: float = 0.0) -> go.Figure:
    """Create a gauge chart for capital ratios."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=ratio_value * 100,  # Convert to percentage
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"{ratio_name}"},
        delta={'reference': (minimum + buffer_requirement) * 100},
        gauge={
            'axis': {'range': [None, max(20, ratio_value * 120)]},
            'bar': {'color': "darkblue"},
            'steps': [
                {'range': [0, minimum * 100], 'color': "lightgray"},
                {'range': [minimum * 100, (minimum + buffer_requirement) * 100], 'color': "yellow"},
                {'range': [(minimum + buffer_requirement) * 100, 20], 'color': "lightgreen"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': (minimum + buffer_requirement) * 100
            }
        }
    ))
    
    fig.update_layout(height=300)
    return fig


def create_rwa_waterfall(rwa_breakdown: Dict[str, float]) -> go.Figure:
    """Create waterfall chart for RWA breakdown."""
    categories = ['Credit RWA', 'Market RWA', 'Operational RWA']
    values = [
        rwa_breakdown.get('credit_rwa', 0),
        rwa_breakdown.get('market_rwa', 0), 
        rwa_breakdown.get('operational_rwa', 0)
    ]
    
    fig = go.Figure(go.Waterfall(
        name="RWA Breakdown",
        orientation="v",
        measure=["relative", "relative", "relative", "total"],
        x=categories + ["Total RWA"],
        textposition="outside",
        text=[f"€{v:,.0f}" for v in values] + [f"€{sum(values):,.0f}"],
        y=values + [sum(values)],
        connector={"line": {"color": "rgb(63, 63, 63)"}},
    ))
    
    fig.update_layout(
        title="Risk-Weighted Assets Breakdown",
        showlegend=False,
        height=400
    )
    
    return fig


def create_capital_structure_chart(capital_breakdown: Dict[str, Any]) -> go.Figure:
    """Create capital structure visualization."""
    labels = ['CET1 Capital', 'AT1 Capital', 'Tier 2 Capital']
    values = [
        capital_breakdown.get('cet1_capital', 0),
        capital_breakdown.get('at1_capital', 0),
        capital_breakdown.get('tier2_capital', 0)
    ]
    
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.3,
        textinfo='label+percent+value',
        texttemplate='%{label}<br>%{percent}<br>€%{value:,.0f}'
    )])
    
    fig.update_layout(
        title="Capital Structure",
        height=400
    )
    
    return fig


def create_stress_test_chart(stress_results: Dict[str, Any]) -> go.Figure:
    """Create stress test results chart."""
    scenarios = list(stress_results.keys())
    cet1_ratios = [result.stressed_results.cet1_ratio * 100 
                  for result in stress_results.values()]
    
    fig = go.Figure()
    
    # Add bars for each scenario
    fig.add_trace(go.Bar(
        x=scenarios,
        y=cet1_ratios,
        name='CET1 Ratio',
        marker_color=['green' if ratio >= 4.5 else 'red' for ratio in cet1_ratios]
    ))
    
    # Add minimum requirement line
    fig.add_hline(y=4.5, line_dash="dash", line_color="red", 
                  annotation_text="Minimum CET1 (4.5%)")
    
    fig.update_layout(
        title="Stress Test Results - CET1 Ratios",
        xaxis_title="Scenario",
        yaxis_title="CET1 Ratio (%)",
        height=400
    )
    
    return fig


def main():
    """Main dashboard function."""
    
    # Header
    st.markdown('<h1 class="main-header">🏦 Basel Capital Engine</h1>', unsafe_allow_html=True)
    st.markdown("**Open-source regulatory capital calculation engine implementing Basel III framework**")
    
    # Sidebar
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox(
        "Select Page",
        ["Portfolio Analysis", "Stress Testing", "Data Input", "Configuration"]
    )
    
    if page == "Portfolio Analysis":
        portfolio_analysis_page()
    elif page == "Stress Testing":
        stress_testing_page()
    elif page == "Data Input":
        data_input_page()
    elif page == "Configuration":
        configuration_page()


def portfolio_analysis_page():
    """Portfolio analysis page."""
    st.header("📊 Portfolio Analysis")
    
    # Load data
    if 'portfolio' not in st.session_state or 'capital' not in st.session_state:
        with st.spinner("Loading sample data..."):
            portfolio, capital = load_sample_data()
            st.session_state.portfolio = portfolio
            st.session_state.capital = capital
    
    portfolio = st.session_state.portfolio
    capital = st.session_state.capital
    
    # Calculate metrics
    with st.spinner("Calculating Basel metrics..."):
        results = calculate_basel_metrics(portfolio, capital)
    
    if results is None:
        st.error("Failed to calculate metrics. Please check your data.")
        return
    
    # Display key metrics
    st.subheader("Key Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        cet1_status = "PASS" if results.cet1_ratio >= 0.045 else "FAIL"
        st.metric(
            "CET1 Ratio",
            f"{results.cet1_ratio:.2%}",
            f"{(results.cet1_ratio - 0.045) * 10000:.0f} bps vs minimum"
        )
        st.markdown(f'<span class="status-{"pass" if cet1_status == "PASS" else "fail"}">{cet1_status}</span>', 
                   unsafe_allow_html=True)
    
    with col2:
        tier1_status = "PASS" if results.tier1_ratio >= 0.06 else "FAIL"
        st.metric(
            "Tier 1 Ratio",
            f"{results.tier1_ratio:.2%}",
            f"{(results.tier1_ratio - 0.06) * 10000:.0f} bps vs minimum"
        )
        st.markdown(f'<span class="status-{"pass" if tier1_status == "PASS" else "fail"}">{tier1_status}</span>', 
                   unsafe_allow_html=True)
    
    with col3:
        total_status = "PASS" if results.basel_ratio >= 0.08 else "FAIL"
        st.metric(
            "Total Capital Ratio",
            f"{results.basel_ratio:.2%}",
            f"{(results.basel_ratio - 0.08) * 10000:.0f} bps vs minimum"
        )
        st.markdown(f'<span class="status-{"pass" if total_status == "PASS" else "fail"}">{total_status}</span>', 
                   unsafe_allow_html=True)
    
    with col4:
        leverage_status = "PASS" if results.leverage_ratio >= 0.03 else "FAIL"
        st.metric(
            "Leverage Ratio",
            f"{results.leverage_ratio:.2%}",
            f"{(results.leverage_ratio - 0.03) * 10000:.0f} bps vs minimum"
        )
        st.markdown(f'<span class="status-{"pass" if leverage_status == "PASS" else "fail"}">{leverage_status}</span>', 
                   unsafe_allow_html=True)
    
    # Visualizations
    st.subheader("Detailed Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Capital ratios gauges
        st.subheader("Capital Ratios")
        
        # CET1 gauge
        fig_cet1 = create_ratio_gauge(results.cet1_ratio, "CET1 Ratio", 0.045, 0.025)
        st.plotly_chart(fig_cet1, use_container_width=True)
    
    with col2:
        # RWA waterfall
        rwa_data = {
            'credit_rwa': results.credit_rwa,
            'market_rwa': results.market_rwa,
            'operational_rwa': results.operational_rwa
        }
        fig_rwa = create_rwa_waterfall(rwa_data)
        st.plotly_chart(fig_rwa, use_container_width=True)
    
    # Capital structure
    st.subheader("Capital Structure")
    fig_capital = create_capital_structure_chart(results.capital_breakdown)
    st.plotly_chart(fig_capital, use_container_width=True)
    
    # Detailed breakdowns
    st.subheader("Detailed Breakdowns")
    
    tab1, tab2, tab3 = st.tabs(["Credit Risk", "Market Risk", "Operational Risk"])
    
    with tab1:
        if 'credit' in results.rwa_breakdown:
            credit_detail = results.rwa_breakdown['credit']['details']
            
            # By exposure class
            if 'by_exposure_class' in credit_detail:
                df_exposure_class = pd.DataFrame([
                    {
                        'Exposure Class': k,
                        'EAD': v['ead'],
                        'RWA': v['rwa'],
                        'Risk Weight': v['risk_weight'],
                        'EAD %': v['ead_percentage'] * 100,
                        'RWA %': v['rwa_percentage'] * 100
                    }
                    for k, v in credit_detail['by_exposure_class'].items()
                ])
                
                st.subheader("By Exposure Class")
                st.dataframe(df_exposure_class, use_container_width=True)
                
                # Chart
                fig = px.bar(df_exposure_class, x='Exposure Class', y='RWA', 
                           title="RWA by Exposure Class")
                st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        if 'market' in results.rwa_breakdown:
            market_detail = results.rwa_breakdown['market']['details']
            
            st.write("Market Risk Details:")
            st.json(market_detail)
    
    with tab3:
        if 'operational' in results.rwa_breakdown:
            op_detail = results.rwa_breakdown['operational']['details']
            
            st.write("Operational Risk Details:")
            st.json(op_detail)
    
    # Buffer analysis
    if results.buffer_breaches:
        st.subheader("⚠️ Buffer Breaches")
        
        for breach in results.buffer_breaches:
            st.error(f"**{breach.buffer_type.value.title()} Buffer Breach**")
            st.write(f"Required: {breach.required_ratio:.2%}")
            st.write(f"Actual: {breach.actual_ratio:.2%}")
            st.write(f"Shortfall: €{breach.shortfall_amount:,.0f}")
    
    # Portfolio summary
    st.subheader("Portfolio Summary")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Exposures", len(portfolio.exposures))
        st.metric("Total Exposure Amount", f"€{portfolio.get_total_exposure():,.0f}")
    
    with col2:
        concentration = portfolio.get_concentration_metrics()
        st.metric("Largest Counterparty", f"{concentration.get('largest_counterparty_pct', 0):.1%}")
        st.metric("Largest Sector", f"{concentration.get('largest_sector_pct', 0):.1%}")
    
    with col3:
        trading_exposures = len(portfolio.get_trading_book_exposures())
        banking_exposures = len(portfolio.get_banking_book_exposures())
        st.metric("Trading Book", trading_exposures)
        st.metric("Banking Book", banking_exposures)


def stress_testing_page():
    """Stress testing page."""
    st.header("🧪 Stress Testing")
    
    # Load data
    if 'portfolio' not in st.session_state or 'capital' not in st.session_state:
        with st.spinner("Loading sample data..."):
            portfolio, capital = load_sample_data()
            st.session_state.portfolio = portfolio
            st.session_state.capital = capital
    
    portfolio = st.session_state.portfolio
    capital = st.session_state.capital
    
    # Scenario selection
    st.subheader("Scenario Selection")
    
    available_scenarios = list_available_scenarios()
    selected_scenarios = st.multiselect(
        "Select stress scenarios to run:",
        available_scenarios,
        default=["adverse"]
    )
    
    if st.button("Run Stress Tests"):
        if not selected_scenarios:
            st.error("Please select at least one scenario.")
            return
        
        with st.spinner("Running stress tests..."):
            stress_engine = StressTestEngine()
            stress_results = {}
            
            # Calculate baseline
            baseline_results = calculate_basel_metrics(portfolio, capital)
            
            for scenario_name in selected_scenarios:
                try:
                    scenario = get_scenario(scenario_name)
                    result = stress_engine.run_stress_test(portfolio, capital, scenario)
                    stress_results[scenario_name] = result
                except Exception as e:
                    st.error(f"Failed to run scenario {scenario_name}: {str(e)}")
        
        if stress_results:
            # Display results
            st.subheader("Stress Test Results")
            
            # Summary metrics
            col1, col2, col3 = st.columns(3)
            
            worst_cet1 = min(r.stressed_results.cet1_ratio for r in stress_results.values())
            worst_scenario = min(stress_results.items(), 
                               key=lambda x: x[1].stressed_results.cet1_ratio)[0]
            max_shortfall = max(r.capital_shortfall for r in stress_results.values())
            
            with col1:
                st.metric("Worst CET1 Ratio", f"{worst_cet1:.2%}")
                st.write(f"Scenario: {worst_scenario}")
            
            with col2:
                st.metric("Max Capital Shortfall", f"€{max_shortfall:,.0f}")
            
            with col3:
                overall_pass = worst_cet1 >= 0.045
                st.metric("Overall Assessment", "PASS" if overall_pass else "FAIL")
            
            # Stress test chart
            fig_stress = create_stress_test_chart(stress_results)
            st.plotly_chart(fig_stress, use_container_width=True)
            
            # Detailed results
            st.subheader("Detailed Results")
            
            for scenario_name, result in stress_results.items():
                with st.expander(f"{scenario_name.title()} Scenario"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**Baseline vs Stressed**")
                        comparison_data = {
                            'Metric': ['CET1 Ratio', 'Tier 1 Ratio', 'Total Capital Ratio'],
                            'Baseline': [
                                f"{result.baseline_results.cet1_ratio:.2%}",
                                f"{result.baseline_results.tier1_ratio:.2%}",
                                f"{result.baseline_results.basel_ratio:.2%}"
                            ],
                            'Stressed': [
                                f"{result.stressed_results.cet1_ratio:.2%}",
                                f"{result.stressed_results.tier1_ratio:.2%}",
                                f"{result.stressed_results.basel_ratio:.2%}"
                            ],
                            'Change (bps)': [
                                f"{result.ratio_impact['cet1_ratio_change_bps']:.0f}",
                                f"{result.ratio_impact['tier1_ratio_change_bps']:.0f}",
                                f"{result.ratio_impact['basel_ratio_change_bps']:.0f}"
                            ]
                        }
                        st.dataframe(pd.DataFrame(comparison_data), use_container_width=True)
                    
                    with col2:
                        st.write("**RWA Impact**")
                        rwa_impact_data = {
                            'Component': ['Credit RWA', 'Market RWA', 'Operational RWA', 'Total RWA'],
                            'Change': [
                                f"€{result.rwa_impact['credit_rwa_change']:,.0f}",
                                f"€{result.rwa_impact['market_rwa_change']:,.0f}",
                                f"€{result.rwa_impact['operational_rwa_change']:,.0f}",
                                f"€{result.rwa_impact['total_rwa_change']:,.0f}"
                            ],
                            'Change %': [
                                f"{result.rwa_impact['credit_rwa_change_pct']:.1%}",
                                f"{result.rwa_impact['market_rwa_change_pct']:.1%}",
                                f"{result.rwa_impact['operational_rwa_change_pct']:.1%}",
                                f"{result.rwa_impact['total_rwa_change_pct']:.1%}"
                            ]
                        }
                        st.dataframe(pd.DataFrame(rwa_impact_data), use_container_width=True)
                    
                    if result.buffer_breaches:
                        st.error("**Buffer Breaches Detected:**")
                        for breach in result.buffer_breaches:
                            st.write(f"- {breach}")
                    
                    if result.capital_shortfall > 0:
                        st.warning(f"**Capital Shortfall:** €{result.capital_shortfall:,.0f}")


def data_input_page():
    """Data input page."""
    st.header("📁 Data Input")
    
    st.write("Upload your portfolio and capital data, or generate synthetic data for testing.")
    
    tab1, tab2, tab3 = st.tabs(["Upload Data", "Generate Synthetic", "Current Data"])
    
    with tab1:
        st.subheader("Upload Portfolio Data")
        
        uploaded_file = st.file_uploader(
            "Choose a CSV file with exposure data",
            type="csv"
        )
        
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                st.write("Data preview:")
                st.dataframe(df.head())
                
                if st.button("Process Data"):
                    st.info("Data processing functionality would be implemented here.")
                    # TODO: Implement data processing
                    
            except Exception as e:
                st.error(f"Error reading file: {str(e)}")
    
    with tab2:
        st.subheader("Generate Synthetic Portfolio")
        
        col1, col2 = st.columns(2)
        
        with col1:
            bank_size = st.selectbox(
                "Bank Size",
                ["small", "medium", "large", "gsib"],
                index=1
            )
            
            bank_name = st.text_input("Bank Name", "Synthetic Bank")
            
            seed = st.number_input("Random Seed", value=42, help="For reproducible results")
        
        with col2:
            st.write("**Bank Size Characteristics:**")
            if bank_size == "small":
                st.write("- Community bank (€500M - €5B assets)")
                st.write("- Mainly retail and mortgage lending")
                st.write("- Limited trading activities")
            elif bank_size == "medium":
                st.write("- Regional bank (€5B - €50B assets)")
                st.write("- Diversified lending portfolio")
                st.write("- Some trading and derivatives")
            elif bank_size == "large":
                st.write("- Large commercial bank (€50B - €500B assets)")
                st.write("- Full service offering")
                st.write("- Significant trading operations")
            else:  # gsib
                st.write("- Global systemically important bank (€500B+ assets)")
                st.write("- Highly diversified and complex")
                st.write("- Extensive international operations")
        
        if st.button("Generate Portfolio"):
            with st.spinner("Generating synthetic portfolio..."):
                generator = PortfolioGenerator(seed=seed)
                portfolio, capital = generator.generate_bank_portfolio(
                    BankSize(bank_size), bank_name
                )
                
                st.session_state.portfolio = portfolio
                st.session_state.capital = capital
                
                st.success(f"Generated portfolio for {bank_name} with {len(portfolio.exposures)} exposures")
                
                # Show summary
                st.write("**Portfolio Summary:**")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Total Exposures", len(portfolio.exposures))
                
                with col2:
                    st.metric("Total Amount", f"€{portfolio.get_total_exposure():,.0f}")
                
                with col3:
                    st.metric("CET1 Capital", f"€{capital.calculate_cet1_capital():,.0f}")
    
    with tab3:
        st.subheader("Current Data Summary")
        
        if 'portfolio' in st.session_state and 'capital' in st.session_state:
            portfolio = st.session_state.portfolio
            capital = st.session_state.capital
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Portfolio Information:**")
                st.write(f"- Portfolio ID: {portfolio.portfolio_id}")
                st.write(f"- Bank Name: {portfolio.bank_name}")
                st.write(f"- Reporting Date: {portfolio.reporting_date}")
                st.write(f"- Number of Exposures: {len(portfolio.exposures)}")
                st.write(f"- Total Exposure: €{portfolio.get_total_exposure():,.0f}")
            
            with col2:
                st.write("**Capital Information:**")
                st.write(f"- CET1 Capital: €{capital.calculate_cet1_capital():,.0f}")
                st.write(f"- Tier 1 Capital: €{capital.calculate_tier1_capital():,.0f}")
                st.write(f"- Total Capital: €{capital.calculate_total_capital():,.0f}")
            
            # Exposure breakdown
            st.write("**Exposure Type Breakdown:**")
            exposure_types = {}
            for exp in portfolio.exposures:
                exp_type = exp.exposure_type.value
                exposure_types[exp_type] = exposure_types.get(exp_type, 0) + exp.current_exposure
            
            df_exp_types = pd.DataFrame([
                {'Type': k, 'Amount': v, 'Percentage': v/portfolio.get_total_exposure()*100}
                for k, v in exposure_types.items()
            ])
            st.dataframe(df_exp_types, use_container_width=True)
            
            # Export functionality
            if st.button("Export Current Data"):
                # Create export data
                export_data = {
                    'portfolio': {
                        'portfolio_id': portfolio.portfolio_id,
                        'bank_name': portfolio.bank_name,
                        'reporting_date': portfolio.reporting_date,
                        'exposures': [exp.model_dump() for exp in portfolio.exposures]
                    },
                    'capital': capital.model_dump()
                }
                
                # Convert to JSON
                json_str = json.dumps(export_data, indent=2, default=str)
                
                st.download_button(
                    label="Download as JSON",
                    data=json_str,
                    file_name=f"{portfolio.bank_name}_data_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json"
                )
        else:
            st.info("No data loaded. Please generate synthetic data or upload a portfolio.")


def configuration_page():
    """Configuration page."""
    st.header("⚙️ Configuration")
    
    st.write("Configure Basel calculation parameters and risk weights.")
    
    tab1, tab2, tab3 = st.tabs(["Risk Weights", "Buffers", "Limits"])
    
    with tab1:
        st.subheader("Credit Risk Weights")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Sovereign Exposures**")
            sovereign_aaa = st.slider("Sovereign AAA/AA", 0.0, 2.0, 0.0, 0.05)
            sovereign_a = st.slider("Sovereign A", 0.0, 2.0, 0.2, 0.05)
            sovereign_bbb = st.slider("Sovereign BBB/BB", 0.0, 2.0, 0.5, 0.05)
            
            st.write("**Bank Exposures**")
            bank_aaa = st.slider("Bank AAA/AA", 0.0, 2.0, 0.2, 0.05)
            bank_a = st.slider("Bank A", 0.0, 2.0, 0.5, 0.05)
            bank_bbb = st.slider("Bank BBB/BB", 0.0, 2.0, 1.0, 0.05)
        
        with col2:
            st.write("**Corporate Exposures**")
            corp_aaa = st.slider("Corporate AAA/AA", 0.0, 2.0, 0.2, 0.05)
            corp_a = st.slider("Corporate A", 0.0, 2.0, 0.5, 0.05)
            corp_bbb = st.slider("Corporate BBB/BB", 0.0, 2.0, 1.0, 0.05)
            
            st.write("**Retail Exposures**")
            retail_mortgage = st.slider("Retail Mortgage", 0.0, 2.0, 0.35, 0.05)
            retail_other = st.slider("Retail Other", 0.0, 2.0, 0.75, 0.05)
    
    with tab2:
        st.subheader("Regulatory Buffers")
        
        col1, col2 = st.columns(2)
        
        with col1:
            conservation_buffer = st.slider("Conservation Buffer (%)", 0.0, 5.0, 2.5, 0.1)
            countercyclical_buffer = st.slider("Countercyclical Buffer (%)", 0.0, 2.5, 0.0, 0.1)
        
        with col2:
            gsib_buffer = st.slider("G-SIB Buffer (%)", 0.0, 3.5, 0.0, 0.1)
            dsib_buffer = st.slider("D-SIB Buffer (%)", 0.0, 2.0, 0.0, 0.1)
        
        if st.button("Apply Buffer Configuration"):
            # Store buffer configuration in session state
            st.session_state.buffer_config = {
                'conservation_buffer': conservation_buffer / 100,
                'countercyclical_buffer': countercyclical_buffer / 100,
                'gsib_buffer': gsib_buffer / 100,
                'dsib_buffer': dsib_buffer / 100
            }
            st.success("Buffer configuration updated!")
    
    with tab3:
        st.subheader("Regulatory Limits")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Minimum Capital Ratios**")
            min_cet1 = st.slider("Minimum CET1 (%)", 0.0, 10.0, 4.5, 0.1)
            min_tier1 = st.slider("Minimum Tier 1 (%)", 0.0, 10.0, 6.0, 0.1)
            min_total = st.slider("Minimum Total Capital (%)", 0.0, 15.0, 8.0, 0.1)
        
        with col2:
            st.write("**Other Limits**")
            min_leverage = st.slider("Minimum Leverage Ratio (%)", 0.0, 10.0, 3.0, 0.1)
            max_single_exposure = st.number_input("Max Single Exposure (€M)", 0, 10000, 1000)
        
        st.info("Configuration changes will be applied to future calculations.")


if __name__ == "__main__":
    main()
