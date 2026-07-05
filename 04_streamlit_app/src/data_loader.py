"""
Data Loader Module — read-only access to processed CSVs for the Streamlit app.

The Streamlit app must never fetch live data on page load; it only reads
from 02_processed_data/ via the functions in this module.
Reference: 00_project_control/master_project_instructions.md.md §3
(Non-Negotiable Runtime Rule) and §9 (Folder Structure).

Every loader in this module is "safe": if the expected processed CSV does
not exist yet (e.g. a later pipeline stage such as benchmarks.py hasn't
been run), it emits a UserWarning and returns an empty DataFrame with the
expected column names, rather than raising. This lets Streamlit pages
render a "data not available yet" state instead of crashing. Callers
should check `utils.is_dataframe_usable(df)` before using the result.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from returns import PROCESSED_DATA_DIR  # noqa: E402 - sys.path must be configured before this import

# ---------------------------------------------------------------------------
# Expected schemas — used to build a correctly-shaped empty DataFrame when a
# processed file does not exist yet, so downstream `df["col"]` access does
# not raise a KeyError even before every pipeline stage has been run.
# ---------------------------------------------------------------------------

_EXPECTED_COLUMNS: Dict[str, List[str]] = {
    "nav_daily_clean.csv": ["date", "fund_label", "scheme_code", "scheme_name", "nav", "source", "source_quality"],
    "nav_monthly.csv": ["month_end_date", "fund_label", "month_end_nav"],
    "returns_daily.csv": ["date", "fund_label", "nav", "daily_return"],
    "returns_monthly.csv": ["month_end_date", "fund_label", "monthly_return"],
    "benchmark_daily.csv": ["date", "benchmark_label", "tri_value", "source", "source_quality"],
    "benchmark_monthly.csv": ["month_end_date", "benchmark_label", "month_end_tri_value", "monthly_return"],
    "metrics_summary.csv": [
        "fund_label", "data_start_date", "data_end_date", "observation_count_daily", "observation_count_monthly",
        "cagr", "annualized_volatility", "downside_deviation", "sharpe_ratio", "sortino_ratio", "max_drawdown",
        "recovery_period_days", "best_month", "worst_month", "positive_month_ratio", "daily_var_95",
        "daily_cvar_95", "monthly_var_95", "monthly_cvar_95", "risk_free_rate_used", "as_of_date",
    ],
    "rolling_metrics.csv": ["date_or_month", "fund_label", "metric_name", "metric_value", "frequency"],
    "benchmark_metrics.csv": [
        "fund_label", "benchmark_label", "excess_return_ann", "beta", "tracking_error",
        "information_ratio", "upside_capture", "downside_capture",
    ],
    "rolling_benchmark_metrics.csv": [
        "date", "fund_label", "benchmark_label", "rolling_252d_beta",
        "rolling_252d_tracking_error", "rolling_252d_information_ratio",
    ],
    "stress_results.csv": [
        "scenario_type", "scenario_name", "fund_label", "stress_return", "window_start", "window_end", "rationale",
    ],
    "attribution_results.csv": [
        "scenario_name", "fund_label", "fund_weight", "fund_stress_return", "fund_loss_contribution",
        "stress_loss_share", "base_portfolio_value", "loss_amount_inr", "total_portfolio_stress_return",
        "post_stress_portfolio_value", "is_largest_loss_contributor", "stress_loss_share_minus_weight",
    ],
    "suitability_results.csv": [
        "fund_label", "client_profile", "suitability_role", "risk_warning", "recommended_action", "rationale",
        "overall_risk_tier", "annualized_volatility", "max_drawdown", "daily_cvar_95", "recovery_period_days",
        "small_cap_exposure_flag", "rolling_beta", "downside_capture", "avg_stress_loss_share_minus_weight",
        "benchmark_relative_data_available",
    ],
    "data_quality_report.csv": [
        "fund_label_or_benchmark_label", "asset_type", "source", "source_quality", "first_date", "last_date",
        "observation_count", "missing_value_count", "duplicate_date_count", "suspicious_return_count_gt_10pct",
        "suspicious_return_count_lt_minus_10pct", "metadata_verification_status", "status",
    ],
}


def _safe_load_csv(filename: str, parse_dates: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Read `02_processed_data/{filename}` if it exists; otherwise warn and
    return an empty DataFrame shaped with the expected columns. Never
    raises on a missing/unreadable/empty file - this module is read-only
    and purely defensive by design (it must never fetch live data, and it
    must never crash a Streamlit page render because a later pipeline
    stage hasn't been run yet).
    """
    path = PROCESSED_DATA_DIR / filename
    expected_columns = _EXPECTED_COLUMNS.get(filename, [])

    if not path.exists():
        warnings.warn(
            f"{path} does not exist. Returning an empty DataFrame — run refresh_data.py to "
            "generate processed outputs before relying on this data in the app.",
            UserWarning,
            stacklevel=3,
        )
        return pd.DataFrame(columns=expected_columns)

    try:
        df = pd.read_csv(path, parse_dates=parse_dates)
    except Exception as exc:  # noqa: BLE001 - any read failure should degrade to empty, not crash the app
        warnings.warn(
            f"Failed to read {path}: {type(exc).__name__}: {exc}. Returning an empty DataFrame.",
            UserWarning,
            stacklevel=3,
        )
        return pd.DataFrame(columns=expected_columns)

    if df.empty:
        warnings.warn(f"{path} exists but contains no rows.", UserWarning, stacklevel=3)

    return df


# ---------------------------------------------------------------------------
# NAV / returns
# ---------------------------------------------------------------------------

def load_nav_daily() -> pd.DataFrame:
    """Load 02_processed_data/nav_daily_clean.csv."""
    return _safe_load_csv("nav_daily_clean.csv", parse_dates=["date"])


def load_nav_monthly() -> pd.DataFrame:
    """Load 02_processed_data/nav_monthly.csv."""
    return _safe_load_csv("nav_monthly.csv", parse_dates=["month_end_date"])


def load_returns_daily() -> pd.DataFrame:
    """Load 02_processed_data/returns_daily.csv."""
    return _safe_load_csv("returns_daily.csv", parse_dates=["date"])


def load_returns_monthly() -> pd.DataFrame:
    """Load 02_processed_data/returns_monthly.csv."""
    return _safe_load_csv("returns_monthly.csv", parse_dates=["month_end_date"])


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

def load_benchmark_daily() -> pd.DataFrame:
    """Load 02_processed_data/benchmark_daily.csv."""
    return _safe_load_csv("benchmark_daily.csv", parse_dates=["date"])


def load_benchmark_monthly() -> pd.DataFrame:
    """Load 02_processed_data/benchmark_monthly.csv."""
    return _safe_load_csv("benchmark_monthly.csv", parse_dates=["month_end_date"])


def load_benchmark_metrics() -> pd.DataFrame:
    """
    Load 02_processed_data/benchmark_metrics.csv (fund-level beta, tracking
    error, information ratio, upside/downside capture). Returns an empty
    correctly-shaped DataFrame with a warning if the file is absent or empty
    (e.g. benchmarks pipeline step has not been run yet).
    """
    return _safe_load_csv("benchmark_metrics.csv")


def load_rolling_benchmark_metrics() -> pd.DataFrame:
    """
    Load 02_processed_data/rolling_benchmark_metrics.csv (rolling 252-day
    beta, tracking error, information ratio). Returns an empty DataFrame
    with a warning if the file is absent or empty.
    """
    return _safe_load_csv("rolling_benchmark_metrics.csv", parse_dates=["date"])


# ---------------------------------------------------------------------------
# Metrics / rolling metrics
# ---------------------------------------------------------------------------

def load_metrics_summary() -> pd.DataFrame:
    """Load 02_processed_data/metrics_summary.csv."""
    return _safe_load_csv("metrics_summary.csv", parse_dates=["data_start_date", "data_end_date", "as_of_date"])


def load_rolling_metrics() -> pd.DataFrame:
    """
    Load 02_processed_data/rolling_metrics.csv (long-form:
    date_or_month, fund_label, metric_name, metric_value, frequency).
    """
    df = _safe_load_csv("rolling_metrics.csv")
    if not df.empty and "date_or_month" in df.columns:
        df["date_or_month"] = pd.to_datetime(df["date_or_month"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Stress / attribution / suitability
# ---------------------------------------------------------------------------

def load_stress_results() -> pd.DataFrame:
    """Load 02_processed_data/stress_results.csv."""
    return _safe_load_csv("stress_results.csv", parse_dates=["window_start", "window_end"])


def load_attribution_results() -> pd.DataFrame:
    """Load 02_processed_data/attribution_results.csv."""
    return _safe_load_csv("attribution_results.csv")


def load_suitability_results() -> pd.DataFrame:
    """Load 02_processed_data/suitability_results.csv."""
    return _safe_load_csv("suitability_results.csv")


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------

def load_data_quality_report() -> pd.DataFrame:
    """Load 02_processed_data/data_quality_report.csv."""
    return _safe_load_csv("data_quality_report.csv", parse_dates=["first_date", "last_date"])


# ---------------------------------------------------------------------------
# Convenience bulk loader
# ---------------------------------------------------------------------------

def load_all_processed_data() -> Dict[str, pd.DataFrame]:
    """
    Load every processed dataset in one call, keyed by a short name. Handy
    for a Streamlit page (or the Methodology page's data-availability
    checklist) that needs to check several datasets at once without
    importing every individual loader function.
    """
    return {
        "nav_daily": load_nav_daily(),
        "nav_monthly": load_nav_monthly(),
        "returns_daily": load_returns_daily(),
        "returns_monthly": load_returns_monthly(),
        "benchmark_daily": load_benchmark_daily(),
        "benchmark_monthly": load_benchmark_monthly(),
        "benchmark_metrics": load_benchmark_metrics(),
        "rolling_benchmark_metrics": load_rolling_benchmark_metrics(),
        "metrics_summary": load_metrics_summary(),
        "rolling_metrics": load_rolling_metrics(),
        "stress_results": load_stress_results(),
        "attribution_results": load_attribution_results(),
        "suitability_results": load_suitability_results(),
        "data_quality_report": load_data_quality_report(),
    }
