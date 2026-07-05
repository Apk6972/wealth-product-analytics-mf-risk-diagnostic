"""
Page: Fund Due Diligence.

Reads only from 02_processed_data/ (via data_loader.py) — never fetches
live data. Reference: 00_project_control/master_project_instructions.md.md
§23.2.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import charts  # noqa: E402
import data_loader as dl  # noqa: E402
import disclosures  # noqa: E402
from utils import CLIENT_PROFILES, format_inr_compact, format_percent, is_dataframe_usable  # noqa: E402

REFRESH_COMMAND = "python 04_streamlit_app/refresh_data.py"
GROWTH_BASE_VALUE = 10_000_000

# metrics_summary.csv column -> (KPI card label, formatter)
_METRIC_CARD_SPECS = [
    ("cagr", "CAGR", "percent"),
    ("annualized_volatility", "Volatility (Ann.)", "percent"),
    ("sharpe_ratio", "Sharpe Ratio", "ratio"),
    ("sortino_ratio", "Sortino Ratio", "ratio"),
    ("max_drawdown", "Max Drawdown", "percent"),
    ("worst_month", "Worst Month", "percent"),
    ("daily_cvar_95", "Daily CVaR 95", "percent"),
    ("recovery_period_days", "Recovery Period", "days"),
]


def _format_ratio(value: float) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.2f}"


def _format_days(value: float) -> str:
    if value is None or pd.isna(value):
        return "Not yet recovered"
    return f"{value:.0f} days"


def _format_metric_card_value(value: float, kind: str) -> str:
    if kind == "percent":
        return format_percent(value)
    if kind == "ratio":
        return _format_ratio(value)
    if kind == "days":
        return _format_days(value)
    return str(value)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("Fund Due Diligence")
st.caption("A single fund's return path, drawdown behaviour, and risk metrics — in isolation.")

disclosures.render_data_quality_banner()

nav_daily = dl.load_nav_daily()
returns_monthly = dl.load_returns_monthly()
rolling_metrics = dl.load_rolling_metrics()
metrics_summary = dl.load_metrics_summary()

missing_files = []
if not is_dataframe_usable(nav_daily):
    missing_files.append("`02_processed_data/nav_daily_clean.csv`")
if not is_dataframe_usable(returns_monthly):
    missing_files.append("`02_processed_data/returns_monthly.csv`")
if not is_dataframe_usable(rolling_metrics):
    missing_files.append("`02_processed_data/rolling_metrics.csv`")
if not is_dataframe_usable(metrics_summary):
    missing_files.append("`02_processed_data/metrics_summary.csv`")

if missing_files:
    st.warning(
        "This page needs the following processed data file(s), which are missing or empty:\n\n"
        + "\n".join(f"- {name}" for name in missing_files)
        + "\n\nRun the data pipeline, then reload this page:"
    )
    st.code(REFRESH_COMMAND, language="bash")
    st.stop()

fund_labels = sorted(metrics_summary["fund_label"].dropna().unique().tolist())
if not fund_labels:
    st.warning("No funds found in `metrics_summary.csv`.")
    st.stop()

with st.sidebar:
    st.header("Fund Selection")
    selected_fund = st.selectbox("Fund", options=fund_labels, key="due_diligence_fund_select")
    client_profile = st.selectbox(
        "Client profile (for suitability note)",
        options=CLIENT_PROFILES,
        index=CLIENT_PROFILES.index("Balanced") if "Balanced" in CLIENT_PROFILES else 0,
        key="due_diligence_profile_select",
    )
    show_annualized_rolling_return = st.checkbox("Show rolling 12M return annualized", value=False)

    st.divider()
    st.caption("This app reads only from `02_processed_data/`. To refresh data, run:")
    st.code(REFRESH_COMMAND, language="bash")

st.subheader(selected_fund)

# ---------------------------------------------------------------------------
# NAV / growth path
# ---------------------------------------------------------------------------

st.markdown("#### NAV / Growth Path")
st.plotly_chart(
    charts.plot_growth_of_investment(nav_daily, base_value=GROWTH_BASE_VALUE, fund_labels=[selected_fund]),
    width="stretch",
)
st.caption(f"Growth of {format_inr_compact(GROWTH_BASE_VALUE)} invested in this fund from its first available NAV date.")

# ---------------------------------------------------------------------------
# Drawdown
# ---------------------------------------------------------------------------

st.markdown("#### Drawdown")
st.plotly_chart(charts.plot_drawdown(nav_daily, fund_labels=[selected_fund]), width="stretch")

# ---------------------------------------------------------------------------
# Monthly returns
# ---------------------------------------------------------------------------

st.markdown("#### Monthly Returns")
st.plotly_chart(charts.plot_monthly_returns_bar(returns_monthly, selected_fund), width="stretch")

# ---------------------------------------------------------------------------
# Rolling 12M return
# ---------------------------------------------------------------------------

st.markdown("#### Rolling 12-Month Return")
st.plotly_chart(
    charts.plot_rolling_return(
        rolling_metrics, window="12m", annualized=show_annualized_rolling_return, fund_labels=[selected_fund]
    ),
    width="stretch",
)

# ---------------------------------------------------------------------------
# Metric cards
# ---------------------------------------------------------------------------

st.markdown("#### Key Metrics")
fund_metrics_rows = metrics_summary[metrics_summary["fund_label"] == selected_fund]
if fund_metrics_rows.empty:
    st.info(f"No metrics available for '{selected_fund}' in `metrics_summary.csv`.")
else:
    fund_metrics_row = fund_metrics_rows.iloc[0]
    card_columns = st.columns(4)
    for index, (column_name, label, kind) in enumerate(_METRIC_CARD_SPECS):
        value = fund_metrics_row.get(column_name, float("nan"))
        card_columns[index % 4].metric(label, _format_metric_card_value(value, kind))

st.divider()

# ---------------------------------------------------------------------------
# Suitability note
# ---------------------------------------------------------------------------

st.markdown("#### Suitability Note")
suitability_results = dl.load_suitability_results()
if not is_dataframe_usable(suitability_results):
    st.info(
        "Suitability diagnostics are not available yet — `02_processed_data/suitability_results.csv` has not "
        "been generated. This file is produced by the suitability engine "
        "(`04_streamlit_app/src/suitability.py`'s `run_suitability_engine()`), which is separate from "
        f"`{REFRESH_COMMAND}`."
    )
else:
    note_rows = suitability_results[
        (suitability_results["fund_label"] == selected_fund)
        & (suitability_results["client_profile"] == client_profile)
    ]
    if note_rows.empty:
        st.info(f"No suitability diagnostic found for '{selected_fund}' under the '{client_profile}' profile.")
    else:
        note_row = note_rows.iloc[0]
        st.info(
            f"**Client profile: {client_profile}** — Suitability role: **{note_row['suitability_role']}** · "
            f"Suggested review action: **{note_row['recommended_action']}**\n\n"
            f"{note_row['risk_warning']}\n\n"
            f"{note_row['rationale']}"
        )

st.caption("Educational analytics project. Not investment advice.")
