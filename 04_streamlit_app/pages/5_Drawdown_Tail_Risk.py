"""
Page: Drawdown & Tail Risk.

Reads only from 02_processed_data/ (via data_loader.py) — never fetches
live data. Reference: 00_project_control/master_project_instructions.md.md
§23.5.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd
import streamlit as st

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import charts  # noqa: E402
import data_loader as dl  # noqa: E402
import disclosures  # noqa: E402
from utils import format_percent, is_dataframe_usable  # noqa: E402

REFRESH_COMMAND = "python 04_streamlit_app/refresh_data.py"
WORST_DRAWDOWNS_SHOWN = 5
WORST_RETURNS_SHOWN = 10


def _compute_drawdown_episodes(nav_daily_fund: pd.DataFrame) -> List[dict]:
    """
    Identify every peak-to-trough-to-recovery drawdown episode from a
    fund's daily NAV series (same single-pass peak-tracking logic as
    metrics.calculate_max_drawdown_and_recovery, extended to record every
    episode rather than only the single worst one / longest recovery).

    A "recovered" episode ends the moment NAV makes a new all-time high.
    If the fund is still below its last peak as of the most recent
    observation, that final episode is emitted with status "Ongoing" and
    recovery_date=None — never fabricated as recovered.
    """
    df = nav_daily_fund.dropna(subset=["nav"]).sort_values("date").reset_index(drop=True)
    if df.empty:
        return []

    peak_value = df["nav"].iloc[0]
    peak_date = df["date"].iloc[0]
    in_drawdown = False
    trough_value: Optional[float] = None
    trough_date = None
    episodes: List[dict] = []

    for date, value in zip(df["date"], df["nav"]):
        if value >= peak_value:
            if in_drawdown:
                episodes.append(
                    {
                        "peak_date": peak_date,
                        "trough_date": trough_date,
                        "recovery_date": date,
                        "drawdown": float(trough_value / peak_value - 1.0),
                        "status": "Recovered",
                    }
                )
                in_drawdown = False
                trough_value = None
                trough_date = None
            peak_value = value
            peak_date = date
        else:
            in_drawdown = True
            if trough_value is None or value < trough_value:
                trough_value = value
                trough_date = date

    if in_drawdown:
        episodes.append(
            {
                "peak_date": peak_date,
                "trough_date": trough_date,
                "recovery_date": None,
                "drawdown": float(trough_value / peak_value - 1.0),
                "status": "Ongoing (not yet recovered)",
            }
        )

    return episodes


def _episodes_to_display_table(episodes: List[dict]) -> pd.DataFrame:
    """Format drawdown episodes (worst-first) into a display-ready table with duration columns."""
    rows = []
    for episode in episodes:
        peak_date = episode["peak_date"]
        trough_date = episode["trough_date"]
        recovery_date = episode["recovery_date"]
        peak_to_trough_days = (trough_date - peak_date).days
        trough_to_recovery_days = (recovery_date - trough_date).days if recovery_date is not None else None
        rows.append(
            {
                "Peak Date": peak_date.strftime("%d %b %Y"),
                "Trough Date": trough_date.strftime("%d %b %Y"),
                "Recovery Date": recovery_date.strftime("%d %b %Y") if recovery_date is not None else "—",
                "Drawdown": format_percent(episode["drawdown"]),
                "Peak → Trough (days)": str(peak_to_trough_days),
                "Trough → Recovery (days)": str(trough_to_recovery_days) if trough_to_recovery_days is not None else "—",
                "Status": episode["status"],
            }
        )
    return pd.DataFrame(rows)


def _recovery_interpretation_text(episodes: List[dict], metrics_row: pd.Series) -> str:
    """Build a fund-specific narrative explaining the worst drawdown episode's recovery path,
    cross-referenced against metrics_summary.csv's longest-recovery-across-all-episodes figure."""
    if not episodes:
        return "No drawdown episodes were found in this fund's NAV history."

    worst_episode = min(episodes, key=lambda ep: ep["drawdown"])
    peak_date = worst_episode["peak_date"].strftime("%d %b %Y")
    trough_date = worst_episode["trough_date"].strftime("%d %b %Y")
    drawdown_pct = format_percent(worst_episode["drawdown"])
    peak_to_trough_days = (worst_episode["trough_date"] - worst_episode["peak_date"]).days

    if worst_episode["status"] == "Recovered":
        recovery_date = worst_episode["recovery_date"].strftime("%d %b %Y")
        trough_to_recovery_days = (worst_episode["recovery_date"] - worst_episode["trough_date"]).days
        total_days = (worst_episode["recovery_date"] - worst_episode["peak_date"]).days
        narrative = (
            f"This fund's deepest historical drawdown was **{drawdown_pct}**, from a peak on **{peak_date}** to a "
            f"trough on **{trough_date}** ({peak_to_trough_days} days to reach bottom), before fully recovering "
            f"to a new NAV high by **{recovery_date}** — {trough_to_recovery_days} days from trough to recovery, "
            f"{total_days} days peak-to-recovery in total."
        )
    else:
        as_of_date = worst_episode.get("as_of_date")
        days_below_peak = worst_episode.get("days_below_peak")
        narrative = (
            f"This fund's deepest historical drawdown of **{drawdown_pct}** began at a peak on **{peak_date}** and "
            f"troughed on **{trough_date}**; as of the latest available data"
            + (f" ({as_of_date.strftime('%d %b %Y')})" if as_of_date is not None else "")
            + ", the fund **has not yet fully recovered** to that prior peak"
            + (f" — {days_below_peak} days and counting." if days_below_peak is not None else ".")
        )

    longest_recovery_days = metrics_row.get("recovery_period_days")
    if pd.notna(longest_recovery_days):
        if worst_episode["status"] == "Recovered" and int(longest_recovery_days) == int(
            (worst_episode["recovery_date"] - worst_episode["peak_date"]).days
        ):
            narrative += (
                f" This is also the fund's **longest** historical recovery period on record "
                f"({int(longest_recovery_days)} days)."
            )
        else:
            narrative += (
                f" Note: the fund's *longest* historical recovery period on record was **"
                f"{int(longest_recovery_days)} days**, which was a *different* (not necessarily the deepest) "
                "drawdown episode — depth and recovery duration do not always coincide."
            )
    else:
        narrative += (
            " The fund has never completed a full recovery from any drawdown within the observed window, so no "
            "longest-recovery figure is available (never fabricated as 0 or an estimate)."
        )

    return narrative


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("Drawdown & Tail Risk")
st.caption("How deep did losses get, how long did they last, and what does the return distribution's tail look like?")

disclosures.render_data_quality_banner()

nav_daily = dl.load_nav_daily()
returns_daily = dl.load_returns_daily()
returns_monthly = dl.load_returns_monthly()
metrics_summary = dl.load_metrics_summary()

missing_files = []
if not is_dataframe_usable(nav_daily):
    missing_files.append("`02_processed_data/nav_daily_clean.csv`")
if not is_dataframe_usable(returns_daily):
    missing_files.append("`02_processed_data/returns_daily.csv`")
if not is_dataframe_usable(returns_monthly):
    missing_files.append("`02_processed_data/returns_monthly.csv`")
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
    selected_fund = st.selectbox("Fund", options=fund_labels, key="drawdown_tail_risk_fund_select")

    st.divider()
    st.caption("This app reads only from `02_processed_data/`. To refresh data, run:")
    st.code(REFRESH_COMMAND, language="bash")

st.subheader(selected_fund)

fund_metrics_rows = metrics_summary[metrics_summary["fund_label"] == selected_fund]
if fund_metrics_rows.empty:
    st.info(f"No metrics available for '{selected_fund}' in `metrics_summary.csv`.")
    st.stop()
fund_metrics_row = fund_metrics_rows.iloc[0]

metric_columns = st.columns(4)
metric_columns[0].metric("Max Drawdown", format_percent(fund_metrics_row["max_drawdown"]))
metric_columns[1].metric("Daily VaR 95", format_percent(fund_metrics_row["daily_var_95"]))
metric_columns[2].metric("Daily CVaR 95", format_percent(fund_metrics_row["daily_cvar_95"]))
recovery_days = fund_metrics_row["recovery_period_days"]
metric_columns[3].metric(
    "Longest Recovery Period", f"{recovery_days:.0f} days" if pd.notna(recovery_days) else "Not yet recovered"
)

st.divider()

# ---------------------------------------------------------------------------
# Drawdown chart
# ---------------------------------------------------------------------------

st.markdown("#### Drawdown from Running Peak")
st.plotly_chart(charts.plot_drawdown(nav_daily, fund_labels=[selected_fund]), width="stretch")

# ---------------------------------------------------------------------------
# Worst drawdown table
# ---------------------------------------------------------------------------

st.markdown(f"#### Worst {WORST_DRAWDOWNS_SHOWN} Drawdown Episodes")
fund_nav = nav_daily[nav_daily["fund_label"] == selected_fund]
episodes = _compute_drawdown_episodes(fund_nav)
if not episodes:
    st.info(f"No drawdown episodes found for '{selected_fund}'.")
else:
    if episodes[-1]["status"] != "Recovered":
        episodes[-1]["as_of_date"] = fund_nav["date"].max()
        episodes[-1]["days_below_peak"] = (fund_nav["date"].max() - episodes[-1]["peak_date"]).days

    worst_episodes = sorted(episodes, key=lambda ep: ep["drawdown"])[:WORST_DRAWDOWNS_SHOWN]
    st.dataframe(_episodes_to_display_table(worst_episodes), width="stretch", hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Daily return distribution + Daily VaR 95 / CVaR 95 visual
# ---------------------------------------------------------------------------

st.markdown("#### Daily Return Distribution — Daily VaR 95 / CVaR 95")
st.plotly_chart(
    charts.plot_return_distribution(
        returns_daily,
        selected_fund,
        var_95=fund_metrics_row["daily_var_95"],
        cvar_95=fund_metrics_row["daily_cvar_95"],
    ),
    width="stretch",
)

st.divider()

# ---------------------------------------------------------------------------
# Worst 10 daily / monthly returns
# ---------------------------------------------------------------------------

col_daily, col_monthly = st.columns(2)

with col_daily:
    st.markdown(f"#### Worst {WORST_RETURNS_SHOWN} Daily Returns")
    fund_daily_returns = returns_daily[returns_daily["fund_label"] == selected_fund].dropna(subset=["daily_return"])
    worst_daily = fund_daily_returns.sort_values("daily_return").head(WORST_RETURNS_SHOWN)
    if worst_daily.empty:
        st.info(f"No daily return data for '{selected_fund}'.")
    else:
        display_df = pd.DataFrame(
            {
                "Date": pd.to_datetime(worst_daily["date"]).dt.strftime("%d %b %Y"),
                "Daily Return": worst_daily["daily_return"].apply(format_percent),
            }
        )
        st.dataframe(display_df, width="stretch", hide_index=True)

with col_monthly:
    st.markdown(f"#### Worst {WORST_RETURNS_SHOWN} Monthly Returns")
    fund_monthly_returns = returns_monthly[returns_monthly["fund_label"] == selected_fund].dropna(
        subset=["monthly_return"]
    )
    worst_monthly = fund_monthly_returns.sort_values("monthly_return").head(WORST_RETURNS_SHOWN)
    if worst_monthly.empty:
        st.info(f"No monthly return data for '{selected_fund}'.")
    else:
        display_df = pd.DataFrame(
            {
                "Month": pd.to_datetime(worst_monthly["month_end_date"]).dt.strftime("%b %Y"),
                "Monthly Return": worst_monthly["monthly_return"].apply(format_percent),
            }
        )
        st.dataframe(display_df, width="stretch", hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Recovery period interpretation
# ---------------------------------------------------------------------------

st.markdown("#### Interpretation: Recovery Period")
st.info(_recovery_interpretation_text(episodes, fund_metrics_row) if episodes else "No drawdown episodes to interpret.")

st.caption(
    "All figures above describe trailing historical NAV/return behaviour only — not a forecast of future "
    "drawdowns or recovery speed."
)
st.caption("Educational analytics project. Not investment advice.")
