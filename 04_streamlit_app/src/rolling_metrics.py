"""
Rolling Metrics Module — rolling returns, volatility, Sharpe.

Reference: 00_project_control/master_project_instructions.md.md §18 (Rolling
Metrics Module) and 00_project_control/formula_audit.md §4.

Inputs (already computed by returns.py, Phase 4):
    02_processed_data/returns_daily.csv
    02_processed_data/returns_monthly.csv

Output (long-form, as requested — one row per fund/date/metric):
    02_processed_data/rolling_metrics.csv
    Columns: date_or_month, fund_label, metric_name, metric_value, frequency

Metrics produced (metric_name values):
    Monthly (frequency="monthly", indexed by month_end_date):
        rolling_3m_return, rolling_6m_return, rolling_12m_return,
        rolling_24m_return, rolling_36m_return
        rolling_12m_return_ann, rolling_24m_return_ann, rolling_36m_return_ann
    Daily (frequency="daily", indexed by date):
        rolling_63d_vol, rolling_126d_vol, rolling_252d_vol
        rolling_252d_return_ann (intermediate figure named in the Sharpe
            formula itself — exposed as its own row for full auditability)
        rolling_252d_sharpe

Rules enforced throughout:
- All rolling windows are calculated strictly within each fund_label —
  never across fund boundaries (each fund's series is rolled independently).
- Data is always sorted by fund_label, then date/month_end_date, before any
  rolling calculation.
- min_periods equals the full window size for every rolling calculation, so
  early-window observations (insufficient trailing history) are NaN, never
  a partial-window estimate.
- Rolling metrics are never forward-filled.

This module does not implement benchmark-relative analytics, stress
testing, attribution, or Streamlit UI (later phases).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import pandas as pd

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from data_cleaning import DataValidationError  # noqa: E402 - sys.path must be configured before this import
from returns import (  # noqa: E402 - sys.path must be configured before this import
    PROCESSED_DATA_DIR,
    RETURNS_DAILY_COLUMNS,
    RETURNS_DAILY_PATH,
    RETURNS_MONTHLY_COLUMNS,
    RETURNS_MONTHLY_PATH,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROLLING_METRICS_PATH = PROCESSED_DATA_DIR / "rolling_metrics.csv"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROLLING_RETURN_WINDOWS_MONTHS = [3, 6, 12, 24, 36]
ROLLING_RETURN_ANN_WINDOWS_MONTHS = [12, 24, 36]
ROLLING_VOL_WINDOWS_DAYS = [63, 126, 252]
ROLLING_SHARPE_WINDOW_DAYS = 252

TRADING_DAYS_PER_YEAR = 252
MONTHS_PER_YEAR = 12
DEFAULT_RISK_FREE_RATE = 0.06

RETURNS_DAILY_INPUT_COLUMNS = RETURNS_DAILY_COLUMNS
RETURNS_MONTHLY_INPUT_COLUMNS = RETURNS_MONTHLY_COLUMNS

# Long-form output schema, as requested.
ROLLING_METRICS_COLUMNS = ["date_or_month", "fund_label", "metric_name", "metric_value", "frequency"]

FREQUENCY_MONTHLY = "monthly"
FREQUENCY_DAILY = "daily"


def _enforce_schema(df: pd.DataFrame, required_columns: List[str], label: str) -> None:
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise DataValidationError(f"{label} is missing required columns: {missing}")


# ---------------------------------------------------------------------------
# Monthly rolling returns
# ---------------------------------------------------------------------------

def calculate_rolling_returns(returns_monthly: pd.DataFrame) -> pd.DataFrame:
    """
    rolling_{N}m_return = PRODUCT(1 + monthly_return over trailing N months) - 1
    for N in ROLLING_RETURN_WINDOWS_MONTHS.

    Calculated within each fund_label only, sorted by month_end_date.
    min_periods = N, so early-window months (fewer than N months of prior
    history) are NaN.

    Returns a wide DataFrame: month_end_date, fund_label, rolling_3m_return,
    rolling_6m_return, rolling_12m_return, rolling_24m_return, rolling_36m_return.
    """
    _enforce_schema(returns_monthly, RETURNS_MONTHLY_INPUT_COLUMNS, "returns_monthly")

    df = returns_monthly.copy()
    df["month_end_date"] = pd.to_datetime(df["month_end_date"])
    df = df.sort_values(["fund_label", "month_end_date"]).reset_index(drop=True)

    output_columns = [f"rolling_{window}m_return" for window in ROLLING_RETURN_WINDOWS_MONTHS]
    frames = []
    for fund_label, group in df.groupby("fund_label", sort=False):
        group = group.sort_values("month_end_date").reset_index(drop=True)
        growth = 1.0 + group["monthly_return"]
        result = group[["month_end_date", "fund_label"]].copy()
        for window in ROLLING_RETURN_WINDOWS_MONTHS:
            rolling_product = growth.rolling(window=window, min_periods=window).apply(
                lambda values: values.prod(), raw=True
            )
            result[f"rolling_{window}m_return"] = rolling_product - 1.0
        frames.append(result)

    if not frames:
        return pd.DataFrame(columns=["month_end_date", "fund_label"] + output_columns)
    return pd.concat(frames, ignore_index=True)


def calculate_rolling_returns_annualized(returns_monthly: pd.DataFrame) -> pd.DataFrame:
    """
    rolling_{N}m_return_ann = PRODUCT(1 + monthly_return over trailing N months) ^ (12/N) - 1
    for N in ROLLING_RETURN_ANN_WINDOWS_MONTHS.

    Derived algebraically from calculate_rolling_returns()'s rolling_{N}m_return
    (PRODUCT(...) = 1 + rolling_{N}m_return), so the same fund-isolated,
    NaN-preserving rolling product is never computed twice.
    """
    rolling_returns = calculate_rolling_returns(returns_monthly)

    result = rolling_returns[["month_end_date", "fund_label"]].copy()
    for window in ROLLING_RETURN_ANN_WINDOWS_MONTHS:
        source_column = f"rolling_{window}m_return"
        ann_column = f"rolling_{window}m_return_ann"
        result[ann_column] = (1.0 + rolling_returns[source_column]) ** (MONTHS_PER_YEAR / window) - 1.0

    return result


# ---------------------------------------------------------------------------
# Daily rolling risk
# ---------------------------------------------------------------------------

def calculate_rolling_volatility(returns_daily: pd.DataFrame) -> pd.DataFrame:
    """
    rolling_{W}d_vol = STDEV(daily_return over trailing W days) x SQRT(252)
    for W in ROLLING_VOL_WINDOWS_DAYS.

    Calculated within each fund_label only, sorted by date. min_periods = W,
    so early-window days (fewer than W days of prior history) are NaN.

    Returns a wide DataFrame: date, fund_label, rolling_63d_vol,
    rolling_126d_vol, rolling_252d_vol.
    """
    _enforce_schema(returns_daily, RETURNS_DAILY_INPUT_COLUMNS, "returns_daily")

    df = returns_daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["fund_label", "date"]).reset_index(drop=True)

    output_columns = [f"rolling_{window}d_vol" for window in ROLLING_VOL_WINDOWS_DAYS]
    frames = []
    for fund_label, group in df.groupby("fund_label", sort=False):
        group = group.sort_values("date").reset_index(drop=True)
        result = group[["date", "fund_label"]].copy()
        for window in ROLLING_VOL_WINDOWS_DAYS:
            rolling_std = group["daily_return"].rolling(window=window, min_periods=window).std(ddof=1)
            result[f"rolling_{window}d_vol"] = rolling_std * (TRADING_DAYS_PER_YEAR ** 0.5)
        frames.append(result)

    if not frames:
        return pd.DataFrame(columns=["date", "fund_label"] + output_columns)
    return pd.concat(frames, ignore_index=True)


def _calculate_rolling_daily_return_ann(
    returns_daily: pd.DataFrame, window_days: int = ROLLING_SHARPE_WINDOW_DAYS
) -> pd.DataFrame:
    """
    rolling_{window_days}d_return_ann = PRODUCT(1 + daily_return over trailing
    window_days) - 1.

    window_days=252 approximates one trading year, so this trailing
    compounded daily return is itself already an annualized figure (unlike
    the monthly rolling-return annualization, no further exponent scaling
    is applied). This is the "rolling_252d_return_ann" referenced directly
    in the rolling Sharpe formula (master_project_instructions.md.md §18) -
    exposed as its own metric row for full auditability of how
    rolling_252d_sharpe was derived.

    Calculated within each fund_label only, sorted by date, with
    min_periods = window_days (early-window days are NaN).
    """
    df = returns_daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["fund_label", "date"]).reset_index(drop=True)

    column = f"rolling_{window_days}d_return_ann"
    frames = []
    for fund_label, group in df.groupby("fund_label", sort=False):
        group = group.sort_values("date").reset_index(drop=True)
        growth = 1.0 + group["daily_return"]
        result = group[["date", "fund_label"]].copy()
        rolling_product = growth.rolling(window=window_days, min_periods=window_days).apply(
            lambda values: values.prod(), raw=True
        )
        result[column] = rolling_product - 1.0
        frames.append(result)

    if not frames:
        return pd.DataFrame(columns=["date", "fund_label", column])
    return pd.concat(frames, ignore_index=True)


def calculate_rolling_sharpe(
    rolling_return_ann: pd.Series,
    rolling_vol: pd.Series,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> pd.Series:
    """
    rolling_252d_sharpe = (rolling_252d_return_ann - risk_free_rate) / rolling_252d_vol

    `rolling_return_ann` and `rolling_vol` must already be aligned
    (same index / same fund+date ordering). A zero rolling_vol (or NaN, e.g.
    an early-window period) safely yields NaN rather than +/-inf or a crash.
    """
    safe_vol = rolling_vol.mask(rolling_vol == 0)
    return (rolling_return_ann - risk_free_rate) / safe_vol


# ---------------------------------------------------------------------------
# Long-form assembly
# ---------------------------------------------------------------------------

def _wide_to_long(
    wide_df: pd.DataFrame,
    date_column: str,
    value_columns: List[str],
    frequency: str,
) -> pd.DataFrame:
    """Melt a wide [date_column, fund_label, metric...] frame into the
    long-form [date_or_month, fund_label, metric_name, metric_value, frequency] schema."""
    melted = wide_df.melt(
        id_vars=[date_column, "fund_label"],
        value_vars=value_columns,
        var_name="metric_name",
        value_name="metric_value",
    )
    melted = melted.rename(columns={date_column: "date_or_month"})
    melted["frequency"] = frequency
    return melted[ROLLING_METRICS_COLUMNS]


def generate_rolling_metrics(
    returns_daily: pd.DataFrame,
    returns_monthly: pd.DataFrame,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> pd.DataFrame:
    """
    Assemble the full long-form rolling_metrics.csv content per
    master_project_instructions.md.md §18: rolling monthly returns (+
    annualized versions), rolling daily volatility, and rolling Sharpe.

    Every metric is calculated strictly within each fund_label, sorted by
    date/month_end_date, with early-window values kept as NaN (never
    forward-filled) — the resulting long-form rows for those periods are
    still emitted with metric_value = NaN, preserving the full time index
    per fund/metric rather than silently dropping them.
    """
    _enforce_schema(returns_daily, RETURNS_DAILY_INPUT_COLUMNS, "returns_daily")
    _enforce_schema(returns_monthly, RETURNS_MONTHLY_INPUT_COLUMNS, "returns_monthly")

    rolling_returns = calculate_rolling_returns(returns_monthly)
    rolling_returns_ann = calculate_rolling_returns_annualized(returns_monthly)
    rolling_vol = calculate_rolling_volatility(returns_daily)
    rolling_return_ann_252d = _calculate_rolling_daily_return_ann(returns_daily, ROLLING_SHARPE_WINDOW_DAYS)

    return_ann_column = f"rolling_{ROLLING_SHARPE_WINDOW_DAYS}d_return_ann"
    vol_column = f"rolling_{ROLLING_SHARPE_WINDOW_DAYS}d_vol"
    daily_sharpe_inputs = pd.merge(
        rolling_vol[["date", "fund_label", vol_column]],
        rolling_return_ann_252d[["date", "fund_label", return_ann_column]],
        on=["date", "fund_label"],
        how="inner",  # both derived from the exact same returns_daily rows per fund
    )
    daily_sharpe_inputs["rolling_252d_sharpe"] = calculate_rolling_sharpe(
        daily_sharpe_inputs[return_ann_column], daily_sharpe_inputs[vol_column], risk_free_rate=risk_free_rate
    )

    long_frames = [
        _wide_to_long(
            rolling_returns,
            date_column="month_end_date",
            value_columns=[f"rolling_{w}m_return" for w in ROLLING_RETURN_WINDOWS_MONTHS],
            frequency=FREQUENCY_MONTHLY,
        ),
        _wide_to_long(
            rolling_returns_ann,
            date_column="month_end_date",
            value_columns=[f"rolling_{w}m_return_ann" for w in ROLLING_RETURN_ANN_WINDOWS_MONTHS],
            frequency=FREQUENCY_MONTHLY,
        ),
        _wide_to_long(
            rolling_vol,
            date_column="date",
            value_columns=[f"rolling_{w}d_vol" for w in ROLLING_VOL_WINDOWS_DAYS],
            frequency=FREQUENCY_DAILY,
        ),
        _wide_to_long(
            daily_sharpe_inputs,
            date_column="date",
            value_columns=[return_ann_column],
            frequency=FREQUENCY_DAILY,
        ),
        _wide_to_long(
            daily_sharpe_inputs,
            date_column="date",
            value_columns=["rolling_252d_sharpe"],
            frequency=FREQUENCY_DAILY,
        ),
    ]

    long_df = pd.concat(long_frames, ignore_index=True)
    long_df["date_or_month"] = pd.to_datetime(long_df["date_or_month"])
    long_df = long_df.sort_values(["fund_label", "metric_name", "date_or_month"]).reset_index(drop=True)

    return long_df[ROLLING_METRICS_COLUMNS]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _load_returns_daily() -> pd.DataFrame:
    if not RETURNS_DAILY_PATH.exists():
        raise DataValidationError(
            f"{RETURNS_DAILY_PATH} does not exist. Run the return engine "
            "(returns.run_return_engine()) before calculating rolling metrics."
        )
    return pd.read_csv(RETURNS_DAILY_PATH)


def _load_returns_monthly() -> pd.DataFrame:
    if not RETURNS_MONTHLY_PATH.exists():
        raise DataValidationError(
            f"{RETURNS_MONTHLY_PATH} does not exist. Run the return engine "
            "(returns.run_return_engine()) before calculating rolling metrics."
        )
    return pd.read_csv(RETURNS_MONTHLY_PATH)


def run_rolling_metrics_engine(risk_free_rate: float = DEFAULT_RISK_FREE_RATE) -> pd.DataFrame:
    """
    Full Phase 5 entry point: load returns_daily.csv and returns_monthly.csv,
    compute every required rolling metric, and write rolling_metrics.csv in
    long form (date_or_month, fund_label, metric_name, metric_value, frequency).

    Intended to be called explicitly (e.g. from refresh_data.py) — never on
    import, never inside a Streamlit page.
    """
    returns_daily = _load_returns_daily()
    returns_monthly = _load_returns_monthly()

    long_df = generate_rolling_metrics(returns_daily, returns_monthly, risk_free_rate=risk_free_rate)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output = long_df.copy()
    output["date_or_month"] = pd.to_datetime(output["date_or_month"]).dt.strftime("%Y-%m-%d")
    output.to_csv(ROLLING_METRICS_PATH, index=False)

    return long_df
