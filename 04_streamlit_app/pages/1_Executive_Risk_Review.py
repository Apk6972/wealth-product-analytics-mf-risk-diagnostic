"""
Page: Executive Risk Review.

Reads only from 02_processed_data/ (via data_loader.py) — never fetches
live data. Reference: 00_project_control/master_project_instructions.md.md
§23.1.

Portfolio-level KPIs (CAGR, volatility, max drawdown, daily CVaR 95,
recovery period) are not a separate processed CSV — there is no
"portfolio_metrics.csv" artifact in the pipeline. Instead, this page blends
each fund's already-computed daily returns (returns_daily.csv) using the
portfolio weights already used by the attribution engine
(attribution_results.csv's fund_weight column) into a single fixed-weight
daily return series, then reuses metrics.py's existing pure calculation
functions on that blended series - the same formulas already audited for
per-fund metrics, just applied to a blended portfolio series computed here
rather than fetched from a file. No live data is fetched at any point.
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
from metrics import (  # noqa: E402
    calculate_annualized_volatility,
    calculate_cagr,
    calculate_max_drawdown_and_recovery,
    calculate_var_cvar,
)
from utils import (  # noqa: E402
    DATA_START_DATE,
    DEFAULT_RISK_FREE_RATE,
    format_inr_compact,
    format_percent,
    is_dataframe_usable,
)

REFRESH_COMMAND = "python 04_streamlit_app/refresh_data.py"
PORTFOLIO_SERIES_LABEL = "Portfolio (Blended)"


# ---------------------------------------------------------------------------
# Portfolio series construction (local to this page — see module docstring)
# ---------------------------------------------------------------------------

def _build_portfolio_weights(attribution_results: pd.DataFrame) -> pd.Series:
    """One weight per fund_label, taken from attribution_results.csv (already
    validated to sum to 1.0 by the attribution engine)."""
    weights = attribution_results.drop_duplicates("fund_label").set_index("fund_label")["fund_weight"].dropna()
    return weights


def _build_portfolio_series(
    nav_daily: pd.DataFrame,
    returns_daily: pd.DataFrame,
    weights: pd.Series,
    base_value: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Blend fund-level daily returns into a single fixed-weight (rebalanced
    daily) portfolio daily-return series, anchored to a synthetic NAV path
    starting at `base_value` on the first date every weighted fund has a
    live NAV observation. Returns (portfolio_nav_df, portfolio_returns_df)
    shaped exactly like the "nav_daily_fund" / "daily_returns_fund" frames
    metrics.py's pure calculation functions expect.
    """
    fund_labels = [label for label in weights.index if label in set(nav_daily["fund_label"].unique())]
    if not fund_labels:
        return pd.DataFrame(columns=["date", "nav"]), pd.DataFrame(columns=["date", "daily_return"])

    normalized_weights = weights.reindex(fund_labels)
    normalized_weights = normalized_weights / normalized_weights.sum()

    nav_wide = nav_daily[nav_daily["fund_label"].isin(fund_labels)].pivot(
        index="date", columns="fund_label", values="nav"
    )
    nav_wide = nav_wide.reindex(columns=fund_labels).dropna(how="any").sort_index()
    if nav_wide.empty:
        return pd.DataFrame(columns=["date", "nav"]), pd.DataFrame(columns=["date", "daily_return"])
    common_start = nav_wide.index[0]

    returns_wide = returns_daily[returns_daily["fund_label"].isin(fund_labels)].pivot(
        index="date", columns="fund_label", values="daily_return"
    )
    returns_wide = returns_wide.reindex(columns=fund_labels)
    returns_wide = returns_wide[returns_wide.index >= common_start].dropna(how="any").sort_index()
    if returns_wide.empty:
        return pd.DataFrame(columns=["date", "nav"]), pd.DataFrame(columns=["date", "daily_return"])

    blended_daily_return = returns_wide.mul(normalized_weights, axis=1).sum(axis=1)

    growth_index = pd.concat([pd.Series([1.0], index=[common_start]), (1.0 + blended_daily_return).cumprod()])
    portfolio_nav = (growth_index * base_value).sort_index()

    portfolio_nav_df = pd.DataFrame({"date": portfolio_nav.index, "nav": portfolio_nav.values})
    portfolio_returns_df = pd.DataFrame(
        {"date": blended_daily_return.index, "daily_return": blended_daily_return.values}
    )
    return portfolio_nav_df, portfolio_returns_df


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("MF Risk Diagnostic Module — Executive Risk Review")
st.markdown("##### *What risk created the return?*")

disclosures.render_data_quality_banner()

with st.sidebar:
    st.header("Assumptions")
    base_portfolio_value = st.number_input(
        "Base portfolio value (₹)",
        min_value=100_000.0,
        value=10_000_000.0,
        step=100_000.0,
        format="%.0f",
        help=(
            "Scales the Growth chart and translates stress-scenario percentage "
            "losses into illustrative ₹ figures. Does not change any underlying "
            "return or risk calculation, which are all computed on percentages."
        ),
    )
    st.caption(f"= {format_inr_compact(base_portfolio_value)}")

    risk_free_rate_percent = st.number_input(
        "Risk-free rate (% p.a.)",
        min_value=0.0,
        max_value=20.0,
        value=DEFAULT_RISK_FREE_RATE * 100,
        step=0.25,
        help="The annual risk-free rate assumption used for Sharpe/Sortino-style risk-adjusted context elsewhere in this app.",
    )
    risk_free_rate = risk_free_rate_percent / 100

    st.divider()
    st.caption("This app reads only from `02_processed_data/`. To refresh NAV, benchmark, and calculated data, run:")
    st.code(REFRESH_COMMAND, language="bash")

st.info(
    "**The objective is not to rank funds by return.** The objective is to understand what risk "
    "created the return, how painful the return path was, and which sleeve may break first under stress."
)

# ---------------------------------------------------------------------------
# Load processed data (never live) and check availability
# ---------------------------------------------------------------------------

nav_daily = dl.load_nav_daily()
returns_daily = dl.load_returns_daily()
attribution_results = dl.load_attribution_results()

missing_files = []
if not is_dataframe_usable(nav_daily):
    missing_files.append("`02_processed_data/nav_daily_clean.csv`")
if not is_dataframe_usable(returns_daily):
    missing_files.append("`02_processed_data/returns_daily.csv`")
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

# Defensive clip to the project's documented data horizon (data_dictionary.md
# §4.1: nav_daily_clean.csv should already be filtered to date >= 2021-01-01).
# returns_daily.csv is correctly bounded; nav_daily_clean.csv as currently
# written by the pipeline is not, so this guards this page's calculations
# against silently blending in pre-2021 history the rest of the app doesn't
# use (e.g. metrics_summary.csv's CAGR windows).
nav_daily = nav_daily[nav_daily["date"] >= pd.Timestamp(DATA_START_DATE)]

portfolio_weights = _build_portfolio_weights(attribution_results)
portfolio_nav_df, portfolio_returns_df = _build_portfolio_series(
    nav_daily, returns_daily, portfolio_weights, base_portfolio_value
)

if portfolio_nav_df.empty or portfolio_returns_df.empty:
    st.error(
        "Could not construct a blended portfolio series — no overlapping NAV/return history was found "
        "across the funds in `portfolio_weights.csv` (via `attribution_results.csv`)."
    )
    st.stop()

with st.expander("Portfolio composition used for the KPIs and charts below"):
    composition_df = portfolio_weights.rename("weight").reset_index().rename(columns={"index": "fund_label"})
    composition_df["weight"] = composition_df["weight"].apply(lambda w: format_percent(w))
    st.dataframe(composition_df, hide_index=True, width="stretch")
    st.caption(
        "Portfolio-level figures below are a fixed-weight (rebalanced daily) blend of each fund's daily "
        "returns using these weights — there is no separate stored 'portfolio' series in "
        "02_processed_data/."
    )

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

portfolio_cagr = calculate_cagr(portfolio_nav_df)
portfolio_volatility = calculate_annualized_volatility(portfolio_returns_df["daily_return"])
portfolio_max_drawdown, portfolio_recovery_days = calculate_max_drawdown_and_recovery(portfolio_returns_df)
_, portfolio_daily_cvar_95 = calculate_var_cvar(portfolio_returns_df["daily_return"])

worst_scenario_name = None
worst_stress_loss_pct = float("nan")
scenario_totals = attribution_results.drop_duplicates("scenario_name")[
    ["scenario_name", "total_portfolio_stress_return"]
].dropna()
if not scenario_totals.empty:
    worst_row = scenario_totals.loc[scenario_totals["total_portfolio_stress_return"].idxmin()]
    worst_scenario_name = str(worst_row["scenario_name"])
    worst_stress_loss_pct = float(worst_row["total_portfolio_stress_return"])
worst_stress_loss_inr = (
    base_portfolio_value * worst_stress_loss_pct if pd.notna(worst_stress_loss_pct) else float("nan")
)

st.subheader("Portfolio Risk Snapshot")

row1 = st.columns(3)
row1[0].metric("Portfolio CAGR", format_percent(portfolio_cagr))
row1[1].metric("Portfolio Volatility (Ann.)", format_percent(portfolio_volatility))
row1[2].metric("Max Drawdown", format_percent(portfolio_max_drawdown))

row2 = st.columns(3)
row2[0].metric("Daily CVaR 95", format_percent(portfolio_daily_cvar_95))
row2[1].metric("Worst Stress Loss", format_percent(worst_stress_loss_pct))
row2[2].metric(
    "Longest Recovery Period",
    f"{portfolio_recovery_days:.0f} days" if pd.notna(portfolio_recovery_days) else "Not yet recovered",
)

if worst_scenario_name is not None:
    st.caption(
        f"Worst modeled stress scenario: **{worst_scenario_name}** — {format_percent(worst_stress_loss_pct)} "
        f"of portfolio value, illustratively ≈ {format_inr_compact(worst_stress_loss_inr)} on a "
        f"{format_inr_compact(base_portfolio_value)} base."
    )

st.divider()

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

st.subheader(f"Growth of {format_inr_compact(base_portfolio_value)}")
portfolio_nav_for_chart = portfolio_nav_df.copy()
portfolio_nav_for_chart["fund_label"] = PORTFOLIO_SERIES_LABEL
combined_nav_for_growth_chart = pd.concat(
    [nav_daily[["date", "fund_label", "nav"]], portfolio_nav_for_chart[["date", "fund_label", "nav"]]],
    ignore_index=True,
)
st.plotly_chart(
    charts.plot_growth_of_investment(
        combined_nav_for_growth_chart,
        base_value=base_portfolio_value,
        fund_labels=list(portfolio_weights.index) + [PORTFOLIO_SERIES_LABEL],
    ),
    width="stretch",
)
st.caption(
    f"**{PORTFOLIO_SERIES_LABEL}** is the blended portfolio path; the remaining lines show each fund grown "
    "individually from its own first available NAV date, for context."
)

st.subheader("Scenario Loss Ranking")
st.plotly_chart(charts.plot_scenario_loss_ranking(attribution_results), width="stretch")

st.subheader("Allocation Weight vs. Stress Loss Share")
scenario_options = sorted(attribution_results["scenario_name"].dropna().unique().tolist())
default_scenario_index = scenario_options.index(worst_scenario_name) if worst_scenario_name in scenario_options else 0
selected_scenario = st.selectbox(
    "Scenario",
    options=scenario_options,
    index=default_scenario_index,
    key="executive_review_scenario_select",
)
st.plotly_chart(
    charts.plot_allocation_vs_stress_loss_share(attribution_results, selected_scenario), width="stretch"
)
st.caption(
    "A fund whose stress loss share bar is taller than its allocation weight bar is contributing "
    "disproportionately to the modeled loss in this scenario."
)

st.divider()
st.caption("Educational analytics project. Not investment advice.")
