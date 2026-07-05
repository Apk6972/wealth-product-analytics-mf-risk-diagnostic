"""
Page: Scenario Stress Testing.

Reads only from 02_processed_data/ (via data_loader.py) for the default
deterministic/historical scenarios — never fetches live data. The "Custom
Shock" mode recomputes attribution live, in-memory, from user slider input
via stress.run_custom_shock() (per its docstring, this is intentionally
never persisted to stress_results.csv). Reference:
00_project_control/master_project_instructions.md.md §23.6.
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
import formatting  # noqa: E402
from stress import CUSTOM_DISCLOSURE, DEFAULT_BASE_PORTFOLIO_VALUE, run_custom_shock  # noqa: E402
from utils import STRESS_TEST_DISCLAIMER, is_dataframe_usable  # noqa: E402

REFRESH_COMMAND = "python 04_streamlit_app/refresh_data.py"
CUSTOM_SCENARIO_LABEL = "Custom Shock (interactive)"

SCENARIO_TYPE_DISPLAY_NAMES = {
    "HISTORICAL_REPLAY": "Historical Replay — actual historical returns",
    "DETERMINISTIC": "Deterministic — illustrative assumption",
    "CUSTOM": "Custom Shock — interactive, illustrative assumption",
}


def _render_scenario_results(scenario_df: pd.DataFrame, scenario_type: str, rationale: str) -> None:
    """Shared rendering path for a single scenario's attribution slice — used for
    on-disk deterministic/historical scenarios and for the live custom-shock table alike,
    since both share the exact same attribution_results.csv column schema."""
    if scenario_df.empty:
        st.info("No attribution data available for this scenario/fund combination.")
        return

    st.caption(f"Scenario type: **{SCENARIO_TYPE_DISPLAY_NAMES.get(scenario_type, scenario_type)}**")
    if scenario_type in ("DETERMINISTIC", "CUSTOM"):
        st.warning(f"{STRESS_TEST_DISCLAIMER} {rationale}")
    else:
        st.caption(rationale)

    total_portfolio_stress_return = scenario_df["total_portfolio_stress_return"].iloc[0]
    base_portfolio_value = scenario_df["base_portfolio_value"].iloc[0]
    post_stress_portfolio_value = scenario_df["post_stress_portfolio_value"].iloc[0]
    total_loss_amount_inr = scenario_df["loss_amount_inr"].sum()

    kpi_columns = st.columns(3)
    kpi_columns[0].metric("Portfolio Stress Loss %", formatting.format_percent(total_portfolio_stress_return))
    kpi_columns[1].metric("Loss Amount (INR)", formatting.format_inr(total_loss_amount_inr))
    kpi_columns[2].metric("Post-Stress Portfolio Value", formatting.format_inr(post_stress_portfolio_value))

    st.markdown("##### Fund-Wise Stress Contribution")
    display_df = scenario_df.sort_values("fund_loss_contribution").copy()
    table_df = pd.DataFrame(
        {
            "Fund": display_df["fund_label"],
            "Weight": display_df["fund_weight"].apply(formatting.format_percent),
            "Stress Return": display_df["fund_stress_return"].apply(formatting.format_percent),
            "Loss Contribution": display_df["fund_loss_contribution"].apply(formatting.format_percent),
            "Stress Loss Share": display_df["stress_loss_share"].apply(formatting.format_percent),
            "Loss Amount (INR)": display_df["loss_amount_inr"].apply(formatting.format_inr),
            "Largest Contributor": display_df["is_largest_loss_contributor"].map({True: "Yes", False: ""}),
        }
    )
    st.dataframe(table_df, width="stretch", hide_index=True)

    st.markdown("##### Stress Waterfall")
    scenario_name = scenario_df["scenario_name"].iloc[0]
    st.plotly_chart(charts.plot_stress_waterfall(scenario_df, scenario_name), width="stretch")

    st.markdown("##### Allocation Weight vs. Stress Loss Share")
    st.plotly_chart(charts.plot_allocation_vs_stress_loss_share(scenario_df, scenario_name), width="stretch")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("Scenario Stress Testing")
st.caption("What happens to the portfolio's value if a historical shock, an illustrative assumption, or your own custom shock plays out?")

disclosures.render_data_quality_banner()

with st.expander("How to read this page"):
    st.markdown(
        "- Pick a historical, deterministic, or custom scenario in the sidebar. KPI cards show the "
        "**portfolio-level** stress loss; the fund table and waterfall chart break that loss down fund-by-fund.\n"
        "- **Allocation weight is not the same as stress loss share** — the allocation-vs-loss-share chart "
        "flags any fund contributing a disproportionate share of the loss relative to its portfolio weight.\n"
        "- Deterministic and Custom Shock scenarios are **illustrative assumptions, not forecasts**; Historical "
        "Replay scenarios use actual historical returns over an identified worst-case window."
    )

stress_results = dl.load_stress_results()
attribution_results = dl.load_attribution_results()

missing_files = []
if not is_dataframe_usable(stress_results):
    missing_files.append("`02_processed_data/stress_results.csv`")
if not is_dataframe_usable(attribution_results):
    missing_files.append("`02_processed_data/attribution_results.csv`")

if missing_files:
    st.warning(
        "This page needs the following processed data file(s), which are missing or empty:\n\n"
        + "\n".join(f"- {name}" for name in missing_files)
        + "\n\nRun the data pipeline, then reload this page:"
    )
    st.code(REFRESH_COMMAND, language="bash")
    st.stop()

scenario_lookup = stress_results.drop_duplicates("scenario_name").set_index("scenario_name")[
    ["scenario_type", "rationale"]
]
scenario_names = sorted(attribution_results["scenario_name"].dropna().unique().tolist())
if not scenario_names:
    st.warning("No scenarios found in `attribution_results.csv`.")
    st.stop()

default_weights = attribution_results.drop_duplicates("fund_label")[["fund_label", "fund_weight"]].set_index(
    "fund_label"
)["fund_weight"]
default_base_value = (
    float(attribution_results["base_portfolio_value"].iloc[0])
    if "base_portfolio_value" in attribution_results.columns and not attribution_results.empty
    else DEFAULT_BASE_PORTFOLIO_VALUE
)
fund_labels = sorted(default_weights.index.tolist())

with st.sidebar:
    st.header("Scenario Selection")
    selected_scenario = st.selectbox(
        "Scenario", options=scenario_names + [CUSTOM_SCENARIO_LABEL], key="stress_scenario_select"
    )

    fund_shocks = {}
    portfolio_allocations = {}
    base_portfolio_value = default_base_value

    if selected_scenario == CUSTOM_SCENARIO_LABEL:
        st.divider()
        st.subheader("Custom Shock Inputs")
        base_portfolio_value = st.number_input(
            "Base portfolio value (₹)", min_value=0.0, value=default_base_value, step=100_000.0, format="%.0f"
        )

        with st.expander("Custom shock (%) per fund", expanded=True):
            for fund_label in fund_labels:
                fund_shocks[fund_label] = (
                    st.slider(fund_label, min_value=-80.0, max_value=50.0, value=0.0, step=1.0, key=f"shock_{fund_label}")
                    / 100.0
                )

        with st.expander("Portfolio allocation (%) per fund", expanded=True):
            raw_allocations = {}
            for fund_label in fund_labels:
                default_pct = float(default_weights.get(fund_label, 0.0)) * 100.0
                raw_allocations[fund_label] = st.slider(
                    fund_label, min_value=0.0, max_value=100.0, value=default_pct, step=1.0, key=f"weight_{fund_label}"
                )
            raw_total = sum(raw_allocations.values())
            if raw_total > 0:
                portfolio_allocations = {label: value / raw_total for label, value in raw_allocations.items()}
                st.caption(f"Raw total: {raw_total:.0f}% — normalized to 100% before use.")
            else:
                st.warning("Set at least one fund's allocation above 0% to compute a custom shock.")

    st.divider()
    st.caption("This app reads only from `02_processed_data/`. To refresh data, run:")
    st.code(REFRESH_COMMAND, language="bash")

st.subheader(selected_scenario)

if selected_scenario == CUSTOM_SCENARIO_LABEL:
    if not portfolio_allocations:
        st.info("Adjust the portfolio allocation sliders in the sidebar (total must be above 0%) to see results.")
    else:
        live_attribution = run_custom_shock(
            fund_shocks=fund_shocks,
            portfolio_weights=portfolio_allocations,
            base_portfolio_value=base_portfolio_value,
            scenario_name=CUSTOM_SCENARIO_LABEL,
        )
        _render_scenario_results(live_attribution, scenario_type="CUSTOM", rationale=CUSTOM_DISCLOSURE)
else:
    scenario_df = attribution_results[attribution_results["scenario_name"] == selected_scenario]
    scenario_type = (
        scenario_lookup.loc[selected_scenario, "scenario_type"] if selected_scenario in scenario_lookup.index else ""
    )
    rationale = scenario_lookup.loc[selected_scenario, "rationale"] if selected_scenario in scenario_lookup.index else ""
    _render_scenario_results(scenario_df, scenario_type=scenario_type, rationale=rationale)

st.divider()
st.caption("Educational analytics project. Not investment advice.")
