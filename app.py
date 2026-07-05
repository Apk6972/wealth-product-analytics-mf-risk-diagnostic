"""
MF Risk Diagnostic Module — Streamlit entry point.

Functional V1: registers all eight implemented pages and wires multi-page
navigation. Each page loads from 02_processed_data/ via data_loader.py and
runs display and charting logic through charts.py. No live data is fetched
on page load.

Reference: 00_project_control/master_project_instructions.md.md §23 (Streamlit
App Layout). Non-negotiable runtime rule: the app must never fetch live data
on page load (see §3 and 00_project_control/model_governance.md).
"""

import streamlit as st

st.set_page_config(
    page_title="MF Risk Diagnostic Module",
    page_icon="📊",
    layout="wide",
)

PAGES_DIR = "04_streamlit_app/pages"

pages = [
    st.Page(f"{PAGES_DIR}/1_Executive_Risk_Review.py", title="Executive Risk Review", icon="📊"),
    st.Page(f"{PAGES_DIR}/2_Fund_Due_Diligence.py", title="Fund Due Diligence", icon="🔍"),
    st.Page(f"{PAGES_DIR}/3_Benchmark_Behaviour.py", title="Benchmark Behaviour", icon="📈"),
    st.Page(f"{PAGES_DIR}/4_Rolling_Risk_Return.py", title="Rolling Risk & Return", icon="🔄"),
    st.Page(f"{PAGES_DIR}/5_Drawdown_Tail_Risk.py", title="Drawdown & Tail Risk", icon="📉"),
    st.Page(f"{PAGES_DIR}/6_Scenario_Stress_Testing.py", title="Scenario Stress Testing", icon="⚠️"),
    st.Page(f"{PAGES_DIR}/7_Suitability_Action_Board.py", title="Suitability & Action Board", icon="🧭"),
    st.Page(f"{PAGES_DIR}/8_Methodology.py", title="Methodology", icon="📚"),
]

navigation = st.navigation(pages)
navigation.run()
