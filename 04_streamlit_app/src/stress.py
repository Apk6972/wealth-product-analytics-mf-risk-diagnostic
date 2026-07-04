"""
Stress Testing Module — historical replay, deterministic shocks, custom shocks.

Reference: 00_project_control/master_project_instructions.md.md §20 (Stress
Testing Module) and 00_project_control/formula_audit.md §6.

Inputs:
    02_processed_data/returns_daily.csv
    02_processed_data/returns_monthly.csv
    01_raw_data/scheme_master/portfolio_weights.csv
    01_raw_data/scheme_master/stress_scenarios.csv
    02_processed_data/benchmark_daily.csv (optional — only used for the
        "worst benchmark drawdown period" historical scenario, per the
        instruction that this scenario applies "if benchmark data exists")

Output:
    02_processed_data/stress_results.csv
    Columns (data_dictionary.md §4.11): scenario_type, scenario_name,
    fund_label, stress_return, window_start, window_end, rationale

Stress types:
    A. Historical replay - actual historical returns over an identified
       worst-case window (worst 1-month / 3-month / 20-trading-day
       portfolio period, worst small-cap fund period, worst benchmark
       drawdown period). Once a window is identified, every portfolio
       fund's own actual compounded return over that exact window is
       reported (not just the fund that anchored the window's discovery),
       so downstream attribution always has full fund coverage.
    B. Deterministic - fixed illustrative shocks from stress_scenarios.csv.
    C. Custom - interactive fund-level shocks for Streamlit sliders,
       returned as a live attribution table (see run_custom_shock below);
       never persisted to stress_results.csv.

Rule: deterministic (and custom) scenarios must always be labelled
illustrative assumptions, not forecasts.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    RETURNS_MONTHLY_COLUMNS,
    RETURNS_MONTHLY_PATH,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCHEME_MASTER_DIR = PROJECT_ROOT / "01_raw_data" / "scheme_master"
PORTFOLIO_WEIGHTS_PATH = SCHEME_MASTER_DIR / "portfolio_weights.csv"
STRESS_SCENARIOS_PATH = SCHEME_MASTER_DIR / "stress_scenarios.csv"
BENCHMARK_DAILY_PATH = PROCESSED_DATA_DIR / "benchmark_daily.csv"

STRESS_RESULTS_PATH = PROCESSED_DATA_DIR / "stress_results.csv"

# ---------------------------------------------------------------------------
# Constants / schemas
# ---------------------------------------------------------------------------

SCENARIO_TYPE_HISTORICAL = "HISTORICAL_REPLAY"
SCENARIO_TYPE_DETERMINISTIC = "DETERMINISTIC"
SCENARIO_TYPE_CUSTOM = "CUSTOM"

DETERMINISTIC_DISCLOSURE = "Deterministic stress scenarios are illustrative assumptions, not forecasts."
CUSTOM_DISCLOSURE = "User-defined interactive shock (Streamlit slider input). Illustrative, not a forecast."

DEFAULT_BASE_PORTFOLIO_VALUE = 10_000_000.0
ROLLING_3M_WINDOW_MONTHS = 3
ROLLING_20D_WINDOW_DAYS = 20

PORTFOLIO_WEIGHTS_COLUMNS = ["fund_label", "weight"]

# Sentinel distinguishing "benchmark_daily not passed" (auto-load from disk)
# from an explicit benchmark_daily=None (caller has no benchmark data / wants
# the drawdown scenario skipped) - a plain None default would conflate the two.
_UNSET = object()

STRESS_RESULTS_COLUMNS = [
    "scenario_type",
    "scenario_name",
    "fund_label",
    "stress_return",
    "window_start",
    "window_end",
    "rationale",
]


def _enforce_schema(df: pd.DataFrame, required_columns: List[str], label: str) -> None:
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise DataValidationError(f"{label} is missing required columns: {missing}")


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------

def _load_portfolio_weights() -> pd.DataFrame:
    if not PORTFOLIO_WEIGHTS_PATH.exists():
        raise DataValidationError(f"{PORTFOLIO_WEIGHTS_PATH} does not exist.")
    df = pd.read_csv(PORTFOLIO_WEIGHTS_PATH)
    _enforce_schema(df, PORTFOLIO_WEIGHTS_COLUMNS, "portfolio_weights.csv")
    total_weight = df["weight"].sum()
    if abs(total_weight - 1.0) > 1e-6:
        warnings.warn(f"portfolio_weights.csv weights sum to {total_weight:.4f}, not 1.0.")
    return df


def _load_stress_scenarios() -> pd.DataFrame:
    if not STRESS_SCENARIOS_PATH.exists():
        raise DataValidationError(f"{STRESS_SCENARIOS_PATH} does not exist.")
    return pd.read_csv(STRESS_SCENARIOS_PATH)


def _load_benchmark_daily() -> Optional[pd.DataFrame]:
    """Benchmark data is optional for the stress engine (only the "worst
    benchmark drawdown" scenario needs it); return None if unavailable
    rather than failing the whole engine."""
    if not BENCHMARK_DAILY_PATH.exists():
        return None
    return pd.read_csv(BENCHMARK_DAILY_PATH)


# ---------------------------------------------------------------------------
# Small helpers shared by the historical-replay scenarios
# ---------------------------------------------------------------------------

def _identify_small_cap_fund(fund_labels: List[str]) -> str:
    """
    Identify "the" small-cap fund generically (rather than hardcoding a
    single literal fund name) by looking for a "small cap" substring
    (case-insensitive) in fund_label. Raises DataValidationError if none or
    more than one fund matches, rather than guessing.
    """
    matches = [label for label in fund_labels if "small cap" in str(label).lower()]
    if not matches:
        raise DataValidationError(
            "Could not identify a small-cap fund from fund_label values (looked for a "
            f"'small cap' substring, case-insensitive) in: {list(fund_labels)}"
        )
    if len(matches) > 1:
        raise DataValidationError(f"Ambiguous small-cap fund identification, multiple matches: {matches}")
    return matches[0]


def _portfolio_weighted_series(returns_pivot: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """
    returns_pivot: index=date/month_end_date, columns=fund_label, values=return.
    weights: index=fund_label, values=weight.

    Only dates where every weighted fund has a non-NaN return are included -
    a portfolio-level return requires full coverage across its holdings for
    that date, never a partial/forward-filled approximation.
    """
    missing_funds = [fund for fund in weights.index if fund not in returns_pivot.columns]
    if missing_funds:
        warnings.warn(
            f"Portfolio fund(s) {missing_funds} have no return series available; excluded from "
            "the portfolio-weighted series (remaining weights are used as-is, not renormalized)."
        )
    common_funds = [fund for fund in weights.index if fund in returns_pivot.columns]
    if not common_funds:
        return pd.Series(dtype=float)
    aligned = returns_pivot[common_funds].dropna(how="any")
    if aligned.empty:
        return pd.Series(dtype=float)
    return aligned.dot(weights.loc[common_funds])


def _cumulative_return_over_window(
    returns_long: pd.DataFrame,
    fund_label: str,
    date_column: str,
    return_column: str,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> float:
    """PRODUCT(1 + return over [window_start, window_end], inclusive) - 1 for one fund_label."""
    series = returns_long[
        (returns_long["fund_label"] == fund_label)
        & (returns_long[date_column] >= window_start)
        & (returns_long[date_column] <= window_end)
    ][return_column].dropna()
    if series.empty:
        return float("nan")
    return float((1.0 + series).prod() - 1.0)


def _build_fund_rows_for_window(
    fund_labels: List[str],
    returns_daily: pd.DataFrame,
    returns_monthly: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    use_daily: bool,
) -> pd.DataFrame:
    """Every portfolio fund's own actual compounded return over [window_start, window_end]."""
    rows = []
    for fund_label in fund_labels:
        if use_daily:
            stress_return = _cumulative_return_over_window(
                returns_daily, fund_label, "date", "daily_return", window_start, window_end
            )
        else:
            stress_return = _cumulative_return_over_window(
                returns_monthly, fund_label, "month_end_date", "monthly_return", window_start, window_end
            )
        rows.append({"fund_label": fund_label, "stress_return": stress_return})
    return pd.DataFrame(rows)


def _max_drawdown_window(values: pd.Series) -> Tuple[pd.Timestamp, pd.Timestamp, float]:
    """
    Given a chronologically sorted Series of daily index/TRI levels (indexed
    by date), return (peak_date, trough_date, drawdown_magnitude) for the
    single deepest peak-to-trough drawdown. drawdown_magnitude is <= 0.
    """
    running_peak = values.cummax()
    drawdown = values / running_peak - 1.0
    trough_date = drawdown.idxmin()
    drawdown_magnitude = float(drawdown.loc[trough_date])
    peak_date = values.loc[:trough_date].idxmax()
    return peak_date, trough_date, drawdown_magnitude


def _worst_benchmark_drawdown_window(benchmark_daily: pd.DataFrame) -> Tuple[pd.Timestamp, pd.Timestamp, float, str]:
    """
    Compute the deepest peak-to-trough drawdown for every benchmark_label
    present and return the single worst one across all benchmarks (fully
    data-driven — no benchmark is hardcoded as "the" market benchmark).
    """
    df = benchmark_daily.copy()
    df["date"] = pd.to_datetime(df["date"])

    worst: Optional[Tuple[pd.Timestamp, pd.Timestamp, float, str]] = None
    for benchmark_label, group in df.groupby("benchmark_label"):
        group = group.sort_values("date").dropna(subset=["tri_value"])
        if len(group) < 2:
            continue
        series = group.set_index("date")["tri_value"]
        peak_date, trough_date, magnitude = _max_drawdown_window(series)
        if worst is None or magnitude < worst[2]:
            worst = (peak_date, trough_date, magnitude, benchmark_label)

    if worst is None:
        raise DataValidationError("No usable benchmark series found to compute a drawdown window.")
    return worst


# ---------------------------------------------------------------------------
# A. Historical replay
# ---------------------------------------------------------------------------

def run_historical_replay(
    returns_daily: pd.DataFrame,
    returns_monthly: pd.DataFrame,
    portfolio_weights: Optional[pd.DataFrame] = None,
    benchmark_daily: Optional[pd.DataFrame] = _UNSET,
) -> pd.DataFrame:
    """
    Identify worst 1M / 3M / 20-trading-day portfolio periods, worst
    small-cap fund period, and worst benchmark drawdown period (if
    available). For each identified window, every portfolio fund's own
    actual compounded return over that window is reported.

    benchmark_daily: omit to auto-load 02_processed_data/benchmark_daily.csv
    from disk if present; pass None explicitly to force-skip the worst
    benchmark drawdown scenario regardless of what is on disk.
    """
    _enforce_schema(returns_daily, RETURNS_DAILY_COLUMNS, "returns_daily")
    _enforce_schema(returns_monthly, RETURNS_MONTHLY_COLUMNS, "returns_monthly")

    if portfolio_weights is None:
        portfolio_weights = _load_portfolio_weights()
    _enforce_schema(portfolio_weights, PORTFOLIO_WEIGHTS_COLUMNS, "portfolio_weights")

    daily = returns_daily.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    monthly = returns_monthly.copy()
    monthly["month_end_date"] = pd.to_datetime(monthly["month_end_date"])

    weights = portfolio_weights.set_index("fund_label")["weight"]
    fund_labels = list(weights.index)

    scenario_frames: List[pd.DataFrame] = []

    def _finalize(rows: pd.DataFrame, scenario_name: str, window_start, window_end, rationale: str) -> None:
        rows = rows.copy()
        rows["scenario_type"] = SCENARIO_TYPE_HISTORICAL
        rows["scenario_name"] = scenario_name
        rows["window_start"] = window_start
        rows["window_end"] = window_end
        rows["rationale"] = rationale
        scenario_frames.append(rows)

    # --- Worst 1-month portfolio period ---
    monthly_pivot = monthly.pivot_table(index="month_end_date", columns="fund_label", values="monthly_return")
    portfolio_monthly = _portfolio_weighted_series(monthly_pivot, weights)
    if not portfolio_monthly.empty:
        worst_month_end = portfolio_monthly.idxmin()
        window_start = worst_month_end.replace(day=1)
        rows = _build_fund_rows_for_window(fund_labels, daily, monthly, window_start, worst_month_end, use_daily=False)
        _finalize(
            rows,
            "Worst 1-Month Portfolio Period",
            window_start,
            worst_month_end,
            "Actual calendar month with the lowest portfolio-weighted monthly return "
            f"({portfolio_monthly.loc[worst_month_end]:.2%}), using default portfolio_weights.csv.",
        )
    else:
        warnings.warn("Could not compute a portfolio monthly series; skipping worst 1-month scenario.")

    # --- Worst 3-month portfolio period ---
    if len(portfolio_monthly) >= ROLLING_3M_WINDOW_MONTHS:
        rolling_3m = (
            (1.0 + portfolio_monthly)
            .rolling(window=ROLLING_3M_WINDOW_MONTHS, min_periods=ROLLING_3M_WINDOW_MONTHS)
            .apply(lambda values: values.prod(), raw=True)
            - 1.0
        ).dropna()
        if not rolling_3m.empty:
            worst_end = rolling_3m.idxmin()
            end_pos = portfolio_monthly.index.get_loc(worst_end)
            start_pos = end_pos - ROLLING_3M_WINDOW_MONTHS + 1
            window_end = portfolio_monthly.index[end_pos]
            window_start = portfolio_monthly.index[start_pos].replace(day=1)
            rows = _build_fund_rows_for_window(fund_labels, daily, monthly, window_start, window_end, use_daily=False)
            _finalize(
                rows,
                "Worst 3-Month Portfolio Period",
                window_start,
                window_end,
                "Rolling 3-calendar-month window with the lowest compounded portfolio-weighted "
                f"return ({rolling_3m.loc[worst_end]:.2%}).",
            )
    else:
        warnings.warn("Insufficient monthly history (<3 months) for worst 3-month scenario; skipped.")

    # --- Worst 20-trading-day portfolio period ---
    daily_pivot = daily.pivot_table(index="date", columns="fund_label", values="daily_return")
    portfolio_daily = _portfolio_weighted_series(daily_pivot, weights)
    if len(portfolio_daily) >= ROLLING_20D_WINDOW_DAYS:
        rolling_20d = (
            (1.0 + portfolio_daily)
            .rolling(window=ROLLING_20D_WINDOW_DAYS, min_periods=ROLLING_20D_WINDOW_DAYS)
            .apply(lambda values: values.prod(), raw=True)
            - 1.0
        ).dropna()
        if not rolling_20d.empty:
            worst_end = rolling_20d.idxmin()
            end_pos = portfolio_daily.index.get_loc(worst_end)
            start_pos = end_pos - ROLLING_20D_WINDOW_DAYS + 1
            window_end = portfolio_daily.index[end_pos]
            window_start = portfolio_daily.index[start_pos]
            rows = _build_fund_rows_for_window(fund_labels, daily, monthly, window_start, window_end, use_daily=True)
            _finalize(
                rows,
                "Worst 20-Trading-Day Portfolio Period",
                window_start,
                window_end,
                "Rolling 20-trading-day window with the lowest compounded portfolio-weighted "
                f"return ({rolling_20d.loc[worst_end]:.2%}).",
            )
    else:
        warnings.warn("Insufficient daily history (<20 trading days) for worst 20-trading-day scenario; skipped.")

    # --- Worst small-cap fund period ---
    try:
        small_cap_fund = _identify_small_cap_fund(fund_labels)
        small_cap_series = (
            monthly[monthly["fund_label"] == small_cap_fund]
            .set_index("month_end_date")["monthly_return"]
            .dropna()
        )
        if not small_cap_series.empty:
            worst_month_end = small_cap_series.idxmin()
            window_start = worst_month_end.replace(day=1)
            rows = _build_fund_rows_for_window(fund_labels, daily, monthly, window_start, worst_month_end, use_daily=False)
            _finalize(
                rows,
                "Worst Small-Cap Fund Period",
                window_start,
                worst_month_end,
                f"Calendar month of '{small_cap_fund}''s own worst historical monthly return "
                f"({small_cap_series.loc[worst_month_end]:.2%}); all portfolio funds' actual returns "
                "shown for the same window.",
            )
    except DataValidationError as exc:
        warnings.warn(f"Skipping worst small-cap fund scenario: {exc}")

    # --- Worst benchmark drawdown period (if benchmark data exists) ---
    if benchmark_daily is _UNSET:
        benchmark_daily = _load_benchmark_daily()
    if benchmark_daily is not None and not benchmark_daily.empty:
        try:
            peak_date, trough_date, drawdown_magnitude, benchmark_label = _worst_benchmark_drawdown_window(
                benchmark_daily
            )
            rows = _build_fund_rows_for_window(fund_labels, daily, monthly, peak_date, trough_date, use_daily=True)
            _finalize(
                rows,
                "Worst Benchmark Drawdown Period",
                peak_date,
                trough_date,
                f"Peak-to-trough window of {benchmark_label}'s largest historical drawdown "
                f"({drawdown_magnitude:.2%}); all portfolio funds' actual returns shown for the same window.",
            )
        except DataValidationError as exc:
            warnings.warn(f"Skipping worst benchmark drawdown scenario: {exc}")
    else:
        warnings.warn("No benchmark data available; skipping worst benchmark drawdown scenario.")

    if not scenario_frames:
        raise DataValidationError("No historical replay scenarios could be computed from the provided data.")

    result = pd.concat(scenario_frames, ignore_index=True)
    result["window_start"] = pd.to_datetime(result["window_start"])
    result["window_end"] = pd.to_datetime(result["window_end"])
    return result[STRESS_RESULTS_COLUMNS]


# ---------------------------------------------------------------------------
# B. Deterministic stress
# ---------------------------------------------------------------------------

def run_deterministic_stress(stress_scenarios: pd.DataFrame) -> pd.DataFrame:
    """Apply fixed illustrative shocks from stress_scenarios.csv per fund."""
    if "scenario" not in stress_scenarios.columns:
        raise DataValidationError("stress_scenarios.csv is missing required column: scenario")

    id_vars = [column for column in ["scenario", "rationale"] if column in stress_scenarios.columns]
    fund_columns = [column for column in stress_scenarios.columns if column not in id_vars]
    if not fund_columns:
        raise DataValidationError("stress_scenarios.csv has no fund-level shock columns.")

    melted = stress_scenarios.melt(
        id_vars=id_vars,
        value_vars=fund_columns,
        var_name="fund_label",
        value_name="stress_return",
    )
    melted = melted.rename(columns={"scenario": "scenario_name"})
    melted["scenario_type"] = SCENARIO_TYPE_DETERMINISTIC
    melted["window_start"] = pd.NaT
    melted["window_end"] = pd.NaT

    if "rationale" in melted.columns:
        base_rationale = melted["rationale"].fillna("").astype(str).str.rstrip(". ")
        melted["rationale"] = base_rationale.where(base_rationale == "", base_rationale + ". ") + DETERMINISTIC_DISCLOSURE
    else:
        melted["rationale"] = DETERMINISTIC_DISCLOSURE

    return melted[STRESS_RESULTS_COLUMNS]


# ---------------------------------------------------------------------------
# C. Interactive custom shock
# ---------------------------------------------------------------------------

def run_custom_shock(
    fund_shocks: Dict[str, float],
    portfolio_weights: Dict[str, float],
    base_portfolio_value: float = DEFAULT_BASE_PORTFOLIO_VALUE,
    scenario_name: str = "Custom Shock",
) -> pd.DataFrame:
    """
    Interactive custom shock function for Streamlit sliders. Accepts
    user-defined fund-level shocks (e.g. {"ICICI Bluechip": -0.12, ...}),
    portfolio weights, and a base portfolio value, and returns the full
    live attribution table (fund_weight, fund_loss_contribution,
    stress_loss_share, loss_amount_inr, post_stress_portfolio_value, ...).

    Nothing here is persisted to stress_results.csv — that file only holds
    the HISTORICAL_REPLAY and DETERMINISTIC scenarios; custom slider shocks
    are session-only, recomputed live as the user moves sliders.
    """
    if not fund_shocks:
        raise DataValidationError("fund_shocks must contain at least one fund_label -> shock mapping.")
    if not portfolio_weights:
        raise DataValidationError("portfolio_weights must contain at least one fund_label -> weight mapping.")

    stress_rows = pd.DataFrame(
        {
            "scenario_type": SCENARIO_TYPE_CUSTOM,
            "scenario_name": scenario_name,
            "fund_label": list(fund_shocks.keys()),
            "stress_return": list(fund_shocks.values()),
            "window_start": pd.NaT,
            "window_end": pd.NaT,
            "rationale": CUSTOM_DISCLOSURE,
        }
    )[STRESS_RESULTS_COLUMNS]

    weights_df = pd.DataFrame(
        {
            "fund_label": list(portfolio_weights.keys()),
            "weight": list(portfolio_weights.values()),
        }
    )

    from attribution import calculate_attribution  # local import: avoids a hard import-time coupling

    return calculate_attribution(stress_rows, weights_df, base_portfolio_value=base_portfolio_value)


# ---------------------------------------------------------------------------
# Assembly / orchestration
# ---------------------------------------------------------------------------

def generate_stress_results(
    returns_daily: pd.DataFrame,
    returns_monthly: pd.DataFrame,
    stress_scenarios: pd.DataFrame,
    portfolio_weights: Optional[pd.DataFrame] = None,
    benchmark_daily: Optional[pd.DataFrame] = _UNSET,
) -> pd.DataFrame:
    """Assemble 02_processed_data/stress_results.csv per data_dictionary.md §4.11
    (historical replay + deterministic scenarios; custom shocks are session-only,
    see run_custom_shock)."""
    _enforce_schema(returns_daily, RETURNS_DAILY_COLUMNS, "returns_daily")
    _enforce_schema(returns_monthly, RETURNS_MONTHLY_COLUMNS, "returns_monthly")

    if portfolio_weights is None:
        portfolio_weights = _load_portfolio_weights()

    historical = run_historical_replay(
        returns_daily, returns_monthly, portfolio_weights=portfolio_weights, benchmark_daily=benchmark_daily
    )
    deterministic = run_deterministic_stress(stress_scenarios)

    combined = pd.concat([historical, deterministic], ignore_index=True)
    return combined[STRESS_RESULTS_COLUMNS]


def _load_returns_daily() -> pd.DataFrame:
    if not RETURNS_DAILY_PATH.exists():
        raise DataValidationError(
            f"{RETURNS_DAILY_PATH} does not exist. Run the return engine "
            "(returns.run_return_engine()) before running the stress engine."
        )
    return pd.read_csv(RETURNS_DAILY_PATH)


def _load_returns_monthly() -> pd.DataFrame:
    if not RETURNS_MONTHLY_PATH.exists():
        raise DataValidationError(
            f"{RETURNS_MONTHLY_PATH} does not exist. Run the return engine "
            "(returns.run_return_engine()) before running the stress engine."
        )
    return pd.read_csv(RETURNS_MONTHLY_PATH)


def run_stress_engine() -> pd.DataFrame:
    """
    Full entry point: load returns_daily.csv, returns_monthly.csv,
    portfolio_weights.csv, stress_scenarios.csv (and benchmark_daily.csv if
    present), compute historical + deterministic stress scenarios, and
    write 02_processed_data/stress_results.csv.
    """
    returns_daily = _load_returns_daily()
    returns_monthly = _load_returns_monthly()
    portfolio_weights = _load_portfolio_weights()
    stress_scenarios = _load_stress_scenarios()
    benchmark_daily = _load_benchmark_daily()

    result = generate_stress_results(
        returns_daily,
        returns_monthly,
        stress_scenarios,
        portfolio_weights=portfolio_weights,
        benchmark_daily=benchmark_daily,
    )

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output = result.copy()
    output["window_start"] = pd.to_datetime(output["window_start"]).dt.strftime("%Y-%m-%d")
    output["window_end"] = pd.to_datetime(output["window_end"]).dt.strftime("%Y-%m-%d")
    output.to_csv(STRESS_RESULTS_PATH, index=False)

    return result
