"""
Charts Module — shared Plotly chart builders for the Streamlit app.

Reference: 00_project_control/master_project_instructions.md.md §23
(Streamlit App Layout) for the chart types each page requires.

Rule: every chart must answer an investment question and be paired with an
interpretation on the page that uses it (enforced on the Streamlit pages
themselves, not here).

Design notes:
- Every function returns a `plotly.graph_objects.Figure` rather than
  rendering directly (no `st.plotly_chart(...)` call inside this module),
  so charts.py stays Streamlit-agnostic and testable outside a running app.
- Every function is defensive: if the required input DataFrame(s) are
  missing/empty/malformed, it returns an annotated placeholder figure instead
  of raising, matching data_loader.py's "never crash the page" philosophy.
- Functions take already-loaded DataFrames (from data_loader.py) as
  arguments; this module never reads files itself.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from utils import format_inr_compact, has_required_columns, is_dataframe_usable  # noqa: E402

TEMPLATE = "plotly_white"


def _empty_figure(message: str) -> go.Figure:
    """Placeholder figure shown when the required data isn't available yet."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 14, "color": "gray"},
        align="center",
    )
    fig.update_layout(
        xaxis={"visible": False},
        yaxis={"visible": False},
        template=TEMPLATE,
        height=350,
    )
    return fig


# ---------------------------------------------------------------------------
# Growth / drawdown
# ---------------------------------------------------------------------------

def plot_growth_of_investment(
    nav_daily: pd.DataFrame,
    base_value: float = 10_000_000,
    fund_labels: Optional[List[str]] = None,
) -> go.Figure:
    """
    Growth of a base investment (e.g. "Growth of ₹1 crore") chart: each
    fund's NAV is rebased to `base_value` at its own first available
    observation and plotted as a cumulative wealth path.
    """
    if not is_dataframe_usable(nav_daily) or not has_required_columns(nav_daily, ["date", "fund_label", "nav"]):
        return _empty_figure("Growth chart: NAV data is not available yet.")

    df = nav_daily.copy()
    if fund_labels:
        df = df[df["fund_label"].isin(fund_labels)]
    df = df.dropna(subset=["nav"]).sort_values(["fund_label", "date"])
    if df.empty:
        return _empty_figure("Growth chart: no NAV observations for the selected fund(s).")

    fig = go.Figure()
    for fund_label, fund_df in df.groupby("fund_label"):
        wealth = base_value * (fund_df["nav"] / fund_df["nav"].iloc[0])
        fig.add_trace(
            go.Scatter(
                x=fund_df["date"],
                y=wealth,
                mode="lines",
                name=fund_label,
                hovertemplate="%{x|%d %b %Y}<br>" + str(fund_label) + ": ₹%{y:,.0f}<extra></extra>",
            )
        )

    fig.update_layout(
        title=f"Growth of {format_inr_compact(base_value)}",
        xaxis_title="Date",
        yaxis_title="Portfolio value (₹)",
        hovermode="x unified",
        legend_title="Fund",
        template=TEMPLATE,
    )
    return fig


def plot_drawdown(nav_daily: pd.DataFrame, fund_labels: Optional[List[str]] = None) -> go.Figure:
    """Drawdown-from-running-peak chart: NAV / running peak NAV - 1, per fund."""
    if not is_dataframe_usable(nav_daily) or not has_required_columns(nav_daily, ["date", "fund_label", "nav"]):
        return _empty_figure("Drawdown chart: NAV data is not available yet.")

    df = nav_daily.copy()
    if fund_labels:
        df = df[df["fund_label"].isin(fund_labels)]
    df = df.dropna(subset=["nav"]).sort_values(["fund_label", "date"])
    if df.empty:
        return _empty_figure("Drawdown chart: no NAV observations for the selected fund(s).")

    fig = go.Figure()
    for fund_label, fund_df in df.groupby("fund_label"):
        running_peak = fund_df["nav"].cummax()
        drawdown = fund_df["nav"] / running_peak - 1
        fig.add_trace(
            go.Scatter(
                x=fund_df["date"],
                y=drawdown,
                mode="lines",
                name=fund_label,
                hovertemplate="%{x|%d %b %Y}<br>" + str(fund_label) + ": %{y:.1%}<extra></extra>",
            )
        )

    fig.update_layout(
        title="Drawdown from Running Peak NAV",
        xaxis_title="Date",
        yaxis_title="Drawdown",
        yaxis_tickformat=".0%",
        hovermode="x unified",
        legend_title="Fund",
        template=TEMPLATE,
    )
    return fig


def plot_fund_vs_benchmark_growth(
    nav_daily: pd.DataFrame,
    benchmark_daily: pd.DataFrame,
    fund_label: str,
    benchmark_label: str,
    base_value: float = 100,
) -> go.Figure:
    """
    Fund vs benchmark cumulative growth comparison chart. Both series are
    rebased to `base_value` at the later of their two first available
    dates, so the comparison starts from a fair common baseline.
    """
    fund_columns_ok = is_dataframe_usable(nav_daily) and has_required_columns(nav_daily, ["date", "fund_label", "nav"])
    bench_columns_ok = is_dataframe_usable(benchmark_daily) and has_required_columns(
        benchmark_daily, ["date", "benchmark_label", "tri_value"]
    )
    if not fund_columns_ok or not bench_columns_ok:
        return _empty_figure("Fund vs. benchmark growth: data is not available yet.")

    fund_df = nav_daily[nav_daily["fund_label"] == fund_label].dropna(subset=["nav"]).sort_values("date")
    bench_df = benchmark_daily[benchmark_daily["benchmark_label"] == benchmark_label].dropna(
        subset=["tri_value"]
    ).sort_values("date")
    if fund_df.empty or bench_df.empty:
        return _empty_figure(f"No data available for '{fund_label}' vs. '{benchmark_label}'.")

    common_start = max(fund_df["date"].iloc[0], bench_df["date"].iloc[0])
    fund_df = fund_df[fund_df["date"] >= common_start]
    bench_df = bench_df[bench_df["date"] >= common_start]
    if fund_df.empty or bench_df.empty:
        return _empty_figure(f"No overlapping date range between '{fund_label}' and '{benchmark_label}'.")

    fund_index = base_value * fund_df["nav"] / fund_df["nav"].iloc[0]
    bench_index = base_value * bench_df["tri_value"] / bench_df["tri_value"].iloc[0]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fund_df["date"], y=fund_index, mode="lines", name=fund_label))
    fig.add_trace(
        go.Scatter(x=bench_df["date"], y=bench_index, mode="lines", name=benchmark_label, line={"dash": "dot"})
    )
    fig.update_layout(
        title=f"{fund_label} vs. {benchmark_label} — Indexed Growth (base = {base_value})",
        xaxis_title="Date",
        yaxis_title=f"Indexed value (base = {base_value})",
        hovermode="x unified",
        legend_title="",
        template=TEMPLATE,
    )
    return fig


# ---------------------------------------------------------------------------
# Monthly / daily return distribution
# ---------------------------------------------------------------------------

def plot_monthly_returns_bar(returns_monthly: pd.DataFrame, fund_label: str) -> go.Figure:
    """Monthly return bar chart for a single fund, coloured by sign."""
    if not is_dataframe_usable(returns_monthly) or not has_required_columns(
        returns_monthly, ["fund_label", "month_end_date", "monthly_return"]
    ):
        return _empty_figure("Monthly returns: data is not available yet.")

    fund_df = returns_monthly[returns_monthly["fund_label"] == fund_label].dropna(subset=["monthly_return"])
    fund_df = fund_df.sort_values("month_end_date")
    if fund_df.empty:
        return _empty_figure(f"No monthly return data for '{fund_label}'.")

    colors = ["seagreen" if value >= 0 else "crimson" for value in fund_df["monthly_return"]]
    fig = go.Figure(
        go.Bar(
            x=fund_df["month_end_date"],
            y=fund_df["monthly_return"],
            marker_color=colors,
            hovertemplate="%{x|%b %Y}: %{y:.1%}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"Monthly Returns — {fund_label}",
        xaxis_title="Month",
        yaxis_title="Monthly return",
        yaxis_tickformat=".1%",
        template=TEMPLATE,
    )
    return fig


def plot_return_distribution(
    returns_daily: pd.DataFrame,
    fund_label: str,
    var_95: Optional[float] = None,
    cvar_95: Optional[float] = None,
    bins: int = 60,
) -> go.Figure:
    """Daily return distribution histogram, optionally overlaid with Daily VaR 95 / CVaR 95 reference lines."""
    if not is_dataframe_usable(returns_daily) or not has_required_columns(returns_daily, ["fund_label", "daily_return"]):
        return _empty_figure("Return distribution: data is not available yet.")

    fund_df = returns_daily[returns_daily["fund_label"] == fund_label].dropna(subset=["daily_return"])
    if fund_df.empty:
        return _empty_figure(f"No daily return data for '{fund_label}'.")

    fig = px.histogram(fund_df, x="daily_return", nbins=bins, template=TEMPLATE)
    fig.update_traces(marker_color="steelblue", hovertemplate="Daily return: %{x:.1%}<br>Count: %{y}<extra></extra>")

    if var_95 is not None and pd.notna(var_95):
        fig.add_vline(
            x=var_95, line_dash="dash", line_color="orange",
            annotation_text=f"Daily VaR 95: {var_95:.1%}", annotation_position="top",
        )
    if cvar_95 is not None and pd.notna(cvar_95):
        fig.add_vline(
            x=cvar_95, line_dash="dash", line_color="crimson",
            annotation_text=f"Daily CVaR 95: {cvar_95:.1%}", annotation_position="bottom",
        )

    fig.update_layout(
        title=f"Daily Return Distribution — {fund_label}",
        xaxis_title="Daily return",
        xaxis_tickformat=".1%",
        yaxis_title="Frequency (trading days)",
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Rolling metrics (long-form rolling_metrics.csv: date_or_month, fund_label,
# metric_name, metric_value, frequency)
# ---------------------------------------------------------------------------

_ROLLING_METRIC_DISPLAY_NAMES = {
    "rolling_3m_return": "Rolling 3-Month Return",
    "rolling_6m_return": "Rolling 6-Month Return",
    "rolling_12m_return": "Rolling 12-Month Return",
    "rolling_24m_return": "Rolling 24-Month Return",
    "rolling_36m_return": "Rolling 36-Month Return",
    "rolling_12m_return_ann": "Rolling 12-Month Return (Annualized)",
    "rolling_24m_return_ann": "Rolling 24-Month Return (Annualized)",
    "rolling_36m_return_ann": "Rolling 36-Month Return (Annualized)",
    "rolling_63d_vol": "Rolling 63-Day Volatility (Annualized)",
    "rolling_126d_vol": "Rolling 126-Day Volatility (Annualized)",
    "rolling_252d_vol": "Rolling 252-Day Volatility (Annualized)",
    "rolling_252d_sharpe": "Rolling 252-Day Sharpe Ratio",
}

# Sharpe is a raw ratio (not a percentage); every other rolling metric in
# this file is a return or a volatility, both expressed as decimals.
_ROLLING_METRICS_AS_PERCENT = {name for name in _ROLLING_METRIC_DISPLAY_NAMES if not name.endswith("_sharpe")}


def plot_rolling_metric(
    rolling_metrics: pd.DataFrame, metric_name: str, fund_labels: Optional[List[str]] = None
) -> go.Figure:
    """Generic rolling-metric line chart (returns, volatility, Sharpe), one line per fund."""
    if not is_dataframe_usable(rolling_metrics) or not has_required_columns(
        rolling_metrics, ["date_or_month", "fund_label", "metric_name", "metric_value"]
    ):
        return _empty_figure("Rolling metrics: data is not available yet.")

    df = rolling_metrics[rolling_metrics["metric_name"] == metric_name].copy()
    if fund_labels:
        df = df[df["fund_label"].isin(fund_labels)]
    df = df.dropna(subset=["metric_value"]).sort_values(["fund_label", "date_or_month"])
    if df.empty:
        return _empty_figure(f"No rolling data available for metric '{metric_name}'.")

    display_name = _ROLLING_METRIC_DISPLAY_NAMES.get(metric_name, metric_name.replace("_", " ").title())
    as_percent = metric_name in _ROLLING_METRICS_AS_PERCENT

    fig = go.Figure()
    for fund_label, fund_df in df.groupby("fund_label"):
        fig.add_trace(go.Scatter(x=fund_df["date_or_month"], y=fund_df["metric_value"], mode="lines", name=fund_label))

    fig.update_layout(
        title=display_name,
        xaxis_title="Date",
        yaxis_title=display_name,
        yaxis_tickformat=".1%" if as_percent else None,
        hovermode="x unified",
        legend_title="Fund",
        template=TEMPLATE,
    )
    return fig


def plot_rolling_return(
    rolling_metrics: pd.DataFrame, window: str = "12m", annualized: bool = False, fund_labels: Optional[List[str]] = None
) -> go.Figure:
    """Rolling return chart. window in {'3m','6m','12m','24m','36m'}; annualized only valid for 12m/24m/36m."""
    metric_name = f"rolling_{window}_return" + ("_ann" if annualized else "")
    return plot_rolling_metric(rolling_metrics, metric_name, fund_labels=fund_labels)


def plot_rolling_volatility(
    rolling_metrics: pd.DataFrame, window_days: int = 252, fund_labels: Optional[List[str]] = None
) -> go.Figure:
    """Rolling volatility chart. window_days in {63, 126, 252}."""
    metric_name = f"rolling_{window_days}d_vol"
    return plot_rolling_metric(rolling_metrics, metric_name, fund_labels=fund_labels)


def plot_rolling_sharpe(rolling_metrics: pd.DataFrame, fund_labels: Optional[List[str]] = None) -> go.Figure:
    """Rolling 252-day Sharpe ratio chart."""
    return plot_rolling_metric(rolling_metrics, "rolling_252d_sharpe", fund_labels=fund_labels)


# ---------------------------------------------------------------------------
# Rolling benchmark-relative metrics (rolling_benchmark_metrics.csv: date,
# fund_label, benchmark_label, rolling_252d_beta, rolling_252d_tracking_error,
# rolling_252d_information_ratio). These gracefully render an annotated
# placeholder figure when the CSV is absent or empty.
# ---------------------------------------------------------------------------

_ROLLING_BENCHMARK_METRIC_DISPLAY_NAMES = {
    "rolling_252d_beta": "Rolling 252-Day Beta",
    "rolling_252d_tracking_error": "Rolling 252-Day Tracking Error (Annualized)",
    "rolling_252d_information_ratio": "Rolling 252-Day Information Ratio",
}


def plot_rolling_benchmark_metric(
    rolling_benchmark_metrics: pd.DataFrame, column: str, fund_labels: Optional[List[str]] = None
) -> go.Figure:
    """Generic rolling benchmark-relative line chart (beta, tracking error, information ratio)."""
    required_columns = ["date", "fund_label", "benchmark_label", column]
    if not is_dataframe_usable(rolling_benchmark_metrics) or not has_required_columns(
        rolling_benchmark_metrics, required_columns
    ):
        return _empty_figure(
            f"{_ROLLING_BENCHMARK_METRIC_DISPLAY_NAMES.get(column, column)}: benchmark-relative data is not available yet."
        )

    df = rolling_benchmark_metrics.copy()
    if fund_labels:
        df = df[df["fund_label"].isin(fund_labels)]
    df = df.dropna(subset=[column]).sort_values(["fund_label", "date"])
    if df.empty:
        return _empty_figure(f"No rolling data available for '{column}'.")

    display_name = _ROLLING_BENCHMARK_METRIC_DISPLAY_NAMES.get(column, column.replace("_", " ").title())

    fig = go.Figure()
    for (fund_label, benchmark_label), group_df in df.groupby(["fund_label", "benchmark_label"]):
        fig.add_trace(
            go.Scatter(
                x=group_df["date"], y=group_df[column], mode="lines", name=f"{fund_label} vs. {benchmark_label}"
            )
        )

    fig.update_layout(
        title=display_name,
        xaxis_title="Date",
        yaxis_title=display_name,
        yaxis_tickformat=".1%" if column == "rolling_252d_tracking_error" else None,
        hovermode="x unified",
        legend_title="",
        template=TEMPLATE,
    )
    return fig


def plot_rolling_beta(rolling_benchmark_metrics: pd.DataFrame, fund_labels: Optional[List[str]] = None) -> go.Figure:
    """Rolling 252-day beta chart."""
    return plot_rolling_benchmark_metric(rolling_benchmark_metrics, "rolling_252d_beta", fund_labels=fund_labels)


def plot_rolling_tracking_error(
    rolling_benchmark_metrics: pd.DataFrame, fund_labels: Optional[List[str]] = None
) -> go.Figure:
    """Rolling 252-day tracking error chart."""
    return plot_rolling_benchmark_metric(rolling_benchmark_metrics, "rolling_252d_tracking_error", fund_labels=fund_labels)


def plot_rolling_information_ratio(
    rolling_benchmark_metrics: pd.DataFrame, fund_labels: Optional[List[str]] = None
) -> go.Figure:
    """Rolling 252-day information ratio chart."""
    return plot_rolling_benchmark_metric(
        rolling_benchmark_metrics, "rolling_252d_information_ratio", fund_labels=fund_labels
    )


def plot_upside_downside_capture_scatter(benchmark_metrics: pd.DataFrame) -> go.Figure:
    """
    Upside vs. downside capture scatter — one point per fund. The top-left
    quadrant (upside capture > 100%, downside capture < 100%) is the
    historically most favourable combination relative to the benchmark.
    """
    required_columns = ["fund_label", "upside_capture", "downside_capture"]
    if not is_dataframe_usable(benchmark_metrics) or not has_required_columns(benchmark_metrics, required_columns):
        return _empty_figure("Upside/downside capture: benchmark-relative data is not available yet.")

    df = benchmark_metrics.dropna(subset=["upside_capture", "downside_capture"])
    if df.empty:
        return _empty_figure("No upside/downside capture data available.")

    fig = px.scatter(
        df, x="downside_capture", y="upside_capture", text="fund_label", template=TEMPLATE,
    )
    fig.update_traces(
        marker={"size": 12, "color": "steelblue"},
        textposition="top center",
        hovertemplate="%{text}<br>Downside capture: %{x:.0%}<br>Upside capture: %{y:.0%}<extra></extra>",
    )
    fig.add_hline(y=1.0, line_dash="dot", line_color="gray")
    fig.add_vline(x=1.0, line_dash="dot", line_color="gray")
    fig.update_layout(
        title="Upside vs. Downside Capture (vs. primary benchmark)",
        xaxis_title="Downside capture",
        yaxis_title="Upside capture",
        xaxis_tickformat=".0%",
        yaxis_tickformat=".0%",
    )
    return fig


# ---------------------------------------------------------------------------
# Stress / attribution
# ---------------------------------------------------------------------------

def plot_scenario_loss_ranking(attribution_results: pd.DataFrame, top_n: Optional[int] = None) -> go.Figure:
    """
    Horizontal bar chart ranking every modeled scenario by total portfolio
    stress return (most severe loss first).
    """
    required_columns = ["scenario_name", "total_portfolio_stress_return"]
    if not is_dataframe_usable(attribution_results) or not has_required_columns(attribution_results, required_columns):
        return _empty_figure("Scenario loss ranking: stress/attribution data is not available yet.")

    scenario_df = attribution_results.drop_duplicates("scenario_name")[required_columns].dropna()
    if scenario_df.empty:
        return _empty_figure("No scenario-level stress results available.")

    scenario_df = scenario_df.sort_values("total_portfolio_stress_return")
    if top_n:
        scenario_df = scenario_df.head(top_n)

    colors = ["crimson" if value < 0 else "seagreen" for value in scenario_df["total_portfolio_stress_return"]]
    fig = go.Figure(
        go.Bar(
            x=scenario_df["total_portfolio_stress_return"],
            y=scenario_df["scenario_name"],
            orientation="h",
            marker_color=colors,
            hovertemplate="%{y}: %{x:.1%}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Scenario Loss Ranking — Total Portfolio Stress Return",
        xaxis_title="Total portfolio stress return",
        xaxis_tickformat=".0%",
        yaxis_title="Scenario",
        template=TEMPLATE,
    )
    return fig


def plot_stress_waterfall(attribution_results: pd.DataFrame, scenario_name: str) -> go.Figure:
    """Stress loss waterfall chart: each fund's loss contribution stacking to the total portfolio stress return."""
    required_columns = ["scenario_name", "fund_label", "fund_loss_contribution"]
    if not is_dataframe_usable(attribution_results) or not has_required_columns(attribution_results, required_columns):
        return _empty_figure("Stress waterfall: attribution data is not available yet.")

    scenario_df = attribution_results[attribution_results["scenario_name"] == scenario_name].dropna(
        subset=["fund_loss_contribution"]
    )
    if scenario_df.empty:
        return _empty_figure(f"No attribution data available for scenario '{scenario_name}'.")

    scenario_df = scenario_df.sort_values("fund_loss_contribution")
    labels = list(scenario_df["fund_label"]) + ["Total portfolio"]
    values = list(scenario_df["fund_loss_contribution"]) + [0]
    measures = ["relative"] * len(scenario_df) + ["total"]

    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=measures,
            x=labels,
            y=values,
            decreasing={"marker": {"color": "crimson"}},
            increasing={"marker": {"color": "seagreen"}},
            totals={"marker": {"color": "steelblue"}},
            texttemplate="%{y:.1%}",
            connector={"line": {"color": "lightgray"}},
        )
    )
    fig.update_layout(
        title=f"Stress Loss Waterfall — {scenario_name}",
        yaxis_title="Contribution to portfolio stress return",
        yaxis_tickformat=".1%",
        template=TEMPLATE,
        showlegend=False,
    )
    return fig


def plot_allocation_vs_stress_loss_share(attribution_results: pd.DataFrame, scenario_name: str) -> go.Figure:
    """
    Allocation weight vs. stress loss share comparison chart for one
    scenario — a fund whose stress loss share bar is taller than its
    weight bar is contributing disproportionately to the modeled loss.
    """
    required_columns = ["scenario_name", "fund_label", "fund_weight", "stress_loss_share"]
    if not is_dataframe_usable(attribution_results) or not has_required_columns(attribution_results, required_columns):
        return _empty_figure("Allocation vs. stress loss share: attribution data is not available yet.")

    scenario_df = attribution_results[attribution_results["scenario_name"] == scenario_name].dropna(
        subset=["fund_weight", "stress_loss_share"]
    )
    if scenario_df.empty:
        return _empty_figure(f"No attribution data available for scenario '{scenario_name}'.")

    scenario_df = scenario_df.sort_values("stress_loss_share", ascending=False)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(x=scenario_df["fund_label"], y=scenario_df["fund_weight"], name="Portfolio weight", marker_color="steelblue")
    )
    fig.add_trace(
        go.Bar(
            x=scenario_df["fund_label"], y=scenario_df["stress_loss_share"], name="Stress loss share", marker_color="crimson"
        )
    )
    fig.update_layout(
        title=f"Allocation Weight vs. Stress Loss Share — {scenario_name}",
        barmode="group",
        xaxis_title="Fund",
        yaxis_title="Share",
        yaxis_tickformat=".0%",
        legend_title="",
        template=TEMPLATE,
    )
    return fig
