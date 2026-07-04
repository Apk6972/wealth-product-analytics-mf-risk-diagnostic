"""
Return Engine Module.

Reference: 00_project_control/master_project_instructions.md.md §16 (Return
Engine) and 00_project_control/formula_audit.md §1.
Related: 00_project_control/data_dictionary.md §4.3-4.6 (output schemas).

Inputs (already fetched and validated by api_fetch.py / data_cleaning.py):
    02_processed_data/nav_daily_clean.csv
    02_processed_data/benchmark_daily.csv

Outputs:
    02_processed_data/returns_daily.csv
    02_processed_data/nav_monthly.csv
    02_processed_data/returns_monthly.csv
    02_processed_data/benchmark_monthly.csv

Formulas (formula_audit.md §1):
    Daily Fund Return       = NAV_t / NAV_(previous available observation) - 1
    Month-End NAV           = latest available NAV observed in that calendar month
    Monthly Fund Return     = Month-End NAV_t / Month-End NAV_(t-1) - 1
    Benchmark Daily Return  = tri_value_t / tri_value_(t-1) - 1
    Benchmark Monthly Return: same month-end / monthly-return logic, applied to tri_value

Rules enforced throughout this module:
- Returns are calculated strictly within each fund_label / benchmark_label
  group — never across label boundaries.
- Data is always sorted by label, then date, before any return calculation.
- NAV / tri_value are never forward-filled. "Previous available observation"
  means the previous row that actually exists in the input after sorting —
  calendar gaps (holidays, non-trading days, missing days) are skipped, not
  filled.
- "Month-end" means the latest observation actually present within that
  calendar month (its own trade date), not an artificial calendar boundary.

This module does not implement CAGR, volatility, Sharpe, drawdown, or any
other analytical metric (see metrics.py, Phase 5).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from data_cleaning import (  # noqa: E402 - sys.path must be configured before this import
    DataValidationError,
    load_benchmark_daily,
    load_nav_daily_clean,
    validate_benchmark_daily,
    validate_nav_daily,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = _THIS_FILE.parents[2]  # .../src -> .../04_streamlit_app -> project root
PROCESSED_DATA_DIR = PROJECT_ROOT / "02_processed_data"

RETURNS_DAILY_PATH = PROCESSED_DATA_DIR / "returns_daily.csv"
NAV_MONTHLY_PATH = PROCESSED_DATA_DIR / "nav_monthly.csv"
RETURNS_MONTHLY_PATH = PROCESSED_DATA_DIR / "returns_monthly.csv"
BENCHMARK_MONTHLY_PATH = PROCESSED_DATA_DIR / "benchmark_monthly.csv"

# ---------------------------------------------------------------------------
# Schemas (data_dictionary.md §4.3-4.6)
# ---------------------------------------------------------------------------

NAV_DAILY_INPUT_COLUMNS = ["date", "fund_label", "nav"]
BENCHMARK_DAILY_INPUT_COLUMNS = ["date", "benchmark_label", "tri_value"]

RETURNS_DAILY_COLUMNS = ["date", "fund_label", "nav", "daily_return"]
NAV_MONTHLY_COLUMNS = ["month_end_date", "fund_label", "month_end_nav"]
RETURNS_MONTHLY_COLUMNS = ["month_end_date", "fund_label", "monthly_return"]

BENCHMARK_MONTHLY_VALUE_COLUMNS = ["month_end_date", "benchmark_label", "month_end_tri_value"]
BENCHMARK_MONTHLY_COLUMNS = ["month_end_date", "benchmark_label", "month_end_tri_value", "monthly_return"]

# Not one of the four required output files (no benchmark_returns_daily.csv
# is listed in master_project_instructions.md.md §16 / data_dictionary.md
# §4). Computed here for completeness/internal reuse (e.g. by a future
# benchmarks.py tracking-error/beta calculation) but not written to disk.
BENCHMARK_DAILY_RETURN_COLUMNS = ["date", "benchmark_label", "tri_value", "daily_return"]


def _enforce_schema(df: pd.DataFrame, required_columns: List[str], label: str) -> None:
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise DataValidationError(f"{label} is missing required columns: {missing}")


# ---------------------------------------------------------------------------
# Daily fund returns
# ---------------------------------------------------------------------------

def calculate_daily_fund_returns(nav_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Daily Return = NAV_today / NAV_previous_available_observation - 1

    Calculated within each fund_label only, sorted by fund_label then date,
    with no forward-fill. The first observation of each fund has no prior
    observation and therefore an undefined (NaN) daily_return.
    """
    _enforce_schema(nav_daily, NAV_DAILY_INPUT_COLUMNS, "nav_daily")

    df = nav_daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["fund_label", "date"]).reset_index(drop=True)
    df["daily_return"] = df.groupby("fund_label")["nav"].pct_change()

    return df[RETURNS_DAILY_COLUMNS]


# ---------------------------------------------------------------------------
# Monthly fund NAV / returns
# ---------------------------------------------------------------------------

def calculate_monthly_fund_nav(nav_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Month-end NAV = latest available NAV observed in that calendar month.

    `month_end_date` is the actual trade date of that latest observation
    (never a synthetic calendar-boundary date, and never forward-filled).
    """
    _enforce_schema(nav_daily, NAV_DAILY_INPUT_COLUMNS, "nav_daily")

    df = nav_daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["fund_label", "date"])
    df["_year_month"] = df["date"].dt.to_period("M")

    monthly = df.groupby(["fund_label", "_year_month"], as_index=False).agg(
        month_end_date=("date", "max"),
        month_end_nav=("nav", "last"),
    )
    monthly = (
        monthly.sort_values(["fund_label", "month_end_date"])
        .drop(columns=["_year_month"])
        .reset_index(drop=True)
    )

    return monthly[NAV_MONTHLY_COLUMNS]


def calculate_monthly_fund_returns(nav_monthly: pd.DataFrame) -> pd.DataFrame:
    """
    Monthly Return = Month-End NAV_t / Month-End NAV_t-1 - 1

    Calculated within each fund_label only, sorted by fund_label then
    month_end_date. The first month of each fund has an undefined (NaN)
    monthly_return.
    """
    _enforce_schema(nav_monthly, NAV_MONTHLY_COLUMNS, "nav_monthly")

    df = nav_monthly.copy()
    df["month_end_date"] = pd.to_datetime(df["month_end_date"])
    df = df.sort_values(["fund_label", "month_end_date"]).reset_index(drop=True)
    df["monthly_return"] = df.groupby("fund_label")["month_end_nav"].pct_change()

    return df[RETURNS_MONTHLY_COLUMNS]


# ---------------------------------------------------------------------------
# Benchmark daily returns (computed for internal reuse; not one of the four
# required output files)
# ---------------------------------------------------------------------------

def calculate_benchmark_daily_returns(benchmark_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Benchmark Daily Return = tri_value_today / tri_value_previous_available_observation - 1

    Calculated within each benchmark_label only, sorted by benchmark_label
    then date, with no forward-fill.
    """
    _enforce_schema(benchmark_daily, BENCHMARK_DAILY_INPUT_COLUMNS, "benchmark_daily")

    df = benchmark_daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["benchmark_label", "date"]).reset_index(drop=True)
    df["daily_return"] = df.groupby("benchmark_label")["tri_value"].pct_change()

    return df[BENCHMARK_DAILY_RETURN_COLUMNS]


# ---------------------------------------------------------------------------
# Monthly benchmark values / returns
# ---------------------------------------------------------------------------

def calculate_monthly_benchmark_values(benchmark_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Benchmark month-end value = latest available tri_value observed in that
    calendar month (own trade date, never forward-filled).
    """
    _enforce_schema(benchmark_daily, BENCHMARK_DAILY_INPUT_COLUMNS, "benchmark_daily")

    df = benchmark_daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["benchmark_label", "date"])
    df["_year_month"] = df["date"].dt.to_period("M")

    monthly = df.groupby(["benchmark_label", "_year_month"], as_index=False).agg(
        month_end_date=("date", "max"),
        month_end_tri_value=("tri_value", "last"),
    )
    monthly = (
        monthly.sort_values(["benchmark_label", "month_end_date"])
        .drop(columns=["_year_month"])
        .reset_index(drop=True)
    )

    return monthly[BENCHMARK_MONTHLY_VALUE_COLUMNS]


def calculate_benchmark_monthly_returns(benchmark_monthly: pd.DataFrame) -> pd.DataFrame:
    """
    Benchmark Monthly Return = Month-End tri_value_t / Month-End tri_value_t-1 - 1

    Same month-end / monthly-return logic as fund NAVs (§1.2-1.3), applied
    to benchmark tri_value. `benchmark_monthly` is expected to already carry
    month_end_date / month_end_tri_value (see calculate_monthly_benchmark_values).
    """
    _enforce_schema(benchmark_monthly, BENCHMARK_MONTHLY_VALUE_COLUMNS, "benchmark_monthly")

    df = benchmark_monthly.copy()
    df["month_end_date"] = pd.to_datetime(df["month_end_date"])
    df = df.sort_values(["benchmark_label", "month_end_date"]).reset_index(drop=True)
    df["monthly_return"] = df.groupby("benchmark_label")["month_end_tri_value"].pct_change()

    return df[BENCHMARK_MONTHLY_COLUMNS]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _format_date_columns_for_csv(df: pd.DataFrame, date_columns: List[str]) -> pd.DataFrame:
    formatted = df.copy()
    for column in date_columns:
        formatted[column] = pd.to_datetime(formatted[column]).dt.strftime("%Y-%m-%d")
    return formatted


def run_return_engine() -> Dict[str, pd.DataFrame]:
    """
    Full Phase 4 entry point: load and validate the two processed inputs
    (via data_cleaning.py — schema, dedup, 2021-01-01 horizon, sorting),
    compute all required return series, and write the four output files.

    Intended to be called explicitly (e.g. from refresh_data.py) — never on
    import, never inside a Streamlit page.
    """
    nav_daily = validate_nav_daily(load_nav_daily_clean())
    benchmark_daily = validate_benchmark_daily(load_benchmark_daily())

    returns_daily = calculate_daily_fund_returns(nav_daily)
    nav_monthly = calculate_monthly_fund_nav(nav_daily)
    returns_monthly = calculate_monthly_fund_returns(nav_monthly)

    benchmark_daily_returns = calculate_benchmark_daily_returns(benchmark_daily)
    benchmark_monthly_values = calculate_monthly_benchmark_values(benchmark_daily)
    benchmark_monthly = calculate_benchmark_monthly_returns(benchmark_monthly_values)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    _format_date_columns_for_csv(returns_daily, ["date"]).to_csv(RETURNS_DAILY_PATH, index=False)
    _format_date_columns_for_csv(nav_monthly, ["month_end_date"]).to_csv(NAV_MONTHLY_PATH, index=False)
    _format_date_columns_for_csv(returns_monthly, ["month_end_date"]).to_csv(RETURNS_MONTHLY_PATH, index=False)
    _format_date_columns_for_csv(benchmark_monthly, ["month_end_date"]).to_csv(BENCHMARK_MONTHLY_PATH, index=False)

    return {
        "returns_daily": returns_daily,
        "nav_monthly": nav_monthly,
        "returns_monthly": returns_monthly,
        "benchmark_daily_returns": benchmark_daily_returns,
        "benchmark_monthly": benchmark_monthly,
    }
