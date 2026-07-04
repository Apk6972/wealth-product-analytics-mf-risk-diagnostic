"""
Attribution Module — allocation weight vs stress loss share.

Reference: 00_project_control/master_project_instructions.md.md §21
(Attribution Module) and 00_project_control/formula_audit.md §7.

Input (from stress.py):
    02_processed_data/stress_results.csv (or any DataFrame with the same
    scenario_type/scenario_name/fund_label/stress_return columns, e.g. a
    single custom-shock scenario built on the fly)
    01_raw_data/scheme_master/portfolio_weights.csv

Output:
    02_processed_data/attribution_results.csv

Formulas (per scenario_name):
    Fund Loss Contribution        = Fund Weight x Fund Stress Return
    Total Portfolio Stress Return = Sum(Fund Loss Contribution)
    Stress Loss Share             = Fund Loss Contribution / Total Portfolio Stress Return
    Loss Amount (INR)             = Base Portfolio Value x Fund Loss Contribution
    Post-Stress Portfolio Value   = Base Portfolio Value x (1 + Total Portfolio Stress Return)

Key insight to preserve downstream: allocation weight is not the same as
stress loss share - a fund can carry a small allocation weight yet
contribute a disproportionate share of total stress-scenario losses.

Two convenience columns beyond data_dictionary.md §4.12's documented
schema are appended, both directly derived from the formulas above (no new
inputs), to satisfy this module's explicit task requirements:
    is_largest_loss_contributor    - True for the single fund with the most
                                      negative fund_loss_contribution in each
                                      scenario ("largest loss contributor by
                                      scenario").
    stress_loss_share_minus_weight - stress_loss_share - fund_weight, a
                                      ready-made series for an allocation
                                      weight vs stress loss share chart.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import List

import pandas as pd

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from data_cleaning import DataValidationError  # noqa: E402 - sys.path must be configured before this import
from returns import PROCESSED_DATA_DIR, PROJECT_ROOT  # noqa: E402 - sys.path must be configured before this import

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCHEME_MASTER_DIR = PROJECT_ROOT / "01_raw_data" / "scheme_master"
PORTFOLIO_WEIGHTS_PATH = SCHEME_MASTER_DIR / "portfolio_weights.csv"
STRESS_RESULTS_PATH = PROCESSED_DATA_DIR / "stress_results.csv"
ATTRIBUTION_RESULTS_PATH = PROCESSED_DATA_DIR / "attribution_results.csv"

# ---------------------------------------------------------------------------
# Constants / schemas
# ---------------------------------------------------------------------------

DEFAULT_BASE_PORTFOLIO_VALUE = 10_000_000.0

STRESS_RESULTS_INPUT_COLUMNS = ["scenario_type", "scenario_name", "fund_label", "stress_return"]
PORTFOLIO_WEIGHTS_COLUMNS = ["fund_label", "weight"]

ATTRIBUTION_RESULTS_COLUMNS = [
    "scenario_name",
    "fund_label",
    "fund_weight",
    "fund_stress_return",
    "fund_loss_contribution",
    "stress_loss_share",
    "base_portfolio_value",
    "loss_amount_inr",
    "total_portfolio_stress_return",
    "post_stress_portfolio_value",
    "is_largest_loss_contributor",
    "stress_loss_share_minus_weight",
]


def _enforce_schema(df: pd.DataFrame, required_columns: List[str], label: str) -> None:
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise DataValidationError(f"{label} is missing required columns: {missing}")


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator is None or pd.isna(denominator) or denominator == 0:
        return float("nan")
    return numerator / denominator


# ---------------------------------------------------------------------------
# Core attribution
# ---------------------------------------------------------------------------

def calculate_attribution(
    stress_results: pd.DataFrame,
    portfolio_weights: pd.DataFrame,
    base_portfolio_value: float = DEFAULT_BASE_PORTFOLIO_VALUE,
) -> pd.DataFrame:
    """
    Fund Loss Contribution = Fund Weight x Fund Stress Return
    Total Portfolio Stress Return = Sum(Fund Loss Contribution)
    Stress Loss Share = Fund Loss Contribution / Total Portfolio Stress Return
    Loss Amount (INR) = Base Portfolio Value x Fund Loss Contribution
    Post-Stress Portfolio Value = Base Portfolio Value x (1 + Total Portfolio Stress Return)

    Computed independently per scenario_name. A fund present in
    portfolio_weights but missing a stress_return for a given scenario (or
    vice versa) is excluded from that scenario's attribution with a
    warning, rather than silently assumed to be zero.
    """
    _enforce_schema(stress_results, STRESS_RESULTS_INPUT_COLUMNS, "stress_results")
    _enforce_schema(portfolio_weights, PORTFOLIO_WEIGHTS_COLUMNS, "portfolio_weights")

    total_weight = portfolio_weights["weight"].sum()
    if abs(total_weight - 1.0) > 1e-6:
        warnings.warn(f"portfolio_weights sum to {total_weight:.4f}, not 1.0.")

    all_portfolio_funds = set(portfolio_weights["fund_label"])

    result_frames: List[pd.DataFrame] = []
    for scenario_name, scenario_group in stress_results.groupby("scenario_name", sort=False):
        merged = scenario_group.merge(portfolio_weights, on="fund_label", how="inner")

        missing_funds = all_portfolio_funds - set(merged["fund_label"])
        if missing_funds:
            warnings.warn(
                f"Scenario '{scenario_name}': portfolio fund(s) {sorted(missing_funds)} have no "
                "stress_return for this scenario and are excluded from its attribution."
            )
        extra_funds = set(scenario_group["fund_label"]) - all_portfolio_funds
        if extra_funds:
            warnings.warn(
                f"Scenario '{scenario_name}': fund(s) {sorted(extra_funds)} have a stress_return "
                "but no entry in portfolio_weights and are excluded from its attribution."
            )
        if merged.empty:
            continue

        merged = merged.reset_index(drop=True)
        merged["fund_loss_contribution"] = merged["weight"] * merged["stress_return"]
        # skipna=False: if any included fund's stress_return is NaN, the
        # portfolio-level total is NaN too (missing data is disclosed, not
        # silently treated as a zero contribution).
        total_portfolio_stress_return = merged["fund_loss_contribution"].sum(skipna=False)
        merged["total_portfolio_stress_return"] = total_portfolio_stress_return
        merged["stress_loss_share"] = merged["fund_loss_contribution"].apply(
            lambda contribution: _safe_divide(contribution, total_portfolio_stress_return)
        )
        merged["base_portfolio_value"] = base_portfolio_value
        merged["loss_amount_inr"] = base_portfolio_value * merged["fund_loss_contribution"]
        merged["post_stress_portfolio_value"] = base_portfolio_value * (1.0 + total_portfolio_stress_return)

        merged["is_largest_loss_contributor"] = False
        if merged["fund_loss_contribution"].notna().any():
            largest_loss_index = merged["fund_loss_contribution"].idxmin()
            merged.loc[largest_loss_index, "is_largest_loss_contributor"] = True

        merged["stress_loss_share_minus_weight"] = merged["stress_loss_share"] - merged["weight"]

        merged = merged.rename(columns={"weight": "fund_weight", "stress_return": "fund_stress_return"})
        result_frames.append(merged[ATTRIBUTION_RESULTS_COLUMNS])

    if not result_frames:
        return pd.DataFrame(columns=ATTRIBUTION_RESULTS_COLUMNS)

    return pd.concat(result_frames, ignore_index=True)


def generate_attribution_results(
    stress_results: pd.DataFrame,
    portfolio_weights: pd.DataFrame,
    base_portfolio_value: float = DEFAULT_BASE_PORTFOLIO_VALUE,
) -> pd.DataFrame:
    """Assemble 02_processed_data/attribution_results.csv per data_dictionary.md §4.12."""
    return calculate_attribution(stress_results, portfolio_weights, base_portfolio_value=base_portfolio_value)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _load_stress_results() -> pd.DataFrame:
    if not STRESS_RESULTS_PATH.exists():
        raise DataValidationError(
            f"{STRESS_RESULTS_PATH} does not exist. Run the stress engine "
            "(stress.run_stress_engine()) before running the attribution engine."
        )
    return pd.read_csv(STRESS_RESULTS_PATH)


def _load_portfolio_weights() -> pd.DataFrame:
    if not PORTFOLIO_WEIGHTS_PATH.exists():
        raise DataValidationError(f"{PORTFOLIO_WEIGHTS_PATH} does not exist.")
    df = pd.read_csv(PORTFOLIO_WEIGHTS_PATH)
    _enforce_schema(df, PORTFOLIO_WEIGHTS_COLUMNS, "portfolio_weights.csv")
    return df


def run_attribution_engine(base_portfolio_value: float = DEFAULT_BASE_PORTFOLIO_VALUE) -> pd.DataFrame:
    """
    Full entry point: load stress_results.csv and portfolio_weights.csv,
    compute attribution for every scenario, and write
    02_processed_data/attribution_results.csv.
    """
    stress_results = _load_stress_results()
    portfolio_weights = _load_portfolio_weights()

    result = generate_attribution_results(stress_results, portfolio_weights, base_portfolio_value=base_portfolio_value)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(ATTRIBUTION_RESULTS_PATH, index=False)

    return result
