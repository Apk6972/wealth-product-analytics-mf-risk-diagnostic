"""
Page: Benchmark Behaviour.

Reads only from 02_processed_data/ (via data_loader.py) — never fetches
live data. Reference: 00_project_control/master_project_instructions.md.md
§23.3.

Each fund is compared only against its own fund-specific primary benchmark
(see 01_raw_data/scheme_master/benchmark_map.csv, surfaced here via
benchmark_metrics.csv's fund_label/benchmark_label pairing rather than by
reading the raw config file directly).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import charts  # noqa: E402
import data_loader as dl  # noqa: E402
import disclosures  # noqa: E402
from benchmarks import ROLLING_WINDOW_DAYS, align_fund_benchmark_returns  # noqa: E402
from returns import calculate_benchmark_daily_returns  # noqa: E402
from utils import TRADING_DAYS_PER_YEAR, format_percent, is_dataframe_usable  # noqa: E402

REFRESH_COMMAND = "python 04_streamlit_app/refresh_data.py"
TEMPLATE = "plotly_white"

PROXY_SOURCE_QUALITIES = {
    "PRICE_INDEX_PROXY_NOT_TRI": (
        "warning",
        "This fund's primary benchmark ('{benchmark_label}') is currently sourced as a **price-index proxy, "
        "NOT an official Total Return Index (TRI)** series (`source_quality = PRICE_INDEX_PROXY_NOT_TRI`). "
        "Price-index levels omit reinvested dividends, so beta/tracking error/capture figures below are "
        "computed against a slightly understated benchmark and should be read with that caveat.",
    ),
    "DISCLOSED_APPROXIMATION": (
        "info",
        "This fund's primary benchmark ('{benchmark_label}') is a disclosed, internally-constructed "
        "approximation (`source_quality = DISCLOSED_APPROXIMATION`), not a directly observed market series. "
        "See the Methodology page for how it is built.",
    ),
}


def _format_ratio(value: float) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.2f}"


def _rolling_excess_return_figure(rolling_excess_return: pd.DataFrame, fund_label: str, benchmark_label: str) -> go.Figure:
    """Page-local chart: rolling annualized excess return (fund - benchmark), built from
    benchmarks.align_fund_benchmark_returns() daily excess returns. Not persisted to any
    processed CSV — recomputed on the fly, matching this page's read-only-from-CSV inputs."""
    if rolling_excess_return.empty or rolling_excess_return["rolling_excess_return_ann"].dropna().empty:
        fig = go.Figure()
        fig.add_annotation(
            text="Rolling excess return: not enough aligned fund/benchmark history yet.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font={"size": 14, "color": "gray"},
        )
        fig.update_layout(xaxis={"visible": False}, yaxis={"visible": False}, template=TEMPLATE, height=350)
        return fig

    fig = go.Figure(
        go.Scatter(
            x=rolling_excess_return["date"],
            y=rolling_excess_return["rolling_excess_return_ann"],
            mode="lines",
            name="Rolling excess return (ann.)",
            line={"color": "steelblue"},
            hovertemplate="%{x|%d %b %Y}: %{y:.1%}<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    fig.update_layout(
        title=f"Rolling {ROLLING_WINDOW_DAYS}-Day Excess Return (Annualized) — {fund_label} vs. {benchmark_label}",
        xaxis_title="Date",
        yaxis_title="Annualized excess return",
        yaxis_tickformat=".1%",
        template=TEMPLATE,
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("Benchmark Behaviour")
st.caption("How much of a fund's return path is explained by its own benchmark — and how much is not.")

disclosures.render_data_quality_banner()

nav_daily = dl.load_nav_daily()
benchmark_daily = dl.load_benchmark_daily()
returns_daily = dl.load_returns_daily()
benchmark_metrics = dl.load_benchmark_metrics()
rolling_benchmark_metrics = dl.load_rolling_benchmark_metrics()

missing_files = []
if not is_dataframe_usable(nav_daily):
    missing_files.append("`02_processed_data/nav_daily_clean.csv`")
if not is_dataframe_usable(benchmark_daily):
    missing_files.append("`02_processed_data/benchmark_daily.csv`")
if not is_dataframe_usable(returns_daily):
    missing_files.append("`02_processed_data/returns_daily.csv`")
if not is_dataframe_usable(benchmark_metrics):
    missing_files.append("`02_processed_data/benchmark_metrics.csv`")
if not is_dataframe_usable(rolling_benchmark_metrics):
    missing_files.append("`02_processed_data/rolling_benchmark_metrics.csv`")

if missing_files:
    st.warning(
        "This page needs the following processed data file(s), which are missing or empty:\n\n"
        + "\n".join(f"- {name}" for name in missing_files)
        + "\n\nRun the data pipeline, then reload this page:"
    )
    st.code(REFRESH_COMMAND, language="bash")
    st.stop()

fund_labels = sorted(benchmark_metrics["fund_label"].dropna().unique().tolist())
if not fund_labels:
    st.warning("No fund/benchmark pairings found in `benchmark_metrics.csv`.")
    st.stop()

with st.sidebar:
    st.header("Fund Selection")
    selected_fund = st.selectbox("Fund", options=fund_labels, key="benchmark_behaviour_fund_select")

    st.divider()
    st.caption("This app reads only from `02_processed_data/`. To refresh data, run:")
    st.code(REFRESH_COMMAND, language="bash")

st.subheader(selected_fund)

fund_metrics_rows = benchmark_metrics[benchmark_metrics["fund_label"] == selected_fund]
if fund_metrics_rows.empty:
    st.info(f"No benchmark-relative metrics available for '{selected_fund}'.")
    st.stop()
fund_metrics_row = fund_metrics_rows.iloc[0]
primary_benchmark = fund_metrics_row["benchmark_label"]

# ---------------------------------------------------------------------------
# Primary benchmark display + source_quality warning
# ---------------------------------------------------------------------------

st.markdown(f"#### Primary Benchmark: `{primary_benchmark}`")

benchmark_source_rows = benchmark_daily[benchmark_daily["benchmark_label"] == primary_benchmark]
source_qualities = benchmark_source_rows["source_quality"].dropna().unique().tolist() if not benchmark_source_rows.empty else []

if not source_qualities:
    st.info(f"No `source_quality` information found for '{primary_benchmark}' in `benchmark_daily.csv`.")
else:
    for source_quality in source_qualities:
        if source_quality in PROXY_SOURCE_QUALITIES:
            level, message_template = PROXY_SOURCE_QUALITIES[source_quality]
            message = message_template.format(benchmark_label=primary_benchmark)
            (st.warning if level == "warning" else st.info)(message)
    if not any(sq in PROXY_SOURCE_QUALITIES for sq in source_qualities):
        st.success(f"Source quality: {', '.join(source_qualities)} — an authentic, directly-sourced series.")

# ---------------------------------------------------------------------------
# Benchmark-relative metric cards
# ---------------------------------------------------------------------------

metric_columns = st.columns(6)
metric_columns[0].metric("Beta", _format_ratio(fund_metrics_row["beta"]))
metric_columns[1].metric("Tracking Error (Ann.)", format_percent(fund_metrics_row["tracking_error"]))
metric_columns[2].metric("Information Ratio", _format_ratio(fund_metrics_row["information_ratio"]))
metric_columns[3].metric("Excess Return (Ann.)", format_percent(fund_metrics_row["excess_return_ann"]))
metric_columns[4].metric("Upside Capture", format_percent(fund_metrics_row["upside_capture"], decimals=0))
metric_columns[5].metric("Downside Capture", format_percent(fund_metrics_row["downside_capture"], decimals=0))

st.divider()

# ---------------------------------------------------------------------------
# Fund vs. benchmark growth
# ---------------------------------------------------------------------------

st.markdown("#### Fund vs. Benchmark Growth")
st.plotly_chart(
    charts.plot_fund_vs_benchmark_growth(nav_daily, benchmark_daily, selected_fund, primary_benchmark),
    width="stretch",
)

# ---------------------------------------------------------------------------
# Rolling excess return (computed on the fly from aligned daily returns)
# ---------------------------------------------------------------------------

st.markdown("#### Rolling Excess Return")
benchmark_returns_daily = calculate_benchmark_daily_returns(benchmark_daily)
aligned = align_fund_benchmark_returns(returns_daily, benchmark_returns_daily, selected_fund, primary_benchmark)
if not aligned.empty:
    aligned = aligned.copy()
    aligned["rolling_excess_return_ann"] = (
        aligned["excess_return"].rolling(window=ROLLING_WINDOW_DAYS, min_periods=ROLLING_WINDOW_DAYS).mean()
        * TRADING_DAYS_PER_YEAR
    )
st.plotly_chart(_rolling_excess_return_figure(aligned, selected_fund, primary_benchmark), width="stretch")

# ---------------------------------------------------------------------------
# Rolling beta / tracking error / information ratio
# ---------------------------------------------------------------------------

st.markdown("#### Rolling Beta")
st.plotly_chart(charts.plot_rolling_beta(rolling_benchmark_metrics, fund_labels=[selected_fund]), width="stretch")

st.markdown("#### Rolling Tracking Error")
st.plotly_chart(
    charts.plot_rolling_tracking_error(rolling_benchmark_metrics, fund_labels=[selected_fund]), width="stretch"
)

st.markdown("#### Rolling Information Ratio")
st.plotly_chart(
    charts.plot_rolling_information_ratio(rolling_benchmark_metrics, fund_labels=[selected_fund]), width="stretch"
)

# ---------------------------------------------------------------------------
# Upside / downside capture (all funds, for relative positioning)
# ---------------------------------------------------------------------------

st.markdown("#### Upside / Downside Capture — All Funds")
st.caption("Each fund plotted against its own primary benchmark. Top-left is historically most favourable.")
st.plotly_chart(charts.plot_upside_downside_capture_scatter(benchmark_metrics), width="stretch")

st.divider()
st.markdown(
    "**How to read this page:** a fund can beat its benchmark on raw return while still failing this page's "
    "diagnostic — e.g. a beta well above 1, low upside capture combined with high downside capture, or a "
    "negative rolling information ratio all indicate the excess return has not been reliably compensated risk."
)
st.caption("Educational analytics project. Not investment advice.")
