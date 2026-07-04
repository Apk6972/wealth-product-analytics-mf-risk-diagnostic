"""
Data Cleaning / Validation Module.

API-first version: this module validates the already-fetched, already-cached
processed files produced by api_fetch.py. It never reads manual AMFI or NSE
files, and it never fetches data itself.

Reference: 00_project_control/master_project_instructions.md.md §15 (Data
Cleaning Module) and §14 (Data Quality Report).
Related: 00_project_control/data_dictionary.md (processed schemas),
00_project_control/model_governance.md (PASS/WARNING/FAIL publication gate).

Responsibilities:
1. Validate 02_processed_data/nav_daily_clean.csv
2. Validate 02_processed_data/benchmark_daily.csv
3. Enforce schema, convert dates, remove duplicates, enforce the
   2021-01-01 data horizon.
4. Generate 02_processed_data/data_quality_report.csv from the RAW
   (pre-clean) data, so the report reflects what the fetch/cache layer
   actually produced.
5. Overwrite 02_processed_data/nav_daily_clean.csv and
   02_processed_data/benchmark_daily.csv in place with the validated,
   deduplicated, 2021-01-01+-filtered result, so those two files match
   their documented contract (data_dictionary.md §4.1/§4.2) for every
   downstream consumer.

This module does not implement CAGR, volatility, Sharpe, drawdown, or any
other analytical metric (see metrics.py, Phase 5). The only calculation
performed here is a simple day-over-day percent change used purely to flag
suspicious (> +10% / < -10%) observations as a data-quality signal — it is
not the official return series and is never written to a processed file.

Status rules (PASS / WARNING / FAIL) are this module's own documented
interpretation of the master spec's requirement for a status column; the
spec defines the required checks and the three enum values but not exact
thresholds. See _determine_status() for the precise rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = _THIS_FILE.parents[2]  # .../src -> .../04_streamlit_app -> project root

PROCESSED_DATA_DIR = PROJECT_ROOT / "02_processed_data"
NAV_DAILY_CLEAN_PATH = PROCESSED_DATA_DIR / "nav_daily_clean.csv"
BENCHMARK_DAILY_PATH = PROCESSED_DATA_DIR / "benchmark_daily.csv"
DATA_QUALITY_REPORT_PATH = PROCESSED_DATA_DIR / "data_quality_report.csv"

FUND_MASTER_PATH = PROJECT_ROOT / "01_raw_data" / "scheme_master" / "fund_master.csv"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_START_DATE = pd.Timestamp("2021-01-01")
SUSPICIOUS_RETURN_THRESHOLD = 0.10  # +/- 10%

NAV_SCHEMA_COLUMNS = ["date", "fund_label", "scheme_code", "scheme_name", "nav", "source", "source_quality"]
BENCHMARK_SCHEMA_COLUMNS = ["date", "benchmark_label", "tri_value", "source", "source_quality"]

DATA_QUALITY_REPORT_COLUMNS = [
    "fund_label_or_benchmark_label",
    "asset_type",
    "source",
    "source_quality",
    "first_date",
    "last_date",
    "observation_count",
    "missing_value_count",
    "duplicate_date_count",
    "suspicious_return_count_gt_10pct",
    "suspicious_return_count_lt_minus_10pct",
    "metadata_verification_status",
    "status",
]

ASSET_TYPE_FUND = "FUND"
ASSET_TYPE_BENCHMARK = "BENCHMARK"

STATUS_PASS = "PASS"
STATUS_WARNING = "WARNING"
STATUS_FAIL = "FAIL"

NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN_FUND_LABEL = "UNKNOWN_FUND_LABEL_NOT_IN_FUND_MASTER"

VERIFICATION_STATUS_NEEDS_VERIFICATION = "NEEDS_API_METADATA_VERIFICATION"
VERIFICATION_STATUS_FAILED = "FAILED_METADATA_CHECK"

# source_quality values that represent a known, disclosed degradation:
# still usable, but not a clean top-quality fetch, and worth flagging.
DEGRADED_SOURCE_QUALITIES = {
    "CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE",
    "API_FETCHED_METADATA_WARNING",
    "PRICE_INDEX_PROXY_NOT_TRI",
    "DISCLOSED_APPROXIMATION",
}


class DataValidationError(Exception):
    """Raised when a processed input file fails schema validation."""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_nav_daily_clean(path: Path = NAV_DAILY_CLEAN_PATH) -> pd.DataFrame:
    """
    Load 02_processed_data/nav_daily_clean.csv as produced by
    api_fetch.fetch_all_mutual_funds(). Never reads a manual file.
    """
    if not path.exists():
        raise DataValidationError(
            f"{path} does not exist. Run the API fetch pipeline "
            "(api_fetch.fetch_all_mutual_funds()) before validating."
        )
    return pd.read_csv(path)


def load_benchmark_daily(path: Path = BENCHMARK_DAILY_PATH) -> pd.DataFrame:
    """
    Load 02_processed_data/benchmark_daily.csv as produced by
    api_fetch.fetch_all_benchmarks(). Never reads a manual file.
    """
    if not path.exists():
        raise DataValidationError(
            f"{path} does not exist. Run the API fetch pipeline "
            "(api_fetch.fetch_all_benchmarks()) before validating."
        )
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Schema enforcement
# ---------------------------------------------------------------------------

def _enforce_schema(df: pd.DataFrame, required_columns: List[str], label: str) -> None:
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise DataValidationError(f"{label} is missing required columns: {missing}")


# ---------------------------------------------------------------------------
# Fund NAV validation / cleaning
# ---------------------------------------------------------------------------

def validate_nav_daily(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate and clean nav_daily_clean.csv:
    - enforce schema
    - convert `date` to datetime (unparseable dates become NaT and are dropped)
    - remove duplicate (fund_label, date) rows, keeping the last occurrence
    - enforce date >= 2021-01-01
    - sort by fund_label, then date

    This is a pure function - it has no file I/O and does not itself
    overwrite nav_daily_clean.csv on disk. run_data_validation() is the
    orchestrator responsible for persisting the cleaned result back to
    nav_daily_clean.csv so that file matches its documented contract
    (data_dictionary.md §4.1: "filtered to date >= 2021-01-01").
    Raises DataValidationError if a required column is missing.
    """
    _enforce_schema(df, NAV_SCHEMA_COLUMNS, "nav_daily_clean.csv")

    cleaned = df.copy()
    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce")
    cleaned = cleaned.dropna(subset=["date"])
    cleaned = cleaned.drop_duplicates(subset=["fund_label", "date"], keep="last")
    cleaned = cleaned[cleaned["date"] >= DATA_START_DATE]
    cleaned = cleaned.sort_values(["fund_label", "date"]).reset_index(drop=True)

    return cleaned[NAV_SCHEMA_COLUMNS]


# ---------------------------------------------------------------------------
# Benchmark validation / cleaning
# ---------------------------------------------------------------------------

def validate_benchmark_daily(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate and clean benchmark_daily.csv:
    - enforce schema
    - convert `date` to datetime (unparseable dates become NaT and are dropped)
    - remove duplicate (benchmark_label, date) rows, keeping the last occurrence
    - enforce date >= 2021-01-01
    - sort by benchmark_label, then date

    This is a pure function - it has no file I/O and does not itself
    overwrite benchmark_daily.csv on disk. run_data_validation() is the
    orchestrator responsible for persisting the cleaned result back to
    benchmark_daily.csv so that file matches its documented contract
    (data_dictionary.md §4.2: "filtered to date >= 2021-01-01").
    Raises DataValidationError if a required column is missing.
    """
    _enforce_schema(df, BENCHMARK_SCHEMA_COLUMNS, "benchmark_daily.csv")

    cleaned = df.copy()
    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce")
    cleaned = cleaned.dropna(subset=["date"])
    cleaned = cleaned.drop_duplicates(subset=["benchmark_label", "date"], keep="last")
    cleaned = cleaned[cleaned["date"] >= DATA_START_DATE]
    cleaned = cleaned.sort_values(["benchmark_label", "date"]).reset_index(drop=True)

    return cleaned[BENCHMARK_SCHEMA_COLUMNS]


# ---------------------------------------------------------------------------
# Fund metadata verification lookup (read-only; scheme_master is config, not
# manual market data)
# ---------------------------------------------------------------------------

def _load_fund_verification_status_map() -> Dict[str, str]:
    """Map fund_label -> verification_status from fund_master.csv, if available."""
    if not FUND_MASTER_PATH.exists():
        return {}
    fund_master = pd.read_csv(FUND_MASTER_PATH)
    if "fund_label" not in fund_master.columns or "verification_status" not in fund_master.columns:
        return {}
    return dict(zip(fund_master["fund_label"], fund_master["verification_status"]))


# ---------------------------------------------------------------------------
# Per-entity quality assessment
# ---------------------------------------------------------------------------

def _assess_entity_quality(raw_group: pd.DataFrame, value_column: str) -> Dict[str, Any]:
    """
    Compute data-quality statistics for one fund_label or benchmark_label
    group, from its RAW (schema-valid, date-converted, but not yet
    deduplicated or date-filtered) rows. Duplicate and missing-value
    counting happens before cleaning so the report reflects what the
    fetch/cache layer actually produced.

    The day-over-day percent change computed here is a data-quality
    diagnostic only (to flag suspicious moves) — it is not the official
    return series produced by returns.py.
    """
    observation_count = len(raw_group)

    invalid_date_count = int(raw_group["date"].isna().sum())
    missing_value_count = int(raw_group[value_column].isna().sum()) + invalid_date_count

    valid_rows = raw_group.dropna(subset=["date"]).sort_values("date")
    first_date = valid_rows["date"].min() if not valid_rows.empty else pd.NaT
    last_date = valid_rows["date"].max() if not valid_rows.empty else pd.NaT
    duplicate_date_count = int(valid_rows["date"].duplicated(keep=False).sum())

    # De-duplicate purely for the suspicious-return scan so a duplicated
    # date doesn't produce a spurious near-zero "return" between identical rows.
    dedup_for_scan = valid_rows.drop_duplicates(subset=["date"], keep="last")
    daily_change = dedup_for_scan[value_column].pct_change()
    suspicious_gt_10pct = int((daily_change > SUSPICIOUS_RETURN_THRESHOLD).sum())
    suspicious_lt_minus_10pct = int((daily_change < -SUSPICIOUS_RETURN_THRESHOLD).sum())

    source = raw_group["source"].iloc[-1] if observation_count else ""
    source_quality = raw_group["source_quality"].iloc[-1] if observation_count else ""

    return {
        "source": source,
        "source_quality": source_quality,
        "first_date": first_date,
        "last_date": last_date,
        "observation_count": observation_count,
        "missing_value_count": missing_value_count,
        "duplicate_date_count": duplicate_date_count,
        "suspicious_return_count_gt_10pct": suspicious_gt_10pct,
        "suspicious_return_count_lt_minus_10pct": suspicious_lt_minus_10pct,
    }


def _determine_status(metrics: Dict[str, Any], asset_type: str) -> str:
    """
    Decide PASS / WARNING / FAIL for one entity row.

    FAIL (blocks publication per model_governance.md §3.5):
    - zero observations
    - any missing value (NaN NAV/tri_value, or an unparseable date)
    - any duplicate (entity, date) row found in the processed file
    - blank/unlabelled source_quality (fetch was never properly labelled)
    - (fund only) metadata_verification_status == FAILED_METADATA_CHECK
    - (fund only) fund_label not found in fund_master.csv at all

    WARNING (usable, but flagged):
    - any daily move beyond +/-10%
    - source_quality indicates a known, disclosed degradation (expired
      cache, metadata warning, price-index proxy, or synthetic approximation)
    - (fund only) metadata_verification_status == NEEDS_API_METADATA_VERIFICATION

    PASS: none of the above.
    """
    if metrics["observation_count"] == 0:
        return STATUS_FAIL
    if metrics["missing_value_count"] > 0:
        return STATUS_FAIL
    if metrics["duplicate_date_count"] > 0:
        return STATUS_FAIL
    if not metrics.get("source_quality"):
        return STATUS_FAIL

    metadata_status = metrics.get("metadata_verification_status", NOT_APPLICABLE)
    if asset_type == ASSET_TYPE_FUND and metadata_status in (VERIFICATION_STATUS_FAILED, UNKNOWN_FUND_LABEL):
        return STATUS_FAIL

    warning_triggered = (
        metrics["suspicious_return_count_gt_10pct"] > 0
        or metrics["suspicious_return_count_lt_minus_10pct"] > 0
        or metrics.get("source_quality") in DEGRADED_SOURCE_QUALITIES
        or (asset_type == ASSET_TYPE_FUND and metadata_status == VERIFICATION_STATUS_NEEDS_VERIFICATION)
    )
    if warning_triggered:
        return STATUS_WARNING

    return STATUS_PASS


# ---------------------------------------------------------------------------
# Data quality report
# ---------------------------------------------------------------------------

def generate_data_quality_report(nav_df: pd.DataFrame, benchmark_df: pd.DataFrame) -> pd.DataFrame:
    """
    Produce the data quality report described in
    master_project_instructions.md.md §14, covering both mutual funds and
    benchmarks.

    `nav_df` and `benchmark_df` should be the RAW, schema-valid DataFrames
    as loaded from nav_daily_clean.csv / benchmark_daily.csv (i.e. before
    deduplication/date-filtering), so duplicate and missing-value counts
    reflect what the fetch/cache layer actually produced. Use
    validate_nav_daily() / validate_benchmark_daily() separately to obtain
    the cleaned data used for downstream calculations.

    Writes 02_processed_data/data_quality_report.csv and returns it.
    """
    _enforce_schema(nav_df, NAV_SCHEMA_COLUMNS, "nav_daily_clean.csv")
    _enforce_schema(benchmark_df, BENCHMARK_SCHEMA_COLUMNS, "benchmark_daily.csv")

    nav_df = nav_df.copy()
    nav_df["date"] = pd.to_datetime(nav_df["date"], errors="coerce")
    benchmark_df = benchmark_df.copy()
    benchmark_df["date"] = pd.to_datetime(benchmark_df["date"], errors="coerce")

    verification_map = _load_fund_verification_status_map()
    rows: List[Dict[str, Any]] = []

    for fund_label, group in nav_df.groupby("fund_label", dropna=False, sort=False):
        metrics = _assess_entity_quality(group, "nav")
        metrics["fund_label_or_benchmark_label"] = fund_label
        metrics["asset_type"] = ASSET_TYPE_FUND
        metrics["metadata_verification_status"] = verification_map.get(fund_label, UNKNOWN_FUND_LABEL)
        metrics["status"] = _determine_status(metrics, ASSET_TYPE_FUND)
        rows.append(metrics)

    for benchmark_label, group in benchmark_df.groupby("benchmark_label", dropna=False, sort=False):
        metrics = _assess_entity_quality(group, "tri_value")
        metrics["fund_label_or_benchmark_label"] = benchmark_label
        metrics["asset_type"] = ASSET_TYPE_BENCHMARK
        metrics["metadata_verification_status"] = NOT_APPLICABLE
        metrics["status"] = _determine_status(metrics, ASSET_TYPE_BENCHMARK)
        rows.append(metrics)

    report = pd.DataFrame(rows, columns=DATA_QUALITY_REPORT_COLUMNS)
    if not report.empty:
        report = report[DATA_QUALITY_REPORT_COLUMNS]
        for date_column in ("first_date", "last_date"):
            report[date_column] = pd.to_datetime(report[date_column]).dt.strftime("%Y-%m-%d")

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    report.to_csv(DATA_QUALITY_REPORT_PATH, index=False)

    return report


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_data_validation() -> Dict[str, pd.DataFrame]:
    """
    Full Phase 3 entry point: load the two raw processed inputs produced by
    api_fetch.py, generate and write the data quality report from that raw
    data (so the report reflects exactly what the fetch/cache layer
    produced, duplicates and all), then clean both files and OVERWRITE
    nav_daily_clean.csv / benchmark_daily.csv in place with the validated
    result (schema-enforced, deduplicated, sorted, filtered to the
    2021-01-01+ data horizon) - fulfilling the contract documented in
    data_dictionary.md §4.1/§4.2. Every downstream stage (returns.py,
    metrics.py, the Streamlit app, Excel/Power BI) then reads an on-disk
    file that is genuinely clean, rather than needing to re-validate it
    themselves.

    Intended to be called explicitly (e.g. from refresh_data.py) — never on
    import, never inside a Streamlit page.
    """
    raw_nav_df = load_nav_daily_clean()
    raw_benchmark_df = load_benchmark_daily()

    _enforce_schema(raw_nav_df, NAV_SCHEMA_COLUMNS, "nav_daily_clean.csv")
    _enforce_schema(raw_benchmark_df, BENCHMARK_SCHEMA_COLUMNS, "benchmark_daily.csv")

    quality_report = generate_data_quality_report(raw_nav_df, raw_benchmark_df)
    cleaned_nav_df = validate_nav_daily(raw_nav_df)
    cleaned_benchmark_df = validate_benchmark_daily(raw_benchmark_df)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    cleaned_nav_df.to_csv(NAV_DAILY_CLEAN_PATH, index=False)
    cleaned_benchmark_df.to_csv(BENCHMARK_DAILY_PATH, index=False)

    return {
        "nav_daily_clean": cleaned_nav_df,
        "benchmark_daily": cleaned_benchmark_df,
        "data_quality_report": quality_report,
    }
