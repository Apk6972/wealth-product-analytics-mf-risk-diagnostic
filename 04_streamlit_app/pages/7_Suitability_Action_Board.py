"""
Page: Suitability & Action Board.

Reads only from 02_processed_data/ (via data_loader.py) — never fetches
live data. Reference: 00_project_control/master_project_instructions.md.md
§23.7.

This page presents educational suitability diagnostics only, derived from
trailing historical risk metrics via a transparent, documented rules-based
rubric (00_project_control/formula_audit.md §8). It never issues a buy /
sell / hold instruction or any other direct investment recommendation.
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

import data_loader as dl  # noqa: E402
from suitability import (  # noqa: E402
    ROLE_AGGRESSIVE_SATELLITE,
    ROLE_CORE,
    ROLE_DEFENSIVE_SLEEVE,
    ROLE_SATELLITE,
    ROLE_UNSUITABLE,
    ROLE_WATCHLIST,
)
from utils import CLIENT_PROFILES, SUITABILITY_DISCLAIMER, is_dataframe_usable  # noqa: E402

REFRESH_COMMAND = "python 04_streamlit_app/refresh_data.py"
SUITABILITY_COMMAND = (
    'python -c "import sys; sys.path.insert(0, \'04_streamlit_app/src\'); '
    'from suitability import run_suitability_engine; run_suitability_engine()"'
)

BOARD_COLUMN_ORDER = [
    ROLE_DEFENSIVE_SLEEVE,
    ROLE_CORE,
    ROLE_SATELLITE,
    ROLE_AGGRESSIVE_SATELLITE,
    ROLE_WATCHLIST,
    ROLE_UNSUITABLE,
]
ROLE_DISPLAY_STYLE = {
    ROLE_DEFENSIVE_SLEEVE: "success",
    ROLE_CORE: "success",
    ROLE_SATELLITE: "info",
    ROLE_AGGRESSIVE_SATELLITE: "info",
    ROLE_WATCHLIST: "warning",
    ROLE_UNSUITABLE: "error",
}


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("Suitability & Action Board")
st.caption("Educational, historical-risk-based diagnostics — not a recommendation to buy, sell, or hold anything.")

suitability_results = dl.load_suitability_results()

if not is_dataframe_usable(suitability_results):
    st.warning(
        "This page needs `02_processed_data/suitability_results.csv`, which is missing or empty.\n\n"
        "This file is produced by the suitability engine (`04_streamlit_app/src/suitability.py`), which is "
        f"separate from `{REFRESH_COMMAND}`. Generate it with:"
    )
    st.code(SUITABILITY_COMMAND, language="bash")
    st.stop()

st.warning(SUITABILITY_DISCLAIMER)

with st.sidebar:
    st.header("Client Profile")
    selected_profile = st.selectbox("Client profile", options=CLIENT_PROFILES, key="suitability_profile_select")

    st.divider()
    st.caption("This app reads only from `02_processed_data/`. To refresh the underlying risk data, run:")
    st.code(REFRESH_COMMAND, language="bash")
    st.caption("To regenerate suitability diagnostics after that, run:")
    st.code(SUITABILITY_COMMAND, language="bash")

profile_df = suitability_results[suitability_results["client_profile"] == selected_profile].copy()
if profile_df.empty:
    st.info(f"No suitability diagnostics found for the '{selected_profile}' profile.")
    st.stop()

st.subheader(f"{selected_profile} Profile")

# ---------------------------------------------------------------------------
# Suitability table
# ---------------------------------------------------------------------------

st.markdown("#### Suitability Table")
table_df = pd.DataFrame(
    {
        "Fund": profile_df["fund_label"],
        "Overall Risk Tier": profile_df["overall_risk_tier"],
        "Suitability Role": profile_df["suitability_role"],
        "Recommended Educational Action": profile_df["recommended_action"],
        "Benchmark Data Available": profile_df["benchmark_relative_data_available"].map({True: "Yes", False: "No"}),
    }
)
st.dataframe(table_df, width="stretch", hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Risk warnings
# ---------------------------------------------------------------------------

st.markdown("#### Risk Warnings")
st.caption("Only factors assessed at MEDIUM or HIGH historical risk tier are listed per fund (see Methodology).")
for _, row in profile_df.sort_values("fund_label").iterrows():
    if isinstance(row["risk_warning"], str) and row["risk_warning"].strip():
        st.warning(f"**{row['fund_label']}** — {row['risk_warning']}")
    else:
        st.success(f"**{row['fund_label']}** — no factors flagged at MEDIUM/HIGH historical risk tier.")

st.divider()

# ---------------------------------------------------------------------------
# Recommended educational action
# ---------------------------------------------------------------------------

st.markdown("#### Recommended Educational Action")
st.caption(
    "Framed as a suggested review action based on trailing historical data — never an instruction to buy, "
    "sell, or hold."
)
for action, action_group in profile_df.groupby("recommended_action"):
    fund_list = ", ".join(sorted(action_group["fund_label"]))
    st.info(f"**{action}**: {fund_list}")

st.divider()

# ---------------------------------------------------------------------------
# Finding / interpretation / action board
# ---------------------------------------------------------------------------

st.markdown("#### Finding / Interpretation / Action Board")
st.caption(
    "Funds grouped by suitability role for this profile — from most defensive fit (left) to least suitable "
    "(right). The same fund can land in a different column under a different client profile."
)

board_columns = st.columns(len(BOARD_COLUMN_ORDER))
for column, role in zip(board_columns, BOARD_COLUMN_ORDER):
    role_funds = profile_df[profile_df["suitability_role"] == role]
    column.markdown(f"**{role}** ({len(role_funds)})")
    display_fn = getattr(column, ROLE_DISPLAY_STYLE.get(role, "info"))
    if role_funds.empty:
        column.caption("No funds")
    else:
        for fund_label in sorted(role_funds["fund_label"]):
            display_fn(fund_label)

st.markdown("##### Per-Fund Finding & Interpretation")
for _, row in profile_df.sort_values("fund_label").iterrows():
    with st.expander(f"{row['fund_label']} — {row['suitability_role']} / {row['recommended_action']}"):
        st.markdown(row["rationale"])

st.caption(
    "All findings above describe trailing historical data only and are educational diagnostics — not a "
    "forecast, not personalized advice, and not an instruction to buy, sell, or hold any security."
)
