"""
Formatting Module — shared display-formatting helpers under one import
path, plus the metric-tooltip glossary used across every Streamlit page.

The core numeric formatting logic (Indian-digit-grouped INR, compact
Lakh/Crore currency, percent formatting) already lives in utils.py and is
used throughout metrics.py, charts.py, and the existing Streamlit pages;
this module does not duplicate that logic. It re-exports those helpers
under formatting.py — alongside date/day formatters and the new
benchmark-label and metric-tooltip helpers — so every page can standardize
on one import path for "how a number is shown to the user", without
changing any existing utils.py call site or any calculation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from utils import (  # noqa: E402,F401 - re-exported
    format_inr,
    format_inr_compact,
    format_percent,
)

from config import get_benchmark_display_label  # noqa: E402


def format_benchmark_label(benchmark_label: str) -> str:
    """
    Disclosure-aware display label for a benchmark_label code, e.g.
    'HYBRID_65_35' -> 'Hybrid 65:35 synthetic benchmark'.

    Thin alias over config.get_benchmark_display_label() — grouped here
    because, from a caller's perspective, choosing how to display a
    benchmark code is a formatting concern.
    """
    return get_benchmark_display_label(benchmark_label)


# ---------------------------------------------------------------------------
# Date / day-count formatting — standardizes the "dd Mon yyyy" and "N days"
# conventions that were previously written ad hoc (df["date"].strftime(...),
# f"{value:.0f} days") on individual pages.
# ---------------------------------------------------------------------------

def format_date(value, fmt: str = "%d %b %Y") -> str:
    """
    Format a date-like value (pandas Timestamp, datetime.date, ISO string,
    None, or NaT) as 'dd Mon yyyy' by default.

    Returns 'N/A' for None/NaT/unparseable inputs rather than raising —
    processed CSVs read via data_loader.py may contain missing dates for
    funds/episodes still in progress (e.g. an ongoing drawdown with no
    recovery_date yet).
    """
    if value is None:
        return "N/A"
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return "N/A"
    if pd.isna(timestamp):
        return "N/A"
    return timestamp.strftime(fmt)


def format_days(value: Optional[float], not_available_text: str = "N/A") -> str:
    """
    Format a day-count value as '<n> days', matching the convention already
    used across the Streamlit pages (e.g. recovery_period_days).

    Returns `not_available_text` for None/NaN inputs (e.g. a fund that has
    never fully recovered from a drawdown within the observed window) —
    never fabricates a 0 or an estimate.
    """
    if value is None or pd.isna(value):
        return not_available_text
    return f"{int(round(float(value)))} days"


# ---------------------------------------------------------------------------
# Metric tooltip glossary — one-line, plain-English explanations shown via
# st.metric(..., help=...) or st.caption(...) next to a metric, so a
# recruiter/reviewer unfamiliar with the formula still knows what the
# number means and (for VaR/CVaR/tracking error/etc.) its exact frequency.
# Full formula definitions with the underlying math live in
# 00_project_control/formula_audit.md and the Methodology page; these are
# intentionally short companions to that reference, not a replacement.
# ---------------------------------------------------------------------------

METRIC_HELP = {
    "cagr": (
        "Compound Annual Growth Rate — the constant annual growth rate that would take the starting NAV to "
        "the ending NAV over the observed period."
    ),
    "volatility": (
        "Annualized standard deviation of daily returns — how much returns swing around their average. "
        "Higher = more variable return path."
    ),
    "sharpe": (
        "Annualized excess return over the risk-free rate, per unit of total volatility. Higher is better; "
        "penalizes upside and downside swings equally."
    ),
    "sortino": (
        "Like Sharpe, but only penalizes downside volatility (returns below the risk-free rate) — rewards a "
        "fund whose volatility comes mostly from gains, not losses."
    ),
    "max_drawdown": (
        "The largest peak-to-trough decline in NAV over the period — the worst-case loss an investor entering "
        "at the peak would have experienced before any recovery."
    ),
    "recovery_period": (
        "Trading days from a peak, through the trough, to the NAV first making a new all-time high again. "
        "'Not yet recovered' means the fund is still below a prior peak as of the latest data."
    ),
    "daily_var_95": (
        "Daily Value at Risk (95%) — on 95% of trading days, the daily loss is expected to be no worse than "
        "this figure. Frequency: DAILY. Does not describe the worst 5% of days."
    ),
    "daily_cvar_95": (
        "Daily Conditional VaR (95%) — the average daily loss on the worst 5% of trading days (beyond the VaR "
        "threshold). Frequency: DAILY."
    ),
    "monthly_var_95": (
        "Monthly Value at Risk (95%) — on 95% of months, the monthly loss is expected to be no worse than "
        "this figure. Frequency: MONTHLY."
    ),
    "monthly_cvar_95": (
        "Monthly Conditional VaR (95%) — the average monthly loss in the worst 5% of months. "
        "Frequency: MONTHLY."
    ),
    "tracking_error": (
        "Annualized standard deviation of (fund return − benchmark return) — how much the fund's return path "
        "deviates from its own primary benchmark, regardless of direction."
    ),
    "information_ratio": (
        "Annualized excess return over the benchmark, divided by tracking error — how consistently the fund "
        "has been rewarded for deviating from its benchmark."
    ),
    "upside_capture": (
        "The fund's average return in benchmark-up periods, as a % of the benchmark's average return in those "
        "same periods. Above 100% = the fund gained more than the benchmark when the benchmark rose."
    ),
    "downside_capture": (
        "The fund's average return in benchmark-down periods, as a % of the benchmark's average return in "
        "those same periods. Below 100% = the fund lost less than the benchmark when the benchmark fell."
    ),
    "beta": (
        "Sensitivity of the fund's daily return to its primary benchmark's daily return. Beta > 1 = "
        "historically more volatile than the benchmark; beta < 1 = historically less volatile."
    ),
    "excess_return": (
        "Annualized (fund return − benchmark return) — positive means the fund has outrun its own primary "
        "benchmark over the period, before considering the risk taken to get there."
    ),
}


def metric_help(key: str) -> Optional[str]:
    """
    Return the one-line tooltip for a metric key (see METRIC_HELP), or None
    if the key is not in the glossary — callers can pass the result
    directly as `help=formatting.metric_help("cagr")` to st.metric().
    """
    return METRIC_HELP.get(key)
