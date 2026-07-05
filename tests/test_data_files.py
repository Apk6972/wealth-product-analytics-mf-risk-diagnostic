"""
Tests: processed CSV outputs exist, load cleanly, and pass integrity checks.

These tests describe the state a healthy, fully-run refresh pipeline leaves
behind.  If any test here fails, the fix is to re-run the data pipeline:

    python 04_streamlit_app/refresh_data.py

Do NOT change these tests to suppress real failures.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "02_processed_data"

REQUIRED_FILES = [
    "nav_daily_clean.csv",
    "returns_daily.csv",
    "returns_monthly.csv",
    "metrics_summary.csv",
    "rolling_metrics.csv",
    "benchmark_metrics.csv",
    "stress_results.csv",
    "attribution_results.csv",
    "suitability_results.csv",
    "data_quality_report.csv",
]


# ---------------------------------------------------------------------------
# Requirement 1 — every required CSV must exist on disk
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", REQUIRED_FILES)
def test_required_csv_exists(filename: str) -> None:
    """Each required processed CSV must exist in 02_processed_data/."""
    path = PROCESSED_DIR / filename
    assert path.is_file(), (
        f"{filename} is missing from {PROCESSED_DIR}. "
        "Run: python 04_streamlit_app/refresh_data.py"
    )


# ---------------------------------------------------------------------------
# Requirement 2 — every required CSV must load with pandas and have rows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", REQUIRED_FILES)
def test_required_csv_loads_and_is_not_empty(filename: str) -> None:
    """Each required CSV must load with pandas and contain at least one row."""
    path = PROCESSED_DIR / filename
    if not path.is_file():
        pytest.skip(f"{filename} is absent — covered by test_required_csv_exists")

    df = pd.read_csv(path)
    assert not df.empty, (
        f"{filename} loaded but is empty (0 rows). "
        "Run: python 04_streamlit_app/refresh_data.py"
    )


# ---------------------------------------------------------------------------
# Requirement 3 — data_quality_report.csv must not contain status == FAIL
# ---------------------------------------------------------------------------


def test_data_quality_report_no_fail_status() -> None:
    """data_quality_report.csv must not contain any rows with status == FAIL."""
    path = PROCESSED_DIR / "data_quality_report.csv"
    if not path.is_file():
        pytest.skip("data_quality_report.csv is absent — covered by test_required_csv_exists")

    df = pd.read_csv(path)
    assert "status" in df.columns, (
        "data_quality_report.csv is missing the 'status' column — the pipeline "
        "may have produced an unexpected schema."
    )

    fail_rows = df[df["status"] == "FAIL"]
    if not fail_rows.empty:
        label_col = "fund_label_or_benchmark_label"
        series_list = (
            fail_rows[label_col].dropna().tolist()
            if label_col in df.columns
            else ["<unknown>"]
        )
        pytest.fail(
            f"data_quality_report.csv contains {len(fail_rows)} FAIL row(s): "
            f"{series_list}. Review the quality report, then re-run the refresh pipeline."
        )


# ---------------------------------------------------------------------------
# Requirement 4 — portfolio weights in attribution_results.csv sum to ~1.0
#                 per scenario (tested only when the weight column is present)
# ---------------------------------------------------------------------------


def test_attribution_weights_sum_to_one_per_scenario() -> None:
    """
    For each scenario in attribution_results.csv the fund_weight values must
    sum to approximately 1.0 (± 1e-6).  The column name is fund_weight (the
    actual schema used in this project — not 'weight').
    """
    path = PROCESSED_DIR / "attribution_results.csv"
    if not path.is_file():
        pytest.skip("attribution_results.csv is absent — covered by test_required_csv_exists")

    df = pd.read_csv(path)

    if "fund_weight" not in df.columns:
        pytest.skip(
            "attribution_results.csv has no 'fund_weight' column — "
            "the weight-sum check is not applicable to this schema."
        )
    if "scenario_name" not in df.columns:
        pytest.skip(
            "attribution_results.csv has no 'scenario_name' column — "
            "cannot group by scenario for the weight-sum check."
        )

    bad_scenarios: list[str] = []
    for scenario, group in df.groupby("scenario_name"):
        total = group["fund_weight"].dropna().sum()
        if abs(total - 1.0) > 1e-6:
            bad_scenarios.append(f"'{scenario}' sums to {total:.8f}")

    assert not bad_scenarios, (
        "Portfolio weights do not sum to 1.0 for the following scenario(s):\n"
        + "\n".join(bad_scenarios)
    )
