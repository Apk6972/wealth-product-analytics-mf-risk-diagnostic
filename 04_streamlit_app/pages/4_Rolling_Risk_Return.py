"""
Page: Rolling Risk & Return.

Reads only from 02_processed_data/ (via data_loader.py) — never fetches
live data. Reference: 00_project_control/master_project_instructions.md.md
§23.4.
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import charts  # noqa: E402
import data_loader as dl  # noqa: E402
import disclosures  # noqa: E402
from utils import is_dataframe_usable  # noqa: E402

REFRESH_COMMAND = "python 04_streamlit_app/refresh_data.py"
TEMPLATE = "plotly_white"

ROLLING_RETURN_METRICS = {
    "rolling_3m_return": "3-Month",
    "rolling_6m_return": "6-Month",
    "rolling_12m_return": "12-Month",
    "rolling_24m_return": "24-Month",
    "rolling_36m_return": "36-Month",
}
ROLLING_VOL_METRICS = {
    "rolling_63d_vol": "63-Day",
    "rolling_126d_vol": "126-Day",
    "rolling_252d_vol": "252-Day",
}


def _multi_metric_line_chart(
    rolling_metrics, metric_display_names: dict, fund_label: str, title: str, y_title: str
) -> go.Figure:
    """Page-local chart: one line per metric_name (e.g. each rolling window), all for a
    single selected fund, on one shared chart — distinct from charts.plot_rolling_metric()
    which draws one line per *fund* for a single metric_name."""
    df = rolling_metrics[
        (rolling_metrics["fund_label"] == fund_label) & (rolling_metrics["metric_name"].isin(metric_display_names))
    ]
    fig = go.Figure()
    plotted_any = False
    for metric_name, display_name in metric_display_names.items():
        series = df[df["metric_name"] == metric_name].dropna(subset=["metric_value"]).sort_values("date_or_month")
        if series.empty:
            continue
        plotted_any = True
        fig.add_trace(
            go.Scatter(
                x=series["date_or_month"],
                y=series["metric_value"],
                mode="lines",
                name=display_name,
                hovertemplate="%{x|%d %b %Y}<br>" + display_name + ": %{y:.1%}<extra></extra>",
            )
        )

    if not plotted_any:
        fig.add_annotation(
            text=f"{title}: no rolling data available for '{fund_label}'.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font={"size": 14, "color": "gray"},
        )
        fig.update_layout(xaxis={"visible": False}, yaxis={"visible": False}, template=TEMPLATE, height=350)
        return fig

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title=y_title,
        yaxis_tickformat=".1%",
        hovermode="x unified",
        legend_title="Window",
        template=TEMPLATE,
    )
    return fig


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("Rolling Risk & Return")
st.caption("How a fund's return and risk profile has evolved through different market regimes.")

disclosures.render_data_quality_banner()

rolling_metrics = dl.load_rolling_metrics()
metrics_summary = dl.load_metrics_summary()
rolling_benchmark_metrics = dl.load_rolling_benchmark_metrics()

missing_files = []
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
    selected_fund = st.selectbox("Fund", options=fund_labels, key="rolling_risk_return_fund_select")

    st.divider()
    st.caption("This app reads only from `02_processed_data/`. To refresh data, run:")
    st.code(REFRESH_COMMAND, language="bash")

st.subheader(selected_fund)

# ---------------------------------------------------------------------------
# Rolling returns (3M / 6M / 12M / 24M / 36M)
# ---------------------------------------------------------------------------

st.markdown("#### Rolling Returns (3M / 6M / 12M / 24M / 36M)")
st.plotly_chart(
    _multi_metric_line_chart(
        rolling_metrics, ROLLING_RETURN_METRICS, selected_fund, "Rolling Returns by Window", "Rolling return"
    ),
    width="stretch",
)

# ---------------------------------------------------------------------------
# Rolling volatility (63D / 126D / 252D)
# ---------------------------------------------------------------------------

st.markdown("#### Rolling Volatility (63D / 126D / 252D, Annualized)")
st.plotly_chart(
    _multi_metric_line_chart(
        rolling_metrics, ROLLING_VOL_METRICS, selected_fund, "Rolling Volatility by Window", "Annualized volatility"
    ),
    width="stretch",
)

# ---------------------------------------------------------------------------
# Rolling 252D Sharpe
# ---------------------------------------------------------------------------

st.markdown("#### Rolling 252-Day Sharpe Ratio")
st.plotly_chart(charts.plot_rolling_sharpe(rolling_metrics, fund_labels=[selected_fund]), width="stretch")

# ---------------------------------------------------------------------------
# Rolling beta / information ratio, if available
# ---------------------------------------------------------------------------

st.markdown("#### Rolling Beta")
if is_dataframe_usable(rolling_benchmark_metrics):
    st.plotly_chart(charts.plot_rolling_beta(rolling_benchmark_metrics, fund_labels=[selected_fund]), width="stretch")
else:
    st.info(
        "Rolling beta is not available yet — `02_processed_data/rolling_benchmark_metrics.csv` has not been "
        f"generated. Run `{REFRESH_COMMAND}` (benchmark analytics step) to produce it."
    )

st.markdown("#### Rolling Information Ratio")
if is_dataframe_usable(rolling_benchmark_metrics):
    st.plotly_chart(
        charts.plot_rolling_information_ratio(rolling_benchmark_metrics, fund_labels=[selected_fund]),
        width="stretch",
    )
else:
    st.info(
        "Rolling information ratio is not available yet — `02_processed_data/rolling_benchmark_metrics.csv` has "
        f"not been generated. Run `{REFRESH_COMMAND}` (benchmark analytics step) to produce it."
    )

st.divider()

# ---------------------------------------------------------------------------
# Interpretation box
# ---------------------------------------------------------------------------

st.markdown("#### Interpretation: Reading Regime Behaviour")
st.info(
    "A single trailing CAGR or Sharpe hides *when* a fund earned its return. These rolling views unpack that "
    "history into overlapping windows so regime shifts become visible:\n\n"
    "- **Rolling returns fanning apart** (short windows swinging far from long windows) signal a fund whose "
    "recent performance is diverging sharply from its longer-term trend — worth checking *why* before "
    "extrapolating either one forward.\n"
    "- **Rolling volatility stepping up** while rolling returns compress or turn negative is the classic "
    "signature of a regime shift into a higher-risk, lower-payoff environment (e.g. a market drawdown or a "
    "liquidity shock), not just noisy day-to-day returns.\n"
    "- **Rolling Sharpe crossing zero or trending down** shows periods where the fund's risk was not being "
    "compensated by return, even if the trailing full-period Sharpe still looks acceptable.\n"
    "- **Rolling beta drifting away from its long-run level** suggests the fund's sensitivity to its benchmark "
    "is not constant — it may be taking on more (or less) market risk than its stated mandate implies during "
    "certain regimes.\n"
    "- **Rolling information ratio turning negative for extended stretches** indicates the fund was not "
    "reliably rewarded for deviating from its benchmark during that regime.\n\n"
    "All of the above describe **trailing historical data only** — they are not forecasts of how the fund will "
    "behave in the next regime."
)
st.caption("Educational analytics project. Not investment advice.")
