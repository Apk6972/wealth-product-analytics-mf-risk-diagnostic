"""
Benchmark Analytics Module — excess return, beta, tracking error, IR, capture ratios.

Reference: 00_project_control/master_project_instructions.md.md §19 (Benchmark
Analytics Module) and 00_project_control/formula_audit.md §5.

Inputs:
    02_processed_data/returns_daily.csv         (fund daily returns, Phase 4)
    02_processed_data/benchmark_daily.csv       (benchmark tri_value; benchmark
        daily returns are derived here via returns.calculate_benchmark_daily_returns)
    01_raw_data/scheme_master/benchmark_map.csv (fund_label -> primary_benchmark)

Outputs:
    02_processed_data/benchmark_metrics.csv         (data_dictionary.md §4.8)
    02_processed_data/rolling_benchmark_metrics.csv (data_dictionary.md §4.9)

Rule: each fund is matched to its own primary benchmark only — never a
single shared benchmark across all funds (formula_audit.md §5). Dates are
inner-joined (aligned) on trading date before any covariance/variance/ratio
calculation.

Annualization convention (formula_audit.md §5, §9): Tracking Error
annualizes a *standard deviation* (STDEV x SQRT(252)). The paired
"annualized excess return" used as Information Ratio's numerator instead
annualizes a *mean* daily figure via simple linear scaling
(mean(daily excess_return) x 252, not SQRT(252) and not compounding) — the
standard convention for excess-return/tracking-error-based ratios, and
consistent with this project's "never mix daily and monthly annualization
within the same ratio" rule.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Dict, List

import pandas as pd

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from data_cleaning import DataValidationError  # noqa: E402 - sys.path must be configured before this import
from returns import (  # noqa: E402 - sys.path must be configured before this import
    PROCESSED_DATA_DIR,
    PROJECT_ROOT,
    RETURNS_DAILY_COLUMNS,
    RETURNS_DAILY_PATH,
    calculate_benchmark_daily_returns,
)
from utils import TRADING_DAYS_PER_YEAR, annualization_factor  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCHEME_MASTER_DIR = PROJECT_ROOT / "01_raw_data" / "scheme_master"
BENCHMARK_MAP_PATH = SCHEME_MASTER_DIR / "benchmark_map.csv"
BENCHMARK_DAILY_PATH = PROCESSED_DATA_DIR / "benchmark_daily.csv"

BENCHMARK_METRICS_PATH = PROCESSED_DATA_DIR / "benchmark_metrics.csv"
ROLLING_BENCHMARK_METRICS_PATH = PROCESSED_DATA_DIR / "rolling_benchmark_metrics.csv"

# ---------------------------------------------------------------------------
# Schemas / constants
# ---------------------------------------------------------------------------

BENCHMARK_MAP_COLUMNS = ["fund_label", "primary_benchmark"]
BENCHMARK_DAILY_INPUT_COLUMNS = ["date", "benchmark_label", "tri_value"]

BENCHMARK_METRICS_COLUMNS = [
    "fund_label",
    "benchmark_label",
    "excess_return_ann",
    "beta",
    "tracking_error",
    "information_ratio",
    "upside_capture",
    "downside_capture",
]

ROLLING_WINDOW_DAYS = 252
ROLLING_BENCHMARK_METRICS_COLUMNS = [
    "date",
    "fund_label",
    "benchmark_label",
    f"rolling_{ROLLING_WINDOW_DAYS}d_beta",
    f"rolling_{ROLLING_WINDOW_DAYS}d_tracking_error",
    f"rolling_{ROLLING_WINDOW_DAYS}d_information_ratio",
]

# Below this many aligned trading days, beta/tracking-error/IR/capture are
# statistically unreliable — emit NaN rather than a number computed from an
# almost-empty sample. Rolling metrics are unaffected (they already use
# min_periods=ROLLING_WINDOW_DAYS, which is a much stricter bar).
MIN_ALIGNED_OBSERVATIONS_FOR_STATIC_METRICS = 20


def _enforce_schema(df: pd.DataFrame, required_columns: List[str], label: str) -> None:
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise DataValidationError(f"{label} is missing required columns: {missing}")


# ---------------------------------------------------------------------------
# Date alignment
# ---------------------------------------------------------------------------

def align_fund_benchmark_returns(
    returns_daily: pd.DataFrame,
    benchmark_returns_daily: pd.DataFrame,
    fund_label: str,
    benchmark_label: str,
) -> pd.DataFrame:
    """
    Inner-join one fund's daily returns with one benchmark's daily returns
    on trading date (formula_audit.md §5: "Dates must be aligned... before
    any covariance/variance/ratio calculation"). Rows with either return
    missing are dropped, never filled.

    Returns columns: date, fund_return, benchmark_return, excess_return,
    sorted by date.
    """
    fund_series = returns_daily[returns_daily["fund_label"] == fund_label][["date", "daily_return"]].rename(
        columns={"daily_return": "fund_return"}
    )
    fund_series = fund_series.copy()
    fund_series["date"] = pd.to_datetime(fund_series["date"])

    benchmark_series = benchmark_returns_daily[benchmark_returns_daily["benchmark_label"] == benchmark_label][
        ["date", "daily_return"]
    ].rename(columns={"daily_return": "benchmark_return"})

    aligned = pd.merge(fund_series, benchmark_series, on="date", how="inner").dropna(
        subset=["fund_return", "benchmark_return"]
    )
    aligned = aligned.sort_values("date").reset_index(drop=True)
    aligned["excess_return"] = calculate_excess_return(aligned["fund_return"], aligned["benchmark_return"])
    return aligned


# ---------------------------------------------------------------------------
# Per-metric formulas (operate on already-aligned Series)
# ---------------------------------------------------------------------------

def calculate_excess_return(fund_return: pd.Series, benchmark_return: pd.Series) -> pd.Series:
    """Excess Return = fund_return - benchmark_return (already date-aligned by the caller)."""
    return fund_return - benchmark_return


def calculate_beta(fund_return: pd.Series, benchmark_return: pd.Series) -> float:
    """Beta = Cov(fund_return, benchmark_return) / Var(benchmark_return), over the full aligned history."""
    if len(fund_return) < 2:
        return float("nan")
    benchmark_variance = benchmark_return.var(ddof=1)
    if benchmark_variance == 0 or pd.isna(benchmark_variance):
        return float("nan")
    covariance = fund_return.cov(benchmark_return)
    return float(covariance / benchmark_variance)


def calculate_tracking_error(excess_return: pd.Series, ann_factor: float) -> float:
    """Tracking Error = STDEV(excess_return) x annualization_factor (SQRT(252) daily, SQRT(12) monthly)."""
    if len(excess_return) < 2:
        return float("nan")
    return float(excess_return.std(ddof=1) * ann_factor)


def calculate_information_ratio(annualized_excess_return: float, tracking_error: float) -> float:
    """Information Ratio = annualized_excess_return / tracking_error."""
    if tracking_error is None or pd.isna(tracking_error) or tracking_error == 0:
        return float("nan")
    return float(annualized_excess_return / tracking_error)


def calculate_capture_ratios(fund_return: pd.Series, benchmark_return: pd.Series) -> Dict[str, float]:
    """
    Upside/Downside Capture on a compounded cumulative basis, split by
    benchmark sign (formula_audit.md §5):

        Upside Capture   = (PRODUCT(1 + fund_return | benchmark_return > 0) - 1)
                            / (PRODUCT(1 + benchmark_return | benchmark_return > 0) - 1)
        Downside Capture = (PRODUCT(1 + fund_return | benchmark_return < 0) - 1)
                            / (PRODUCT(1 + benchmark_return | benchmark_return < 0) - 1)
    """

    def _capture(mask: pd.Series) -> float:
        if mask.sum() == 0:
            return float("nan")
        fund_cumulative = float((1.0 + fund_return[mask]).prod() - 1.0)
        benchmark_cumulative = float((1.0 + benchmark_return[mask]).prod() - 1.0)
        if benchmark_cumulative == 0:
            return float("nan")
        return fund_cumulative / benchmark_cumulative

    return {
        "upside_capture": _capture(benchmark_return > 0),
        "downside_capture": _capture(benchmark_return < 0),
    }


# ---------------------------------------------------------------------------
# Assembly — static (full-history) benchmark_metrics.csv
# ---------------------------------------------------------------------------

def generate_benchmark_metrics(
    returns_daily: pd.DataFrame,
    benchmark_daily: pd.DataFrame,
    benchmark_map: pd.DataFrame,
) -> pd.DataFrame:
    """
    Assemble 02_processed_data/benchmark_metrics.csv per data_dictionary.md
    §4.8: one row per fund, each matched to its own primary_benchmark from
    benchmark_map.csv (never one shared benchmark for every fund).
    """
    _enforce_schema(returns_daily, RETURNS_DAILY_COLUMNS, "returns_daily")
    _enforce_schema(benchmark_daily, BENCHMARK_DAILY_INPUT_COLUMNS, "benchmark_daily")
    _enforce_schema(benchmark_map, BENCHMARK_MAP_COLUMNS, "benchmark_map")

    benchmark_returns_daily = calculate_benchmark_daily_returns(benchmark_daily)
    daily_ann_factor = annualization_factor("daily")

    fund_labels_available = set(returns_daily["fund_label"].unique())
    benchmark_labels_available = set(benchmark_returns_daily["benchmark_label"].unique())

    rows = []
    for _, map_row in benchmark_map.iterrows():
        fund_label = map_row["fund_label"]
        benchmark_label = map_row["primary_benchmark"]

        if fund_label not in fund_labels_available:
            warnings.warn(f"'{fund_label}' has no daily return data; skipping its benchmark_metrics row.")
            continue
        if benchmark_label not in benchmark_labels_available:
            warnings.warn(
                f"Primary benchmark '{benchmark_label}' for '{fund_label}' has no daily data; "
                "skipping its benchmark_metrics row."
            )
            continue

        aligned = align_fund_benchmark_returns(returns_daily, benchmark_returns_daily, fund_label, benchmark_label)

        if len(aligned) < MIN_ALIGNED_OBSERVATIONS_FOR_STATIC_METRICS:
            warnings.warn(
                f"Only {len(aligned)} aligned trading day(s) between '{fund_label}' and '{benchmark_label}' "
                f"(< {MIN_ALIGNED_OBSERVATIONS_FOR_STATIC_METRICS}); benchmark_metrics values set to NaN."
            )
            rows.append(
                {
                    "fund_label": fund_label,
                    "benchmark_label": benchmark_label,
                    "excess_return_ann": float("nan"),
                    "beta": float("nan"),
                    "tracking_error": float("nan"),
                    "information_ratio": float("nan"),
                    "upside_capture": float("nan"),
                    "downside_capture": float("nan"),
                }
            )
            continue

        excess_return_ann = float(aligned["excess_return"].mean() * TRADING_DAYS_PER_YEAR)
        beta = calculate_beta(aligned["fund_return"], aligned["benchmark_return"])
        tracking_error = calculate_tracking_error(aligned["excess_return"], daily_ann_factor)
        information_ratio = calculate_information_ratio(excess_return_ann, tracking_error)
        capture = calculate_capture_ratios(aligned["fund_return"], aligned["benchmark_return"])

        rows.append(
            {
                "fund_label": fund_label,
                "benchmark_label": benchmark_label,
                "excess_return_ann": excess_return_ann,
                "beta": beta,
                "tracking_error": tracking_error,
                "information_ratio": information_ratio,
                "upside_capture": capture["upside_capture"],
                "downside_capture": capture["downside_capture"],
            }
        )

    return pd.DataFrame(rows, columns=BENCHMARK_METRICS_COLUMNS)


# ---------------------------------------------------------------------------
# Assembly — rolling_benchmark_metrics.csv
# ---------------------------------------------------------------------------

def generate_rolling_benchmark_metrics(
    returns_daily: pd.DataFrame,
    benchmark_daily: pd.DataFrame,
    benchmark_map: pd.DataFrame,
    window_days: int = ROLLING_WINDOW_DAYS,
) -> pd.DataFrame:
    """
    Assemble 02_processed_data/rolling_benchmark_metrics.csv per
    data_dictionary.md §4.9: rolling `window_days`-trading-day beta,
    tracking error, and information ratio, one row per (fund, date) in the
    fund/benchmark's aligned history. min_periods = window_days, so
    early-window values are NaN — never forward-filled, matching
    rolling_metrics.py's convention.
    """
    _enforce_schema(returns_daily, RETURNS_DAILY_COLUMNS, "returns_daily")
    _enforce_schema(benchmark_daily, BENCHMARK_DAILY_INPUT_COLUMNS, "benchmark_daily")
    _enforce_schema(benchmark_map, BENCHMARK_MAP_COLUMNS, "benchmark_map")

    benchmark_returns_daily = calculate_benchmark_daily_returns(benchmark_daily)
    daily_ann_factor = annualization_factor("daily")

    beta_column = f"rolling_{window_days}d_beta"
    te_column = f"rolling_{window_days}d_tracking_error"
    ir_column = f"rolling_{window_days}d_information_ratio"

    fund_labels_available = set(returns_daily["fund_label"].unique())
    benchmark_labels_available = set(benchmark_returns_daily["benchmark_label"].unique())

    frames = []
    for _, map_row in benchmark_map.iterrows():
        fund_label = map_row["fund_label"]
        benchmark_label = map_row["primary_benchmark"]

        if fund_label not in fund_labels_available or benchmark_label not in benchmark_labels_available:
            continue

        aligned = align_fund_benchmark_returns(returns_daily, benchmark_returns_daily, fund_label, benchmark_label)
        if aligned.empty:
            continue

        rolling_covariance = aligned["fund_return"].rolling(window=window_days, min_periods=window_days).cov(
            aligned["benchmark_return"]
        )
        rolling_variance = aligned["benchmark_return"].rolling(window=window_days, min_periods=window_days).var(
            ddof=1
        )
        rolling_beta = rolling_covariance / rolling_variance.mask(rolling_variance == 0)

        rolling_tracking_error = (
            aligned["excess_return"].rolling(window=window_days, min_periods=window_days).std(ddof=1)
            * daily_ann_factor
        )

        rolling_excess_return_ann = (
            aligned["excess_return"].rolling(window=window_days, min_periods=window_days).mean()
            * TRADING_DAYS_PER_YEAR
        )
        rolling_information_ratio = rolling_excess_return_ann / rolling_tracking_error.mask(
            rolling_tracking_error == 0
        )

        result = aligned[["date"]].copy()
        result["fund_label"] = fund_label
        result["benchmark_label"] = benchmark_label
        result[beta_column] = rolling_beta
        result[te_column] = rolling_tracking_error
        result[ir_column] = rolling_information_ratio
        frames.append(result)

    if not frames:
        return pd.DataFrame(columns=ROLLING_BENCHMARK_METRICS_COLUMNS)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["fund_label", "date"]).reset_index(drop=True)
    return combined[ROLLING_BENCHMARK_METRICS_COLUMNS]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _load_returns_daily() -> pd.DataFrame:
    if not RETURNS_DAILY_PATH.exists():
        raise DataValidationError(
            f"{RETURNS_DAILY_PATH} does not exist. Run the return engine "
            "(returns.run_return_engine()) before running the benchmark analytics engine."
        )
    return pd.read_csv(RETURNS_DAILY_PATH)


def _load_benchmark_daily() -> pd.DataFrame:
    if not BENCHMARK_DAILY_PATH.exists():
        raise DataValidationError(
            f"{BENCHMARK_DAILY_PATH} does not exist. Run the API fetch/validation pipeline "
            "before running the benchmark analytics engine."
        )
    return pd.read_csv(BENCHMARK_DAILY_PATH)


def _load_benchmark_map() -> pd.DataFrame:
    if not BENCHMARK_MAP_PATH.exists():
        raise DataValidationError(f"{BENCHMARK_MAP_PATH} does not exist.")
    df = pd.read_csv(BENCHMARK_MAP_PATH)
    _enforce_schema(df, BENCHMARK_MAP_COLUMNS, "benchmark_map.csv")
    return df


def run_benchmarks_engine() -> Dict[str, pd.DataFrame]:
    """
    Full Phase 6 entry point: load returns_daily.csv, benchmark_daily.csv,
    and benchmark_map.csv, compute fund-specific benchmark-relative
    analytics (each fund matched to its own primary benchmark only), and
    write benchmark_metrics.csv + rolling_benchmark_metrics.csv.

    Intended to be called explicitly (e.g. from refresh_data.py) — never on
    import, never inside a Streamlit page.
    """
    returns_daily = _load_returns_daily()
    benchmark_daily = _load_benchmark_daily()
    benchmark_map = _load_benchmark_map()

    benchmark_metrics = generate_benchmark_metrics(returns_daily, benchmark_daily, benchmark_map)
    rolling_benchmark_metrics = generate_rolling_benchmark_metrics(returns_daily, benchmark_daily, benchmark_map)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    benchmark_metrics.to_csv(BENCHMARK_METRICS_PATH, index=False)

    rolling_output = rolling_benchmark_metrics.copy()
    if not rolling_output.empty:
        rolling_output["date"] = pd.to_datetime(rolling_output["date"]).dt.strftime("%Y-%m-%d")
    rolling_output.to_csv(ROLLING_BENCHMARK_METRICS_PATH, index=False)

    return {
        "benchmark_metrics": benchmark_metrics,
        "rolling_benchmark_metrics": rolling_benchmark_metrics,
    }
