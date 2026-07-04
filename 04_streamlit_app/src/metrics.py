"""
Metrics Module.

Reference: 00_project_control/master_project_instructions.md.md §17 (Metrics
Module) and 00_project_control/formula_audit.md §3 (Core Metrics).
Related: 00_project_control/data_dictionary.md §4.10 (metrics_summary.csv).

Inputs (already fetched/validated/computed by earlier phases):
    02_processed_data/nav_daily_clean.csv   (used only for CAGR - "Daily NAV")
    02_processed_data/returns_daily.csv     (daily-return-based metrics)
    02_processed_data/returns_monthly.csv   (monthly-return-based metrics)

Output:
    02_processed_data/metrics_summary.csv

Non-negotiable rules (formula_audit.md §3):
- Never label a VaR/CVaR figure without stating its frequency (daily vs
  monthly) - enforced here via distinct daily_var_95 / monthly_var_95
  (and CVaR) columns; there is no unlabelled "var_95" anywhere.
- Never mix daily and monthly annualization within the same ratio - Sharpe
  and Sortino combine CAGR (annual) with *annualized* volatility/downside
  deviation (already annualized from daily data); no monthly figures are
  blended in.
- risk_free_rate default = 0.06, overridable, and always disclosed via the
  risk_free_rate_used column.
- All divisions are guarded against zero/undefined denominators (see
  _safe_divide) - metrics that cannot be reliably computed are NaN, never a
  fabricated number or a crash.

This module does not implement rolling metrics, benchmark-relative
analytics, stress testing, attribution, or Streamlit UI (later phases).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from data_cleaning import (  # noqa: E402 - sys.path must be configured before this import
    DataValidationError,
    load_nav_daily_clean,
    validate_nav_daily,
)
from returns import (  # noqa: E402 - sys.path must be configured before this import
    PROCESSED_DATA_DIR,
    RETURNS_DAILY_PATH,
    RETURNS_MONTHLY_PATH,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

METRICS_SUMMARY_PATH = PROCESSED_DATA_DIR / "metrics_summary.csv"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_RISK_FREE_RATE = 0.06
TRADING_DAYS_PER_YEAR = 252
CALENDAR_DAYS_PER_YEAR = 365
VAR_PERCENTILE = 0.05  # 5th percentile -> "95%" VaR/CVaR

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

NAV_DAILY_INPUT_COLUMNS = ["date", "fund_label", "nav"]
RETURNS_DAILY_INPUT_COLUMNS = ["date", "fund_label", "nav", "daily_return"]
RETURNS_MONTHLY_INPUT_COLUMNS = ["month_end_date", "fund_label", "monthly_return"]

# data_dictionary.md §4.10, extended with data_start_date, data_end_date,
# observation_count_daily, observation_count_monthly per explicit request.
METRICS_SUMMARY_COLUMNS = [
    "fund_label",
    "data_start_date",
    "data_end_date",
    "observation_count_daily",
    "observation_count_monthly",
    "cagr",
    "annualized_volatility",
    "downside_deviation",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "recovery_period_days",
    "best_month",
    "worst_month",
    "positive_month_ratio",
    "daily_var_95",
    "daily_cvar_95",
    "monthly_var_95",
    "monthly_cvar_95",
    "risk_free_rate_used",
    "as_of_date",
]


def _enforce_schema(df: pd.DataFrame, required_columns: List[str], label: str) -> None:
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise DataValidationError(f"{label} is missing required columns: {missing}")


def _safe_divide(numerator: float, denominator: float) -> float:
    """Division helper that returns NaN instead of raising/inf on a zero,
    missing, or NaN denominator (or a NaN numerator)."""
    if denominator is None or pd.isna(denominator) or denominator == 0:
        return float("nan")
    if numerator is None or pd.isna(numerator):
        return float("nan")
    return float(numerator / denominator)


# ---------------------------------------------------------------------------
# Individual metric calculations (each takes a single fund's data)
# ---------------------------------------------------------------------------

def calculate_cagr(nav_daily_fund: pd.DataFrame) -> float:
    """
    CAGR = (ending_nav / beginning_nav) ^ (365 / calendar_days) - 1

    Uses the first and last available daily NAV observations (from
    nav_daily_clean.csv), not returns_daily.csv - CAGR is explicitly a
    "Daily NAV" frequency metric per formula_audit.md §3, distinct from the
    daily-*return*-based metrics below.
    """
    if nav_daily_fund.empty:
        return float("nan")

    df = nav_daily_fund.sort_values("date")
    beginning_nav = df["nav"].iloc[0]
    ending_nav = df["nav"].iloc[-1]
    calendar_days = (df["date"].iloc[-1] - df["date"].iloc[0]).days

    if calendar_days <= 0 or pd.isna(beginning_nav) or pd.isna(ending_nav) or beginning_nav <= 0:
        return float("nan")

    ratio = ending_nav / beginning_nav
    if ratio <= 0:
        return float("nan")

    return float(ratio ** (CALENDAR_DAYS_PER_YEAR / calendar_days) - 1.0)


def calculate_annualized_volatility(daily_returns: pd.Series) -> float:
    """Annualized Volatility = STDEV(daily_return) x SQRT(252)."""
    valid = daily_returns.dropna()
    if len(valid) < 2:
        return float("nan")
    return float(valid.std(ddof=1) * (TRADING_DAYS_PER_YEAR ** 0.5))


def calculate_downside_deviation(daily_returns: pd.Series) -> float:
    """Downside Deviation = STDEV(negative daily returns) x SQRT(252)."""
    valid = daily_returns.dropna()
    negative = valid[valid < 0]
    if len(negative) < 2:
        return float("nan")
    return float(negative.std(ddof=1) * (TRADING_DAYS_PER_YEAR ** 0.5))


def calculate_sharpe_ratio(cagr: float, annualized_volatility: float, risk_free_rate: float) -> float:
    """Sharpe = (CAGR - risk_free_rate) / annualized_volatility. Both inputs are annual figures."""
    numerator = cagr - risk_free_rate if not pd.isna(cagr) else float("nan")
    return _safe_divide(numerator, annualized_volatility)


def calculate_sortino_ratio(cagr: float, downside_deviation: float, risk_free_rate: float) -> float:
    """Sortino = (CAGR - risk_free_rate) / downside_deviation. Both inputs are annual figures."""
    numerator = cagr - risk_free_rate if not pd.isna(cagr) else float("nan")
    return _safe_divide(numerator, downside_deviation)


def calculate_max_drawdown_and_recovery(daily_returns_fund: pd.DataFrame) -> Tuple[float, float]:
    """
    Builds a wealth index (anchored at 1.0 on the first observation; the
    first row's undefined daily_return is treated as 0.0 contribution only
    for this anchor, never forward-filled elsewhere) and computes:

    - max_drawdown: min(wealth / running_peak - 1) across the series -
      the worst peak-to-trough decline observed.
    - recovery_period_days: the longest CALENDAR-DAY duration between a
      peak and the date wealth fully recovers to (or exceeds) that peak
      level again. Only COMPLETED recoveries are counted. If the fund is
      still below a prior peak as of the last observation and has never
      completed any other recovery, this is NaN (not yet observed to
      recover - never fabricated as 0 or "ongoing"). If the fund never
      experienced any drawdown at all, this is 0 (no recovery needed).
    """
    if daily_returns_fund.empty:
        return float("nan"), float("nan")

    df = daily_returns_fund.sort_values("date").reset_index(drop=True)
    filled_returns = df["daily_return"].fillna(0.0)
    wealth = (1.0 + filled_returns).cumprod()
    running_peak = wealth.cummax()
    drawdown = wealth / running_peak - 1.0
    max_drawdown = float(drawdown.min())

    peak_value = wealth.iloc[0]
    peak_date = df["date"].iloc[0]
    drawdown_active = False
    had_completed_recovery = False
    max_recovery_days = 0

    for date, wealth_value in zip(df["date"], wealth):
        if wealth_value >= peak_value:
            if drawdown_active:
                recovery_days = (date - peak_date).days
                max_recovery_days = max(max_recovery_days, recovery_days)
                had_completed_recovery = True
                drawdown_active = False
            peak_value = wealth_value
            peak_date = date
        else:
            drawdown_active = True

    if drawdown_active and not had_completed_recovery:
        recovery_period_days = float("nan")
    else:
        recovery_period_days = float(max_recovery_days)

    return max_drawdown, recovery_period_days


def calculate_best_worst_month(monthly_returns: pd.Series) -> Tuple[float, float]:
    """Best Month = MAX(monthly_return); Worst Month = MIN(monthly_return)."""
    valid = monthly_returns.dropna()
    if valid.empty:
        return float("nan"), float("nan")
    return float(valid.max()), float(valid.min())


def calculate_positive_month_ratio(monthly_returns: pd.Series) -> float:
    """Positive Month Ratio = count(monthly_return > 0) / count(valid monthly_return)."""
    valid = monthly_returns.dropna()
    if valid.empty:
        return float("nan")
    return float((valid > 0).sum() / len(valid))


def calculate_var_cvar(returns: pd.Series, percentile: float = VAR_PERCENTILE) -> Tuple[float, float]:
    """
    Generic VaR/CVaR calculation (frequency-agnostic by design - the CALLER
    must store the result under a frequency-labelled column such as
    daily_var_95 / monthly_var_95; this rule is enforced structurally by
    METRICS_SUMMARY_COLUMNS never containing an unlabelled "var_95").

    VaR  = 5th percentile of the return distribution.
    CVaR = mean of returns <= VaR (the average tail loss beyond VaR).
    """
    valid = returns.dropna()
    if valid.empty:
        return float("nan"), float("nan")

    var_value = float(valid.quantile(percentile))
    tail = valid[valid <= var_value]
    cvar_value = float(tail.mean()) if not tail.empty else float("nan")
    return var_value, cvar_value


# ---------------------------------------------------------------------------
# Per-fund and full summary assembly
# ---------------------------------------------------------------------------

def calculate_fund_metrics(
    fund_label: str,
    nav_daily_fund: pd.DataFrame,
    returns_daily_fund: pd.DataFrame,
    returns_monthly_fund: pd.DataFrame,
    risk_free_rate: float,
    as_of_date: str,
) -> Dict[str, Any]:
    """Compute every required metric for a single fund and return one metrics_summary.csv row."""
    nav_daily_fund = nav_daily_fund.sort_values("date")
    returns_daily_fund = returns_daily_fund.sort_values("date")
    returns_monthly_fund = returns_monthly_fund.sort_values("month_end_date")

    data_start_date = nav_daily_fund["date"].min()
    data_end_date = nav_daily_fund["date"].max()
    observation_count_daily = int(len(nav_daily_fund))
    observation_count_monthly = int(len(returns_monthly_fund))

    cagr = calculate_cagr(nav_daily_fund)
    annualized_volatility = calculate_annualized_volatility(returns_daily_fund["daily_return"])
    downside_deviation = calculate_downside_deviation(returns_daily_fund["daily_return"])
    sharpe_ratio = calculate_sharpe_ratio(cagr, annualized_volatility, risk_free_rate)
    sortino_ratio = calculate_sortino_ratio(cagr, downside_deviation, risk_free_rate)
    max_drawdown, recovery_period_days = calculate_max_drawdown_and_recovery(
        returns_daily_fund[["date", "daily_return"]]
    )
    best_month, worst_month = calculate_best_worst_month(returns_monthly_fund["monthly_return"])
    positive_month_ratio = calculate_positive_month_ratio(returns_monthly_fund["monthly_return"])
    daily_var_95, daily_cvar_95 = calculate_var_cvar(returns_daily_fund["daily_return"])
    monthly_var_95, monthly_cvar_95 = calculate_var_cvar(returns_monthly_fund["monthly_return"])

    return {
        "fund_label": fund_label,
        "data_start_date": data_start_date,
        "data_end_date": data_end_date,
        "observation_count_daily": observation_count_daily,
        "observation_count_monthly": observation_count_monthly,
        "cagr": cagr,
        "annualized_volatility": annualized_volatility,
        "downside_deviation": downside_deviation,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "max_drawdown": max_drawdown,
        "recovery_period_days": recovery_period_days,
        "best_month": best_month,
        "worst_month": worst_month,
        "positive_month_ratio": positive_month_ratio,
        "daily_var_95": daily_var_95,
        "daily_cvar_95": daily_cvar_95,
        "monthly_var_95": monthly_var_95,
        "monthly_cvar_95": monthly_cvar_95,
        "risk_free_rate_used": risk_free_rate,
        "as_of_date": as_of_date,
    }


def calculate_metrics_summary(
    nav_daily: pd.DataFrame,
    returns_daily: pd.DataFrame,
    returns_monthly: pd.DataFrame,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> pd.DataFrame:
    """
    Build the full metrics_summary.csv content, one row per fund_label
    present in nav_daily. `risk_free_rate` defaults to 0.06 and is always
    recorded in risk_free_rate_used so it is disclosed wherever the summary
    is shown, per formula_audit.md §3.
    """
    _enforce_schema(nav_daily, NAV_DAILY_INPUT_COLUMNS, "nav_daily")
    _enforce_schema(returns_daily, RETURNS_DAILY_INPUT_COLUMNS, "returns_daily")
    _enforce_schema(returns_monthly, RETURNS_MONTHLY_INPUT_COLUMNS, "returns_monthly")

    nav_daily = nav_daily.copy()
    nav_daily["date"] = pd.to_datetime(nav_daily["date"])
    returns_daily = returns_daily.copy()
    returns_daily["date"] = pd.to_datetime(returns_daily["date"])
    returns_monthly = returns_monthly.copy()
    returns_monthly["month_end_date"] = pd.to_datetime(returns_monthly["month_end_date"])

    as_of_date = pd.Timestamp.now().strftime("%Y-%m-%d")

    fund_labels = sorted(nav_daily["fund_label"].dropna().unique().tolist())
    rows: List[Dict[str, Any]] = []
    for fund_label in fund_labels:
        rows.append(
            calculate_fund_metrics(
                fund_label,
                nav_daily[nav_daily["fund_label"] == fund_label],
                returns_daily[returns_daily["fund_label"] == fund_label],
                returns_monthly[returns_monthly["fund_label"] == fund_label],
                risk_free_rate,
                as_of_date,
            )
        )

    summary = pd.DataFrame(rows, columns=METRICS_SUMMARY_COLUMNS)
    if not summary.empty:
        for date_column in ("data_start_date", "data_end_date"):
            summary[date_column] = pd.to_datetime(summary[date_column]).dt.strftime("%Y-%m-%d")

    return summary


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _load_returns_daily() -> pd.DataFrame:
    if not RETURNS_DAILY_PATH.exists():
        raise DataValidationError(
            f"{RETURNS_DAILY_PATH} does not exist. Run the return engine "
            "(returns.run_return_engine()) before calculating metrics."
        )
    return pd.read_csv(RETURNS_DAILY_PATH)


def _load_returns_monthly() -> pd.DataFrame:
    if not RETURNS_MONTHLY_PATH.exists():
        raise DataValidationError(
            f"{RETURNS_MONTHLY_PATH} does not exist. Run the return engine "
            "(returns.run_return_engine()) before calculating metrics."
        )
    return pd.read_csv(RETURNS_MONTHLY_PATH)


def run_metrics_engine(risk_free_rate: float = DEFAULT_RISK_FREE_RATE) -> pd.DataFrame:
    """
    Full Phase 5 entry point: load nav_daily_clean.csv (validated/cleaned
    via data_cleaning.py, so CAGR uses the same 2021-01-01+ data horizon as
    everywhere else in the project) plus the already-computed
    returns_daily.csv and returns_monthly.csv, calculate every required
    fund-level metric, and write metrics_summary.csv.

    Intended to be called explicitly (e.g. from refresh_data.py) - never on
    import, never inside a Streamlit page.
    """
    nav_daily = validate_nav_daily(load_nav_daily_clean())
    returns_daily = _load_returns_daily()
    returns_monthly = _load_returns_monthly()

    summary = calculate_metrics_summary(nav_daily, returns_daily, returns_monthly, risk_free_rate=risk_free_rate)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(METRICS_SUMMARY_PATH, index=False)

    return summary
