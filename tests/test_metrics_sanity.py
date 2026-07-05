"""
Tests: daily returns are plausible, metrics directional relationships hold,
and the pure calculation functions produce correct results for known inputs.

Requirement 5 — daily returns must be numeric and broadly plausible.
The data_quality_report.csv intentionally flags a small number of extreme
daily returns (suspicious_return_count_lt_minus_10pct = 1 for three funds).
These are real market events that have been reviewed and retained in the
pipeline.  Tests here use a deliberately wide tolerance (±50%) so that
disclosed outliers do NOT cause false failures.

This file also contains lightweight unit tests for the pure calculation
functions in metrics.py.  These tests do not touch any CSV files; they verify
the mathematical correctness of the formulas with known inputs.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "04_streamlit_app" / "src"
PROCESSED_DIR = PROJECT_ROOT / "02_processed_data"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from metrics import (  # noqa: E402
    calculate_annualized_volatility,
    calculate_cagr,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_var_cvar,
)

# ---------------------------------------------------------------------------
# Module-scoped fixtures — each CSV is loaded once per test session
# ---------------------------------------------------------------------------

EXPECTED_FUNDS = frozenset(
    {
        "HDFC Balanced Advantage",
        "ICICI Bluechip",
        "Nippon India Small Cap",
        "Parag Parikh Flexi Cap",
        "UTI Nifty 50 Index",
    }
)


@pytest.fixture(scope="module")
def returns_daily() -> pd.DataFrame:
    path = PROCESSED_DIR / "returns_daily.csv"
    if not path.is_file():
        pytest.skip("returns_daily.csv is absent — run refresh_data.py")
    return pd.read_csv(path, parse_dates=["date"])


@pytest.fixture(scope="module")
def metrics_summary() -> pd.DataFrame:
    path = PROCESSED_DIR / "metrics_summary.csv"
    if not path.is_file():
        pytest.skip("metrics_summary.csv is absent — run refresh_data.py")
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Requirement 5a — daily_return column is numeric, not corrupted to strings
# ---------------------------------------------------------------------------


def test_daily_returns_column_is_numeric(returns_daily: pd.DataFrame) -> None:
    """daily_return must be a numeric dtype, never string/object."""
    assert pd.api.types.is_numeric_dtype(returns_daily["daily_return"]), (
        "daily_return column is not a numeric dtype. "
        "The CSV may have been overwritten with non-numeric values."
    )


# ---------------------------------------------------------------------------
# Requirement 5b — at least some non-NaN returns exist
# ---------------------------------------------------------------------------


def test_daily_returns_not_all_nan(returns_daily: pd.DataFrame) -> None:
    """At least some daily_return values must be non-NaN.

    The first observation per fund always has NaN daily_return by design
    (no prior NAV to compute a return from) — that is expected and correct.
    """
    valid_count = returns_daily["daily_return"].dropna().shape[0]
    assert valid_count > 0, (
        "All daily_return values are NaN. The pipeline may not have run correctly."
    )


# ---------------------------------------------------------------------------
# Requirement 5c — plausibility: ≥99% of non-NaN returns are within ±50%
# ---------------------------------------------------------------------------


def test_daily_returns_plausibility(returns_daily: pd.DataFrame) -> None:
    """
    At least 99% of non-NaN daily returns must satisfy |return| ≤ 0.50.

    The ±50% threshold is intentionally wide to accommodate disclosed outliers
    (data_quality_report.csv shows suspicious_return_count_lt_minus_10pct = 1
    for ICICI Bluechip, Nippon India Small Cap, and UTI Nifty 50 Index — these
    are real, retained market events).  A failure here indicates something more
    systematic, such as a NAV series expressed in an unexpected unit.
    """
    valid = returns_daily["daily_return"].dropna()
    assert len(valid) > 0, "No valid daily_return observations to check."

    within_range = (valid.abs() <= 0.50).sum()
    pct_within = within_range / len(valid)

    assert pct_within >= 0.99, (
        f"Only {pct_within:.1%} of daily returns are within ±50% — expected ≥99%. "
        "This may indicate a data corruption or unit error in the NAV series."
    )


# ---------------------------------------------------------------------------
# Requirement 5d — all five expected funds have return data
# ---------------------------------------------------------------------------


def test_daily_returns_fund_coverage(returns_daily: pd.DataFrame) -> None:
    """All five portfolio funds must appear in returns_daily.csv."""
    actual_funds = set(returns_daily["fund_label"].dropna().unique())
    missing = EXPECTED_FUNDS - actual_funds
    assert not missing, (
        f"The following fund(s) are absent from returns_daily.csv: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# Metrics summary directional checks
# (these verify relationships that must hold regardless of exact numbers)
# ---------------------------------------------------------------------------


def test_metrics_cagr_is_finite_and_present(metrics_summary: pd.DataFrame) -> None:
    """Every fund in metrics_summary must have a finite, non-NaN CAGR."""
    missing_cagr = metrics_summary[metrics_summary["cagr"].isna()]["fund_label"].tolist()
    assert not missing_cagr, f"NaN CAGR for fund(s): {missing_cagr}"

    infinite_cagr = metrics_summary[
        ~metrics_summary["cagr"].apply(math.isfinite)
    ]["fund_label"].tolist()
    assert not infinite_cagr, f"Infinite CAGR for fund(s): {infinite_cagr}"


def test_metrics_annualized_volatility_positive(metrics_summary: pd.DataFrame) -> None:
    """Annualized volatility must be strictly positive for every fund."""
    bad = metrics_summary[metrics_summary["annualized_volatility"] <= 0]["fund_label"].tolist()
    assert not bad, f"Non-positive annualized_volatility for fund(s): {bad}"


def test_metrics_max_drawdown_is_negative(metrics_summary: pd.DataFrame) -> None:
    """Max drawdown must be strictly negative — it represents a peak-to-trough loss."""
    bad = metrics_summary[metrics_summary["max_drawdown"] >= 0]["fund_label"].tolist()
    assert not bad, (
        f"Non-negative max_drawdown for fund(s): {bad}. "
        "Drawdown is a loss and must always be a negative number."
    )


def test_metrics_daily_var_is_negative(metrics_summary: pd.DataFrame) -> None:
    """Daily VaR 95 must be negative — it represents a loss threshold."""
    bad = metrics_summary[metrics_summary["daily_var_95"] >= 0]["fund_label"].tolist()
    assert not bad, f"Non-negative daily_var_95 for fund(s): {bad}"


def test_metrics_cvar_is_at_least_as_bad_as_var(metrics_summary: pd.DataFrame) -> None:
    """
    Daily CVaR 95 must be ≤ Daily VaR 95 for every fund.

    CVaR is the mean of the worst-5%-of-days returns; VaR is the threshold
    at the 5th percentile.  By construction CVaR ≤ VaR (both are losses, CVaR
    is deeper into the tail).
    """
    both = metrics_summary[["fund_label", "daily_var_95", "daily_cvar_95"]].dropna()
    bad = both[both["daily_cvar_95"] > both["daily_var_95"]]["fund_label"].tolist()
    assert not bad, (
        f"daily_cvar_95 > daily_var_95 (CVaR should never exceed VaR) for fund(s): {bad}"
    )


def test_metrics_positive_month_ratio_bounded(metrics_summary: pd.DataFrame) -> None:
    """Positive month ratio must be in [0, 1] — it is a proportion."""
    col = metrics_summary["positive_month_ratio"].dropna()
    assert (col >= 0).all() and (col <= 1).all(), (
        "positive_month_ratio contains values outside [0, 1]."
    )


# ---------------------------------------------------------------------------
# Unit tests for pure calculation functions (no file I/O, known inputs)
# ---------------------------------------------------------------------------


class TestCalculateCagr:
    """Unit tests for calculate_cagr()."""

    def test_known_two_year_growth(self) -> None:
        """NAV growing from 100 → 121 over 730 days (≈ 2 years) → CAGR ≈ 10%."""
        nav_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2021-01-01", "2023-01-01"]),
                "nav": [100.0, 121.0],
            }
        )
        result = calculate_cagr(nav_df)
        assert abs(result - 0.10) < 0.001, f"Expected ~0.10, got {result:.6f}"

    def test_empty_input_returns_nan(self) -> None:
        """Empty DataFrame must return NaN, not raise."""
        result = calculate_cagr(pd.DataFrame(columns=["date", "nav"]))
        assert math.isnan(result)

    def test_single_row_returns_nan(self) -> None:
        """A single observation has zero calendar-day span — must return NaN."""
        nav_df = pd.DataFrame(
            {"date": pd.to_datetime(["2021-01-01"]), "nav": [100.0]}
        )
        result = calculate_cagr(nav_df)
        assert math.isnan(result)

    def test_negative_nav_returns_nan(self) -> None:
        """A zero or negative starting NAV is invalid and must return NaN."""
        nav_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2021-01-01", "2022-01-01"]),
                "nav": [0.0, 100.0],
            }
        )
        result = calculate_cagr(nav_df)
        assert math.isnan(result)


class TestCalculateAnnualizedVolatility:
    """Unit tests for calculate_annualized_volatility()."""

    def test_known_daily_std(self) -> None:
        """
        With daily std = 0.01, annualized vol ≈ 0.01 × √252 ≈ 0.1587.
        Allow ±20% relative tolerance for sampling variability with n=252.
        """
        rng = np.random.default_rng(seed=42)
        daily_returns = pd.Series(rng.normal(loc=0.0, scale=0.01, size=252))
        vol = calculate_annualized_volatility(daily_returns)
        expected = 0.01 * math.sqrt(252)
        assert abs(vol - expected) / expected < 0.20, (
            f"Annualized vol {vol:.4f} deviates more than 20% from expected {expected:.4f}"
        )

    def test_single_observation_returns_nan(self) -> None:
        """std() requires at least 2 observations — single value must return NaN."""
        result = calculate_annualized_volatility(pd.Series([0.01]))
        assert math.isnan(result)

    def test_empty_series_returns_nan(self) -> None:
        result = calculate_annualized_volatility(pd.Series(dtype=float))
        assert math.isnan(result)

    def test_constant_returns_zero_volatility(self) -> None:
        """A constant daily return has zero std — annualized vol must also be zero."""
        result = calculate_annualized_volatility(pd.Series([0.001] * 100))
        assert result == pytest.approx(0.0, abs=1e-10)


class TestCalculateVarCvar:
    """Unit tests for calculate_var_cvar()."""

    def test_var_is_negative_for_mixed_returns(self) -> None:
        """5th-percentile VaR should be negative for a distribution centered near 0."""
        returns = pd.Series(list(range(-100, 101)) * 5, dtype=float) / 1000.0
        var, _ = calculate_var_cvar(returns)
        assert var < 0, f"VaR should be negative for a symmetric distribution, got {var}"

    def test_cvar_is_leq_var(self) -> None:
        """CVaR (average of worst-5% days) must be ≤ VaR (5th-percentile threshold)."""
        rng = np.random.default_rng(seed=0)
        returns = pd.Series(rng.normal(loc=0.0005, scale=0.012, size=1000))
        var, cvar = calculate_var_cvar(returns)
        assert cvar <= var, (
            f"CVaR ({cvar:.6f}) must be ≤ VaR ({var:.6f}) by construction."
        )

    def test_empty_series_returns_nan_pair(self) -> None:
        var, cvar = calculate_var_cvar(pd.Series(dtype=float))
        assert math.isnan(var) and math.isnan(cvar)


class TestCalculateRatios:
    """Unit tests for Sharpe and Sortino ratio calculations."""

    def test_sharpe_positive_when_cagr_exceeds_rfr(self) -> None:
        sharpe = calculate_sharpe_ratio(
            cagr=0.15, annualized_volatility=0.12, risk_free_rate=0.06
        )
        assert sharpe > 0

    def test_sharpe_negative_when_cagr_below_rfr(self) -> None:
        sharpe = calculate_sharpe_ratio(
            cagr=0.04, annualized_volatility=0.12, risk_free_rate=0.06
        )
        assert sharpe < 0

    def test_sharpe_zero_volatility_returns_nan(self) -> None:
        """Zero denominator must return NaN, not raise ZeroDivisionError."""
        result = calculate_sharpe_ratio(
            cagr=0.10, annualized_volatility=0.0, risk_free_rate=0.06
        )
        assert math.isnan(result)

    def test_sortino_positive_when_cagr_exceeds_rfr(self) -> None:
        sortino = calculate_sortino_ratio(
            cagr=0.15, downside_deviation=0.08, risk_free_rate=0.06
        )
        assert sortino > 0

    def test_sortino_zero_downside_returns_nan(self) -> None:
        result = calculate_sortino_ratio(
            cagr=0.10, downside_deviation=0.0, risk_free_rate=0.06
        )
        assert math.isnan(result)

    def test_sortino_geq_sharpe_for_same_cagr(self) -> None:
        """
        When downside deviation < total volatility (which is typical), Sortino
        ratio must be greater than or equal to Sharpe ratio for the same CAGR.
        """
        cagr, rfr = 0.15, 0.06
        vol = 0.12
        dd = 0.08  # downside_deviation < total vol
        sharpe = calculate_sharpe_ratio(cagr, vol, rfr)
        sortino = calculate_sortino_ratio(cagr, dd, rfr)
        assert sortino >= sharpe, (
            f"Sortino ({sortino:.4f}) should be ≥ Sharpe ({sharpe:.4f}) when "
            "downside deviation < total volatility."
        )
