"""
Refresh Data Script — manual entry point for the API-first data pipeline.

Reference: 00_project_control/master_project_instructions.md.md §13 (Refresh
Script) and 00_project_control/implementation_plan.md.

Run manually:
    python 04_streamlit_app/refresh_data.py

Non-negotiable rule (see model_governance.md): this script is the only place
in the project allowed to trigger live data fetches. The Streamlit app must
never call this pipeline on page load — it only reads processed CSVs from
02_processed_data/.

Current stage (Phase 2 API fetch + Phase 3 validation + Phase 4 returns +
Phase 5 metrics/rolling metrics + Phase 6 benchmark analytics + Phase 7
stress/attribution):
    1. fetch_all_mutual_funds()   -> 02_processed_data/nav_daily_clean.csv
    2. fetch_all_benchmarks()     -> 02_processed_data/benchmark_daily.csv
    3. run_data_validation()      -> 02_processed_data/data_quality_report.csv
    4. run_return_engine()        -> 02_processed_data/returns_daily.csv
                                      02_processed_data/nav_monthly.csv
                                      02_processed_data/returns_monthly.csv
                                      02_processed_data/benchmark_monthly.csv
    5. run_metrics_engine()       -> 02_processed_data/metrics_summary.csv
    6. run_rolling_metrics_engine() -> 02_processed_data/rolling_metrics.csv
    7. run_benchmarks_engine()    -> 02_processed_data/benchmark_metrics.csv
                                      02_processed_data/rolling_benchmark_metrics.csv
    8. run_stress_engine()        -> 02_processed_data/stress_results.csv
    9. run_attribution_engine()   -> 02_processed_data/attribution_results.csv

Later phases (suitability wiring, Excel export) will be appended to this
script incrementally as each module is implemented — see
00_project_control/implementation_plan.md for the full sequence.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "04_streamlit_app" / "src"
sys.path.insert(0, str(SRC_DIR))

from api_fetch import (  # noqa: E402 - sys.path must be configured before this import
    BENCHMARK_DAILY_PATH,
    NAV_DAILY_CLEAN_PATH,
    DataFetchError,
    fetch_all_benchmarks,
    fetch_all_mutual_funds,
)
from data_cleaning import (  # noqa: E402 - sys.path must be configured before this import
    DATA_QUALITY_REPORT_PATH,
    run_data_validation,
)
from returns import (  # noqa: E402 - sys.path must be configured before this import
    BENCHMARK_MONTHLY_PATH,
    NAV_MONTHLY_PATH,
    RETURNS_DAILY_PATH,
    RETURNS_MONTHLY_PATH,
    run_return_engine,
)
from metrics import (  # noqa: E402 - sys.path must be configured before this import
    METRICS_SUMMARY_PATH,
    run_metrics_engine,
)
from rolling_metrics import (  # noqa: E402 - sys.path must be configured before this import
    ROLLING_METRICS_PATH,
    run_rolling_metrics_engine,
)
from benchmarks import (  # noqa: E402 - sys.path must be configured before this import
    BENCHMARK_METRICS_PATH,
    ROLLING_BENCHMARK_METRICS_PATH,
    run_benchmarks_engine,
)
from stress import (  # noqa: E402 - sys.path must be configured before this import
    STRESS_RESULTS_PATH,
    run_stress_engine,
)
from attribution import (  # noqa: E402 - sys.path must be configured before this import
    ATTRIBUTION_RESULTS_PATH,
    run_attribution_engine,
)


def _print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def refresh_mutual_funds() -> bool:
    """Step 1: fetch all included funds' NAV history and write nav_daily_clean.csv."""
    _print_header("STEP 1/9 - Fetching mutual fund NAV data (MFAPI)")
    try:
        nav_df = fetch_all_mutual_funds()
    except PermissionError as exc:
        print(f"[FAILED] Mutual fund NAV fetch failed: {type(exc).__name__}: {exc}")
        print("         Hint: close any app using nav_daily_clean.csv (Excel, Power BI, editor preview) and retry.")
        return False
    except Exception as exc:  # noqa: BLE001 - top-level orchestrator must report, not crash silently
        print(f"[FAILED] Mutual fund NAV fetch failed: {type(exc).__name__}: {exc}")
        return False

    fund_count = nav_df["fund_label"].nunique()
    row_count = len(nav_df)
    print(f"[SUCCESS] Fetched NAV data for {fund_count} fund(s), {row_count} total observations.")
    print(f"[SUCCESS] Wrote {NAV_DAILY_CLEAN_PATH}")

    quality_counts = nav_df["source_quality"].value_counts().to_dict()
    print(f"          source_quality breakdown: {quality_counts}")
    return True


def refresh_benchmarks() -> bool:
    """Step 2: fetch all required benchmarks, build HYBRID_65_35, write benchmark_daily.csv."""
    _print_header("STEP 2/9 - Fetching benchmark/index data")
    try:
        # Explicitly opt in to yfinance price-index proxy fallback in the
        # refresh pipeline when TRI endpoints are unavailable.
        benchmark_df = fetch_all_benchmarks(allow_yfinance_fallback=True)
    except DataFetchError as exc:
        print(f"[FAILED] Benchmark fetch failed: {type(exc).__name__}: {exc}")
        print("         Hint: TRI source fetch failed and no benchmark cache was available.")
        print("               Retry later/network-on, or populate benchmark cache first.")
        return False
    except Exception as exc:  # noqa: BLE001 - top-level orchestrator must report, not crash silently
        print(f"[FAILED] Benchmark fetch failed: {type(exc).__name__}: {exc}")
        return False

    benchmark_count = benchmark_df["benchmark_label"].nunique()
    row_count = len(benchmark_df)
    print(f"[SUCCESS] Fetched {benchmark_count} benchmark series, {row_count} total observations.")
    print(f"[SUCCESS] Wrote {BENCHMARK_DAILY_PATH}")

    quality_counts = benchmark_df["source_quality"].value_counts().to_dict()
    print(f"          source_quality breakdown: {quality_counts}")

    proxy_labels = (
        benchmark_df.loc[benchmark_df["source_quality"] == "PRICE_INDEX_PROXY_NOT_TRI", "benchmark_label"]
        .unique()
        .tolist()
    )
    if proxy_labels:
        print(
            f"[WARNING] The following benchmarks are price-index proxies, NOT official TRI series: "
            f"{proxy_labels}"
        )
    return True


def refresh_data_validation() -> bool:
    """
    Step 3: validate nav_daily_clean.csv and benchmark_daily.csv, write
    data_quality_report.csv from the raw pre-clean data, then overwrite
    both nav_daily_clean.csv and benchmark_daily.csv in place with the
    validated/deduplicated/2021-01-01+-filtered result (see
    data_cleaning.py, Phase 3). Runs against whatever processed files are
    currently on disk, so it still reports accurately even if a fetch step
    above failed but earlier cached output files remain in place.
    """
    _print_header("STEP 3/9 - Validating processed data and writing data_quality_report.csv")
    try:
        results = run_data_validation()
    except Exception as exc:  # noqa: BLE001 - top-level orchestrator must report, not crash silently
        print(f"[FAILED] Data validation failed: {type(exc).__name__}: {exc}")
        return False

    report = results["data_quality_report"]
    status_counts = report["status"].value_counts().to_dict()
    print(f"[SUCCESS] Wrote {DATA_QUALITY_REPORT_PATH}")
    print(f"          {len(report)} fund(s)/benchmark(s) assessed. status breakdown: {status_counts}")
    print(
        f"          Overwrote nav_daily_clean.csv ({len(results['nav_daily_clean'])} rows) and "
        f"benchmark_daily.csv ({len(results['benchmark_daily'])} rows) with the validated/cleaned result."
    )

    fail_rows = report[report["status"] == "FAIL"]
    if not fail_rows.empty:
        print("[WARNING] FAIL status - do not proceed to publication for these entities:")
        for _, row in fail_rows.iterrows():
            print(f"          - {row['fund_label_or_benchmark_label']} ({row['asset_type']})")

    warning_rows = report[report["status"] == "WARNING"]
    if not warning_rows.empty:
        print("[INFO] WARNING status - usable but flagged, see data_quality_report.csv for detail:")
        for _, row in warning_rows.iterrows():
            print(f"          - {row['fund_label_or_benchmark_label']} ({row['asset_type']})")

    return True


def refresh_returns() -> bool:
    """
    Step 4: run the return engine (see returns.py, Phase 4) and write
    returns_daily.csv, nav_monthly.csv, returns_monthly.csv, and
    benchmark_monthly.csv. Only runs after data validation has succeeded,
    since it reuses data_cleaning's validated/deduplicated/date-filtered
    NAV and benchmark data as its input.
    """
    _print_header("STEP 4/9 - Calculating returns (daily + monthly, fund + benchmark)")
    try:
        results = run_return_engine()
    except Exception as exc:  # noqa: BLE001 - top-level orchestrator must report, not crash silently
        print(f"[FAILED] Return engine failed: {type(exc).__name__}: {exc}")
        return False

    returns_daily = results["returns_daily"]
    returns_monthly = results["returns_monthly"]
    benchmark_monthly = results["benchmark_monthly"]

    print(f"[SUCCESS] Wrote {RETURNS_DAILY_PATH} ({len(returns_daily)} rows, "
          f"{returns_daily['fund_label'].nunique()} fund(s))")
    print(f"[SUCCESS] Wrote {NAV_MONTHLY_PATH}")
    print(f"[SUCCESS] Wrote {RETURNS_MONTHLY_PATH} ({len(returns_monthly)} rows)")
    print(f"[SUCCESS] Wrote {BENCHMARK_MONTHLY_PATH} ({len(benchmark_monthly)} rows, "
          f"{benchmark_monthly['benchmark_label'].nunique()} benchmark(s))")
    return True


def refresh_metrics() -> bool:
    """
    Step 5: run the metrics engine (see metrics.py, Phase 5) and write
    metrics_summary.csv. Only runs after the return engine has succeeded,
    since it reuses returns_daily.csv / returns_monthly.csv as input.
    """
    _print_header("STEP 5/9 - Calculating fund-level metrics (CAGR, volatility, Sharpe, drawdown, VaR/CVaR, ...)")
    try:
        summary = run_metrics_engine()
    except Exception as exc:  # noqa: BLE001 - top-level orchestrator must report, not crash silently
        print(f"[FAILED] Metrics engine failed: {type(exc).__name__}: {exc}")
        return False

    print(f"[SUCCESS] Wrote {METRICS_SUMMARY_PATH} ({len(summary)} fund(s))")
    return True


def refresh_rolling_metrics() -> bool:
    """
    Step 6: run the rolling metrics engine (see rolling_metrics.py, Phase 5)
    and write rolling_metrics.csv (long form). Only runs after the return
    engine has succeeded, since it reuses returns_daily.csv /
    returns_monthly.csv as input.
    """
    _print_header("STEP 6/9 - Calculating rolling metrics (rolling returns, volatility, Sharpe)")
    try:
        rolling = run_rolling_metrics_engine()
    except Exception as exc:  # noqa: BLE001 - top-level orchestrator must report, not crash silently
        print(f"[FAILED] Rolling metrics engine failed: {type(exc).__name__}: {exc}")
        return False

    print(f"[SUCCESS] Wrote {ROLLING_METRICS_PATH} ({len(rolling)} rows, "
          f"{rolling['fund_label'].nunique()} fund(s), {rolling['metric_name'].nunique()} metric(s))")
    return True


def refresh_benchmark_analytics() -> bool:
    """
    Step 7: run the benchmark analytics engine (see benchmarks.py, Phase 6)
    and write benchmark_metrics.csv + rolling_benchmark_metrics.csv. Only
    runs after the return engine has succeeded, since it reuses
    returns_daily.csv (plus benchmark_daily.csv and benchmark_map.csv) as
    input. Each fund is matched to its own primary benchmark only.
    """
    _print_header("STEP 7/9 - Calculating benchmark-relative analytics (excess return, beta, tracking error, IR, capture)")
    try:
        results = run_benchmarks_engine()
    except Exception as exc:  # noqa: BLE001 - top-level orchestrator must report, not crash silently
        print(f"[FAILED] Benchmark analytics engine failed: {type(exc).__name__}: {exc}")
        return False

    benchmark_metrics = results["benchmark_metrics"]
    rolling_benchmark_metrics = results["rolling_benchmark_metrics"]
    print(f"[SUCCESS] Wrote {BENCHMARK_METRICS_PATH} ({len(benchmark_metrics)} fund(s))")
    print(f"[SUCCESS] Wrote {ROLLING_BENCHMARK_METRICS_PATH} ({len(rolling_benchmark_metrics)} rows, "
          f"{rolling_benchmark_metrics['fund_label'].nunique()} fund(s))")
    return True


def refresh_stress() -> bool:
    """
    Step 8: run the stress engine (see stress.py, Phase 7) - historical
    replay + deterministic scenarios - and write stress_results.csv. Only
    runs after the return engine has succeeded, since it reuses
    returns_daily.csv / returns_monthly.csv as input.
    """
    _print_header("STEP 8/9 - Running stress engine (historical replay + deterministic scenarios)")
    try:
        results = run_stress_engine()
    except Exception as exc:  # noqa: BLE001 - top-level orchestrator must report, not crash silently
        print(f"[FAILED] Stress engine failed: {type(exc).__name__}: {exc}")
        return False

    scenario_counts = results.groupby("scenario_type")["scenario_name"].nunique().to_dict()
    print(f"[SUCCESS] Wrote {STRESS_RESULTS_PATH} ({len(results)} rows, scenario counts by type: {scenario_counts})")
    return True


def refresh_attribution() -> bool:
    """
    Step 9: run the attribution engine (see attribution.py, Phase 7) and
    write attribution_results.csv. Only runs after the stress engine has
    succeeded, since it reuses stress_results.csv as input.
    """
    _print_header("STEP 9/9 - Running attribution engine (allocation weight vs stress loss share)")
    try:
        results = run_attribution_engine()
    except Exception as exc:  # noqa: BLE001 - top-level orchestrator must report, not crash silently
        print(f"[FAILED] Attribution engine failed: {type(exc).__name__}: {exc}")
        return False

    print(f"[SUCCESS] Wrote {ATTRIBUTION_RESULTS_PATH} ({len(results)} rows)")

    largest_contributors = results[results["is_largest_loss_contributor"]]
    if not largest_contributors.empty:
        print("[INFO] Largest loss contributor by scenario (allocation weight vs stress loss share):")
        for _, row in largest_contributors.iterrows():
            print(
                f"          - {row['scenario_name']}: {row['fund_label']} "
                f"(weight {row['fund_weight']:.1%}, stress loss share {row['stress_loss_share']:.1%})"
            )
    return True


def main() -> int:
    _print_header("MF Risk Diagnostic Module - Data Refresh (API-First Pipeline)")
    print("This script fetches, caches, and validates data. It must never run inside Streamlit.")

    mutual_funds_ok = refresh_mutual_funds()
    benchmarks_ok = refresh_benchmarks()
    validation_ok = False
    validation_skipped = False
    if mutual_funds_ok and benchmarks_ok:
        validation_ok = refresh_data_validation()
    else:
        validation_skipped = True
        _print_header("STEP 3/8 - Validating processed data and writing data_quality_report.csv")
        print("[SKIPPED] Data validation skipped because earlier fetch step(s) failed.")
        print("          Validation requires both nav_daily_clean.csv and benchmark_daily.csv.")

    returns_ok = False
    returns_skipped = False
    if validation_ok:
        returns_ok = refresh_returns()
    else:
        returns_skipped = True
        _print_header("STEP 4/8 - Calculating returns (daily + monthly, fund + benchmark)")
        print("[SKIPPED] Return engine skipped because data validation did not succeed.")

    metrics_ok = False
    metrics_skipped = False
    rolling_metrics_ok = False
    rolling_metrics_skipped = False
    benchmark_analytics_ok = False
    benchmark_analytics_skipped = False
    stress_ok = False
    stress_skipped = False
    if returns_ok:
        metrics_ok = refresh_metrics()
        rolling_metrics_ok = refresh_rolling_metrics()
        benchmark_analytics_ok = refresh_benchmark_analytics()
        stress_ok = refresh_stress()
    else:
        metrics_skipped = True
        rolling_metrics_skipped = True
        benchmark_analytics_skipped = True
        stress_skipped = True
        _print_header("STEP 5/9 - Calculating fund-level metrics (CAGR, volatility, Sharpe, drawdown, VaR/CVaR, ...)")
        print("[SKIPPED] Metrics engine skipped because the return engine did not succeed.")
        _print_header("STEP 6/9 - Calculating rolling metrics (rolling returns, volatility, Sharpe)")
        print("[SKIPPED] Rolling metrics engine skipped because the return engine did not succeed.")
        _print_header("STEP 7/9 - Calculating benchmark-relative analytics (excess return, beta, tracking error, IR, capture)")
        print("[SKIPPED] Benchmark analytics engine skipped because the return engine did not succeed.")
        _print_header("STEP 8/9 - Running stress engine (historical replay + deterministic scenarios)")
        print("[SKIPPED] Stress engine skipped because the return engine did not succeed.")

    attribution_ok = False
    attribution_skipped = False
    if stress_ok:
        attribution_ok = refresh_attribution()
    else:
        attribution_skipped = True
        _print_header("STEP 9/9 - Running attribution engine (allocation weight vs stress loss share)")
        print("[SKIPPED] Attribution engine skipped because the stress engine did not succeed.")

    _print_header("REFRESH SUMMARY")
    print(f"Mutual fund NAV data : {'SUCCESS' if mutual_funds_ok else 'FAILED'}")
    print(f"Benchmark data       : {'SUCCESS' if benchmarks_ok else 'FAILED'}")
    if validation_skipped:
        print("Data validation      : SKIPPED (fetch prerequisite failed)")
    else:
        print(f"Data validation      : {'SUCCESS' if validation_ok else 'FAILED'}")
    if returns_skipped:
        print("Return engine        : SKIPPED (validation prerequisite failed)")
    else:
        print(f"Return engine        : {'SUCCESS' if returns_ok else 'FAILED'}")
    if metrics_skipped:
        print("Metrics engine       : SKIPPED (return engine prerequisite failed)")
    else:
        print(f"Metrics engine       : {'SUCCESS' if metrics_ok else 'FAILED'}")
    if rolling_metrics_skipped:
        print("Rolling metrics      : SKIPPED (return engine prerequisite failed)")
    else:
        print(f"Rolling metrics      : {'SUCCESS' if rolling_metrics_ok else 'FAILED'}")
    if benchmark_analytics_skipped:
        print("Benchmark analytics  : SKIPPED (return engine prerequisite failed)")
    else:
        print(f"Benchmark analytics  : {'SUCCESS' if benchmark_analytics_ok else 'FAILED'}")
    if stress_skipped:
        print("Stress engine        : SKIPPED (return engine prerequisite failed)")
    else:
        print(f"Stress engine        : {'SUCCESS' if stress_ok else 'FAILED'}")
    if attribution_skipped:
        print("Attribution engine   : SKIPPED (stress engine prerequisite failed)")
    else:
        print(f"Attribution engine   : {'SUCCESS' if attribution_ok else 'FAILED'}")

    all_ok = (
        mutual_funds_ok
        and benchmarks_ok
        and validation_ok
        and returns_ok
        and metrics_ok
        and rolling_metrics_ok
        and benchmark_analytics_ok
        and stress_ok
        and attribution_ok
    )
    if all_ok:
        print("\nPhase 2 + Phase 3 + Phase 4 + Phase 5 + Phase 6 + Phase 7 pipeline steps completed successfully.")
        print("Check data_quality_report.csv above for any FAIL/WARNING entities before proceeding.")
        print("Not yet implemented in this script: suitability.")
        return 0

    print("\nOne or more pipeline steps failed. Resolve the errors above before proceeding.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
