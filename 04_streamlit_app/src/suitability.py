"""
Suitability Module — client profile fit, role, and educational action diagnostics.

Reference: 00_project_control/master_project_instructions.md.md §22
(Suitability Module) and 00_project_control/formula_audit.md §8.

Inputs:
    02_processed_data/metrics_summary.csv
    02_processed_data/benchmark_metrics.csv (optional — if absent or empty,
        rolling beta / downside capture gracefully degrade to "not available"
        rather than failing the whole engine)
    02_processed_data/stress_results.csv
    02_processed_data/attribution_results.csv
    01_raw_data/scheme_master/portfolio_weights.csv

Output:
    02_processed_data/suitability_results.csv
    Columns: fund_label, client_profile, suitability_role, risk_warning,
    recommended_action, rationale — plus every underlying factor value used
    to reach that classification (overall_risk_tier, annualized_volatility,
    max_drawdown, daily_cvar_95, recovery_period_days,
    small_cap_exposure_flag, rolling_beta, downside_capture,
    avg_stress_loss_share_minus_weight, benchmark_relative_data_available),
    appended beyond the 6 requested columns for full auditability — every
    label in this file must be traceable back to a concrete number.

------------------------------------------------------------------------
SCORING RUBRIC (formula_audit.md §8 flags these thresholds as an explicit
open item to be "specified explicitly during Phase 8 implementation, not
decided ad hoc in code" — this docstring IS that specification; see
limitations.md's Phase 8 open item to mirror it into formula_audit.md).
------------------------------------------------------------------------

One row is produced per (fund_label, client_profile) pair — the same fund
can be a "Core" holding for a Growth investor and "Unsuitable for profile"
for a Conservative one, so profile fit is never assessed independently of
the fund.

Step 1 — Per-factor risk tiering (LOW / MEDIUM / HIGH), fund-only (not
profile-dependent). A factor that cannot be computed (e.g. no benchmark
data) is treated as unavailable, never defaulted to a guessed value:

    Factor                  LOW              MEDIUM             HIGH
    -----------------------------------------------------------------------
    Annualized volatility   < 10%            10%-18%            > 18%
    Max drawdown (|value|)  < 15%            15%-30%            > 30%
    Daily CVaR 95 (|value|) < 2%             2%-4%              > 4%
    Recovery period         < 180 days       180-450 days       > 450 days,
                                                                 or never
                                                                 fully
                                                                 recovered
                                                                 within the
                                                                 observed
                                                                 window
                                                                 (unless
                                                                 max
                                                                 drawdown
                                                                 is
                                                                 negligible)
    Small-cap exposure      not a small-      -                 fund_label
                            cap fund                            identifies
                                                                 as small-cap
    Rolling beta            < 0.85           0.85-1.15          > 1.15
    Downside capture        < 90%            90%-110%           > 110%
                            (ratio; 1.0 = 100%, same decimal convention as
                            monthly_return / weight elsewhere in this project)
    Stress loss share       <= +2pp over      +2pp to +8pp       > +8pp over
    vs. weight (avg across  weight            over weight        weight
    all stress_results.csv
    scenarios, from
    attribution_results.csv's stress_loss_share_minus_weight)

Step 2 — Overall risk tier: each available factor tier is mapped to a
point value (LOW=1.0, MEDIUM=2.5, HIGH=4.0) and averaged across only the
AVAILABLE factors (never zero-filled); the average is bucketed back into
LOW (< 1.75), MEDIUM (1.75-3.25), or HIGH (> 3.25).

Step 3 — Profile fit via a risk-appetite "gap": each client profile has a
risk-appetite point value on the same 1.0-4.0 scale (Conservative=1.0,
Balanced=2.0, Growth=3.0, Aggressive=4.0). gap = profile_appetite -
fund_risk_points. The gap is then mapped to role/action:

    gap >= +1.5             : Defensive sleeve / Retain
                               (fund is comfortably below what this
                               profile could take on; serves as a ballast)
    -0.5 <= gap < +1.5       : Core / Retain
                               (fund's risk matches the profile well)
    -1.5 <= gap < -0.5       : Growth/Aggressive -> Aggressive satellite
                               (if fund risk = HIGH) or Satellite,
                               action Stagger allocation;
                               Balanced -> Satellite, action Cap exposure;
                               Conservative -> Watchlist, action Cap exposure
    -2.5 <= gap < -1.5       : Watchlist; action Pair with defensive sleeve
                               (Growth/Aggressive) or Cap exposure
                               (Conservative/Balanced)
    gap < -2.5               : Unsuitable for profile / Avoid for low
                               drawdown tolerance

Override: if the resulting role is Watchlist and benchmark-relative data
(beta, downside capture) was unavailable, the action becomes "Review
benchmark-relative behaviour" instead — Watchlist already signals
uncertainty, and missing benchmark context is the most direct way to
resolve it.

Language rule: every generated sentence describes trailing *historical*
data (never a forecast) and is phrased as an educational diagnostic, never
a buy/sell/hold instruction — enforced by always ending the rationale with
an explicit "not an investment recommendation" disclaimer.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

METRICS_SUMMARY_PATH = PROCESSED_DATA_DIR / "metrics_summary.csv"
BENCHMARK_METRICS_PATH = PROCESSED_DATA_DIR / "benchmark_metrics.csv"
STRESS_RESULTS_PATH = PROCESSED_DATA_DIR / "stress_results.csv"
ATTRIBUTION_RESULTS_PATH = PROCESSED_DATA_DIR / "attribution_results.csv"
SUITABILITY_RESULTS_PATH = PROCESSED_DATA_DIR / "suitability_results.csv"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLIENT_PROFILES = ["Conservative", "Balanced", "Growth", "Aggressive"]
RETURN_SEEKING_PROFILES = {"Growth", "Aggressive"}

RISK_TIER_LOW = "LOW"
RISK_TIER_MEDIUM = "MEDIUM"
RISK_TIER_HIGH = "HIGH"

# Shared 1.0 / 2.5 / 4.0 points scale used for both individual-factor tiers
# and the client-profile risk-appetite axis, so a "gap" between the two is
# directly comparable.
RISK_TIER_POINTS = {RISK_TIER_LOW: 1.0, RISK_TIER_MEDIUM: 2.5, RISK_TIER_HIGH: 4.0}
PROFILE_RISK_APPETITE_POINTS = {"Conservative": 1.0, "Balanced": 2.0, "Growth": 3.0, "Aggressive": 4.0}

ROLE_CORE = "Core"
ROLE_SATELLITE = "Satellite"
ROLE_DEFENSIVE_SLEEVE = "Defensive sleeve"
ROLE_AGGRESSIVE_SATELLITE = "Aggressive satellite"
ROLE_WATCHLIST = "Watchlist"
ROLE_UNSUITABLE = "Unsuitable for profile"

ACTION_RETAIN = "Retain"
ACTION_CAP_EXPOSURE = "Cap exposure"
ACTION_STAGGER_ALLOCATION = "Stagger allocation"
ACTION_PAIR_WITH_DEFENSIVE_SLEEVE = "Pair with defensive sleeve"
ACTION_REVIEW_BENCHMARK_RELATIVE = "Review benchmark-relative behaviour"
ACTION_AVOID_LOW_DRAWDOWN_TOLERANCE = "Avoid for low drawdown tolerance"

SCENARIO_TYPE_LABELS = {
    "HISTORICAL_REPLAY": "historical replay",
    "DETERMINISTIC": "deterministic",
    "CUSTOM": "custom",
}

DISCLAIMER = (
    "This is an educational diagnostic based on trailing historical data, not a forecast or an "
    "investment recommendation."
)

SUITABILITY_RESULTS_COLUMNS = [
    "fund_label",
    "client_profile",
    "suitability_role",
    "risk_warning",
    "recommended_action",
    "rationale",
    # Extra transparency/audit columns beyond the 6 requested ones: every
    # factor value that drove the classification above.
    "overall_risk_tier",
    "annualized_volatility",
    "max_drawdown",
    "daily_cvar_95",
    "recovery_period_days",
    "small_cap_exposure_flag",
    "rolling_beta",
    "downside_capture",
    "avg_stress_loss_share_minus_weight",
    "benchmark_relative_data_available",
]

METRICS_SUMMARY_INPUT_COLUMNS = ["fund_label", "annualized_volatility", "max_drawdown", "daily_cvar_95", "recovery_period_days"]
ATTRIBUTION_RESULTS_INPUT_COLUMNS = ["fund_label", "scenario_name", "stress_loss_share_minus_weight", "is_largest_loss_contributor"]
STRESS_RESULTS_INPUT_COLUMNS = ["scenario_name", "scenario_type"]
PORTFOLIO_WEIGHTS_COLUMNS = ["fund_label", "weight"]


def _enforce_schema(df: pd.DataFrame, required_columns: List[str], label: str) -> None:
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise DataValidationError(f"{label} is missing required columns: {missing}")


# ---------------------------------------------------------------------------
# Per-factor tiering
# ---------------------------------------------------------------------------

def _tier_volatility(annualized_volatility: float) -> Optional[str]:
    if pd.isna(annualized_volatility):
        return None
    if annualized_volatility < 0.10:
        return RISK_TIER_LOW
    if annualized_volatility < 0.18:
        return RISK_TIER_MEDIUM
    return RISK_TIER_HIGH


def _tier_drawdown(max_drawdown: float) -> Optional[str]:
    if pd.isna(max_drawdown):
        return None
    magnitude = abs(max_drawdown)
    if magnitude < 0.15:
        return RISK_TIER_LOW
    if magnitude < 0.30:
        return RISK_TIER_MEDIUM
    return RISK_TIER_HIGH


def _tier_cvar(daily_cvar_95: float) -> Optional[str]:
    if pd.isna(daily_cvar_95):
        return None
    magnitude = abs(daily_cvar_95)
    if magnitude < 0.02:
        return RISK_TIER_LOW
    if magnitude < 0.04:
        return RISK_TIER_MEDIUM
    return RISK_TIER_HIGH


def _tier_recovery(recovery_period_days: float, max_drawdown: float) -> Optional[str]:
    if pd.isna(recovery_period_days):
        # A NaN recovery period means either the fund never meaningfully
        # drew down (nothing to recover from - not risky) or it drew down
        # and never fully recovered within the observed window (the most
        # cautious case). Disambiguate using the drawdown magnitude.
        if pd.notna(max_drawdown) and abs(max_drawdown) < 0.01:
            return RISK_TIER_LOW
        return RISK_TIER_HIGH
    if recovery_period_days < 180:
        return RISK_TIER_LOW
    if recovery_period_days <= 450:
        return RISK_TIER_MEDIUM
    return RISK_TIER_HIGH


def _tier_small_cap(is_small_cap: bool) -> str:
    return RISK_TIER_HIGH if is_small_cap else RISK_TIER_LOW


def _tier_beta(rolling_beta: float) -> Optional[str]:
    if pd.isna(rolling_beta):
        return None
    if rolling_beta < 0.85:
        return RISK_TIER_LOW
    if rolling_beta <= 1.15:
        return RISK_TIER_MEDIUM
    return RISK_TIER_HIGH


def _tier_downside_capture(downside_capture: float) -> Optional[str]:
    if pd.isna(downside_capture):
        return None
    if downside_capture < 0.90:
        return RISK_TIER_LOW
    if downside_capture <= 1.10:
        return RISK_TIER_MEDIUM
    return RISK_TIER_HIGH


def _tier_stress_concentration(avg_stress_loss_share_minus_weight: float) -> Optional[str]:
    if pd.isna(avg_stress_loss_share_minus_weight):
        return None
    if avg_stress_loss_share_minus_weight <= 0.02:
        return RISK_TIER_LOW
    if avg_stress_loss_share_minus_weight <= 0.08:
        return RISK_TIER_MEDIUM
    return RISK_TIER_HIGH


def _overall_risk_tier(tiers: List[Optional[str]]) -> str:
    """Average available factor tiers (1.0/2.5/4.0 points scale) and bucket
    back into LOW/MEDIUM/HIGH. Unavailable factors (None) are excluded from
    the average, never treated as zero risk."""
    available_points = [RISK_TIER_POINTS[tier] for tier in tiers if tier is not None]
    if not available_points:
        return RISK_TIER_MEDIUM  # no usable factors at all - default to the cautious middle tier
    average_points = sum(available_points) / len(available_points)
    if average_points < 1.75:
        return RISK_TIER_LOW
    if average_points < 3.25:
        return RISK_TIER_MEDIUM
    return RISK_TIER_HIGH


# ---------------------------------------------------------------------------
# Factor extraction helpers
# ---------------------------------------------------------------------------

def _identify_small_cap_fund_flag(fund_label: str) -> bool:
    """Generic small-cap identification (consistent with stress.py) via a
    "small cap" substring match on fund_label, rather than a hardcoded name
    or an undeclared fund_master.csv dependency."""
    return "small cap" in str(fund_label).lower()


def _extract_benchmark_relative_factors(
    benchmark_metrics: Optional[pd.DataFrame], fund_label: str
) -> Tuple[float, float, bool]:
    """Returns (rolling_beta, downside_capture, benchmark_relative_data_available).
    benchmark_metrics may be None/empty (e.g. benchmarks pipeline not yet run) —
    handled gracefully rather than raising. If a fund has more than one row
    (multiple benchmark_label entries), the first is used."""
    if benchmark_metrics is None or benchmark_metrics.empty:
        return float("nan"), float("nan"), False
    fund_rows = benchmark_metrics[benchmark_metrics["fund_label"] == fund_label]
    if fund_rows.empty:
        return float("nan"), float("nan"), False
    row = fund_rows.iloc[0]
    beta = row["beta"] if "beta" in row.index else float("nan")
    downside_capture = row["downside_capture"] if "downside_capture" in row.index else float("nan")
    beta = float(beta) if pd.notna(beta) else float("nan")
    downside_capture = float(downside_capture) if pd.notna(downside_capture) else float("nan")
    available = pd.notna(beta) or pd.notna(downside_capture)
    return beta, downside_capture, available


def _extract_stress_concentration(
    attribution_results: pd.DataFrame, fund_label: str
) -> Tuple[float, Optional[str], float]:
    """Returns (avg_stress_loss_share_minus_weight, worst_scenario_name, worst_value)
    across every scenario in attribution_results.csv for this fund."""
    fund_rows = attribution_results[attribution_results["fund_label"] == fund_label]
    if fund_rows.empty:
        return float("nan"), None, float("nan")
    values = fund_rows["stress_loss_share_minus_weight"].dropna()
    if values.empty:
        return float("nan"), None, float("nan")
    avg_value = float(values.mean())
    worst_index = values.idxmax()
    worst_scenario = str(fund_rows.loc[worst_index, "scenario_name"])
    worst_value = float(values.loc[worst_index])
    return avg_value, worst_scenario, worst_value


# ---------------------------------------------------------------------------
# Role / action classification
# ---------------------------------------------------------------------------

def _classify_role_and_action(
    overall_risk_tier: str, client_profile: str, benchmark_relative_data_available: bool
) -> Tuple[str, str]:
    profile_appetite = PROFILE_RISK_APPETITE_POINTS[client_profile]
    fund_risk_points = RISK_TIER_POINTS[overall_risk_tier]
    gap = profile_appetite - fund_risk_points
    is_return_seeking = client_profile in RETURN_SEEKING_PROFILES

    if gap >= 1.5:
        role, action = ROLE_DEFENSIVE_SLEEVE, ACTION_RETAIN
    elif gap >= -0.5:
        role, action = ROLE_CORE, ACTION_RETAIN
    elif gap >= -1.5:
        if is_return_seeking:
            role = ROLE_AGGRESSIVE_SATELLITE if overall_risk_tier == RISK_TIER_HIGH else ROLE_SATELLITE
            action = ACTION_STAGGER_ALLOCATION
        else:
            role = ROLE_SATELLITE if client_profile == "Balanced" else ROLE_WATCHLIST
            action = ACTION_CAP_EXPOSURE
    elif gap >= -2.5:
        role = ROLE_WATCHLIST
        action = ACTION_PAIR_WITH_DEFENSIVE_SLEEVE if is_return_seeking else ACTION_CAP_EXPOSURE
    else:
        role, action = ROLE_UNSUITABLE, ACTION_AVOID_LOW_DRAWDOWN_TOLERANCE

    if role == ROLE_WATCHLIST and not benchmark_relative_data_available:
        action = ACTION_REVIEW_BENCHMARK_RELATIVE

    return role, action


# ---------------------------------------------------------------------------
# Narrative (risk_warning / rationale) builders
# ---------------------------------------------------------------------------

def _build_risk_warning(factor_descriptions: List[Tuple[str, str]]) -> str:
    """factor_descriptions: (tier, human-readable description) for every
    factor at MEDIUM or HIGH tier. HIGH-tier items are listed first."""
    if not factor_descriptions:
        return "No elevated risk factors were identified across the measured metrics for this fund."
    high = [description for tier, description in factor_descriptions if tier == RISK_TIER_HIGH]
    medium = [description for tier, description in factor_descriptions if tier == RISK_TIER_MEDIUM]
    return "; ".join(high + medium) + "."


def _compute_fund_risk_profile(
    fund_label: str,
    metrics_row: pd.Series,
    benchmark_metrics: Optional[pd.DataFrame],
    attribution_results: pd.DataFrame,
) -> Dict[str, Any]:
    annualized_volatility = float(metrics_row.get("annualized_volatility", float("nan")))
    max_drawdown = float(metrics_row.get("max_drawdown", float("nan")))
    daily_cvar_95 = float(metrics_row.get("daily_cvar_95", float("nan")))
    recovery_period_days_raw = metrics_row.get("recovery_period_days", float("nan"))
    recovery_period_days = float(recovery_period_days_raw) if pd.notna(recovery_period_days_raw) else float("nan")

    small_cap_exposure_flag = _identify_small_cap_fund_flag(fund_label)
    rolling_beta, downside_capture, benchmark_relative_data_available = _extract_benchmark_relative_factors(
        benchmark_metrics, fund_label
    )
    avg_stress_gap, worst_scenario_name, worst_stress_gap = _extract_stress_concentration(
        attribution_results, fund_label
    )

    tiers = {
        "volatility": _tier_volatility(annualized_volatility),
        "drawdown": _tier_drawdown(max_drawdown),
        "cvar": _tier_cvar(daily_cvar_95),
        "recovery": _tier_recovery(recovery_period_days, max_drawdown),
        "small_cap": _tier_small_cap(small_cap_exposure_flag),
        "beta": _tier_beta(rolling_beta),
        "downside_capture": _tier_downside_capture(downside_capture),
        "stress_concentration": _tier_stress_concentration(avg_stress_gap),
    }
    overall_risk_tier = _overall_risk_tier(list(tiers.values()))

    factor_descriptions: List[Tuple[str, str]] = []
    if tiers["volatility"] in (RISK_TIER_MEDIUM, RISK_TIER_HIGH):
        factor_descriptions.append((tiers["volatility"], f"annualized volatility of {annualized_volatility:.1%}"))
    if tiers["drawdown"] in (RISK_TIER_MEDIUM, RISK_TIER_HIGH):
        factor_descriptions.append((tiers["drawdown"], f"historical maximum drawdown of {max_drawdown:.1%}"))
    if tiers["cvar"] in (RISK_TIER_MEDIUM, RISK_TIER_HIGH):
        factor_descriptions.append(
            (tiers["cvar"], f"daily CVaR 95 of {daily_cvar_95:.1%} (average loss on the worst 5% of trading days)")
        )
    if tiers["recovery"] in (RISK_TIER_MEDIUM, RISK_TIER_HIGH):
        if pd.isna(recovery_period_days):
            factor_descriptions.append(
                (tiers["recovery"], "fund has not fully recovered from its worst historical drawdown within the observed data window")
            )
        else:
            factor_descriptions.append(
                (tiers["recovery"], f"longest historical drawdown recovery took {recovery_period_days:.0f} days")
            )
    if tiers["small_cap"] == RISK_TIER_HIGH:
        factor_descriptions.append((RISK_TIER_HIGH, "fund carries structural small-cap size/liquidity risk"))
    if tiers["beta"] in (RISK_TIER_MEDIUM, RISK_TIER_HIGH):
        factor_descriptions.append((tiers["beta"], f"rolling beta of {rolling_beta:.2f} versus its benchmark"))
    if tiers["downside_capture"] in (RISK_TIER_MEDIUM, RISK_TIER_HIGH):
        factor_descriptions.append(
            (tiers["downside_capture"], f"downside capture of {downside_capture:.0%} versus its benchmark")
        )
    if tiers["stress_concentration"] in (RISK_TIER_MEDIUM, RISK_TIER_HIGH):
        scenario_note = (
            f", most pronounced in the '{worst_scenario_name}' scenario ({worst_stress_gap:+.1%} vs. weight)"
            if worst_scenario_name
            else ""
        )
        factor_descriptions.append(
            (
                tiers["stress_concentration"],
                f"stress-scenario loss share exceeds portfolio weight by {avg_stress_gap:+.1%} on average across "
                f"scenarios{scenario_note}",
            )
        )

    risk_warning = _build_risk_warning(factor_descriptions)

    return {
        "overall_risk_tier": overall_risk_tier,
        "annualized_volatility": annualized_volatility,
        "max_drawdown": max_drawdown,
        "daily_cvar_95": daily_cvar_95,
        "recovery_period_days": recovery_period_days,
        "small_cap_exposure_flag": small_cap_exposure_flag,
        "rolling_beta": rolling_beta,
        "downside_capture": downside_capture,
        "avg_stress_loss_share_minus_weight": avg_stress_gap,
        "benchmark_relative_data_available": benchmark_relative_data_available,
        "risk_warning": risk_warning,
    }


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _build_rationale(
    fund_label: str,
    client_profile: str,
    role: str,
    action: str,
    profile_data: Dict[str, Any],
    largest_loss_scenarios: int,
    total_scenarios: int,
    scenario_type_summary: str,
    portfolio_weight: float,
) -> str:
    weight_sentence = (
        f"In the reference portfolio, {fund_label} carries a {portfolio_weight:.1%} allocation weight. "
        if pd.notna(portfolio_weight)
        else ""
    )
    largest_loss_sentence = (
        f"{fund_label} was the single largest loss contributor in {largest_loss_scenarios} of {total_scenarios} "
        f"modeled stress scenarios ({scenario_type_summary}). "
        if largest_loss_scenarios > 0
        else ""
    )
    benchmark_note = (
        ""
        if profile_data["benchmark_relative_data_available"]
        else "Rolling beta and downside capture were not available for this fund at the time of assessment. "
    )

    article = _article(client_profile)
    return (
        f"For {article} {client_profile} profile, {fund_label}'s trailing historical risk profile is assessed as "
        f"{profile_data['overall_risk_tier']} overall. {profile_data['risk_warning']} {weight_sentence}"
        f"{largest_loss_sentence}{benchmark_note}Relative to {article} {client_profile} investor's typical risk "
        f"tolerance, this maps to a suitability role of '{role}' with a suggested review action of '{action}'. "
        f"{DISCLAIMER}"
    )


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def score_suitability(
    metrics_summary: pd.DataFrame,
    benchmark_metrics: Optional[pd.DataFrame],
    stress_results: pd.DataFrame,
    attribution_results: pd.DataFrame,
    portfolio_weights: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Map risk factors (max drawdown, volatility, Daily CVaR 95, small-cap
    exposure, rolling beta, downside capture, stress loss share, recovery
    period) to client profile fit, role, and recommended action. See the
    module docstring for the full scoring rubric. Produces one row per
    (fund_label, client_profile) pair.
    """
    _enforce_schema(metrics_summary, METRICS_SUMMARY_INPUT_COLUMNS, "metrics_summary")
    _enforce_schema(attribution_results, ATTRIBUTION_RESULTS_INPUT_COLUMNS, "attribution_results")
    _enforce_schema(stress_results, STRESS_RESULTS_INPUT_COLUMNS, "stress_results")

    if portfolio_weights is not None:
        _enforce_schema(portfolio_weights, PORTFOLIO_WEIGHTS_COLUMNS, "portfolio_weights")
        fund_labels = list(portfolio_weights["fund_label"])
        weight_lookup = portfolio_weights.set_index("fund_label")["weight"]
    else:
        fund_labels = list(metrics_summary["fund_label"].unique())
        weight_lookup = pd.Series(dtype=float)

    metrics_by_fund = metrics_summary.set_index("fund_label")

    total_scenarios = stress_results["scenario_name"].nunique()
    scenario_type_counts = stress_results.groupby("scenario_type")["scenario_name"].nunique().to_dict()
    scenario_type_summary = ", ".join(
        f"{SCENARIO_TYPE_LABELS.get(scenario_type, scenario_type.lower())}: {count}"
        for scenario_type, count in scenario_type_counts.items()
    )

    rows: List[Dict[str, Any]] = []
    for fund_label in fund_labels:
        if fund_label not in metrics_by_fund.index:
            warnings.warn(f"'{fund_label}' is in portfolio_weights but missing from metrics_summary; skipped.")
            continue
        metrics_row = metrics_by_fund.loc[fund_label]

        profile_data = _compute_fund_risk_profile(fund_label, metrics_row, benchmark_metrics, attribution_results)

        fund_attribution = attribution_results[attribution_results["fund_label"] == fund_label]
        largest_loss_scenarios = int(fund_attribution["is_largest_loss_contributor"].sum())

        portfolio_weight = float(weight_lookup.get(fund_label, float("nan"))) if not weight_lookup.empty else float("nan")

        for client_profile in CLIENT_PROFILES:
            role, action = _classify_role_and_action(
                profile_data["overall_risk_tier"], client_profile, profile_data["benchmark_relative_data_available"]
            )
            rationale = _build_rationale(
                fund_label,
                client_profile,
                role,
                action,
                profile_data,
                largest_loss_scenarios,
                total_scenarios,
                scenario_type_summary,
                portfolio_weight,
            )
            rows.append(
                {
                    "fund_label": fund_label,
                    "client_profile": client_profile,
                    "suitability_role": role,
                    "risk_warning": profile_data["risk_warning"],
                    "recommended_action": action,
                    "rationale": rationale,
                    "overall_risk_tier": profile_data["overall_risk_tier"],
                    "annualized_volatility": profile_data["annualized_volatility"],
                    "max_drawdown": profile_data["max_drawdown"],
                    "daily_cvar_95": profile_data["daily_cvar_95"],
                    "recovery_period_days": profile_data["recovery_period_days"],
                    "small_cap_exposure_flag": profile_data["small_cap_exposure_flag"],
                    "rolling_beta": profile_data["rolling_beta"],
                    "downside_capture": profile_data["downside_capture"],
                    "avg_stress_loss_share_minus_weight": profile_data["avg_stress_loss_share_minus_weight"],
                    "benchmark_relative_data_available": profile_data["benchmark_relative_data_available"],
                }
            )

    if not rows:
        raise DataValidationError("No suitability rows could be generated (no funds found across metrics_summary/portfolio_weights).")

    return pd.DataFrame(rows)[SUITABILITY_RESULTS_COLUMNS]


def generate_suitability_results(
    metrics_summary: pd.DataFrame,
    benchmark_metrics: Optional[pd.DataFrame],
    stress_results: pd.DataFrame,
    attribution_results: pd.DataFrame,
    portfolio_weights: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Assemble 02_processed_data/suitability_results.csv per this module's scoring rubric."""
    return score_suitability(
        metrics_summary, benchmark_metrics, stress_results, attribution_results, portfolio_weights=portfolio_weights
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _load_metrics_summary() -> pd.DataFrame:
    if not METRICS_SUMMARY_PATH.exists():
        raise DataValidationError(
            f"{METRICS_SUMMARY_PATH} does not exist. Run the metrics engine "
            "(metrics.run_metrics_engine()) before running the suitability engine."
        )
    return pd.read_csv(METRICS_SUMMARY_PATH)


def _load_benchmark_metrics() -> Optional[pd.DataFrame]:
    """benchmark_metrics.csv is optional — if absent, rolling beta / downside
    capture gracefully degrade to "not available" rather than failing the
    whole engine."""
    if not BENCHMARK_METRICS_PATH.exists():
        return None
    return pd.read_csv(BENCHMARK_METRICS_PATH)


def _load_stress_results() -> pd.DataFrame:
    if not STRESS_RESULTS_PATH.exists():
        raise DataValidationError(
            f"{STRESS_RESULTS_PATH} does not exist. Run the stress engine "
            "(stress.run_stress_engine()) before running the suitability engine."
        )
    return pd.read_csv(STRESS_RESULTS_PATH)


def _load_attribution_results() -> pd.DataFrame:
    if not ATTRIBUTION_RESULTS_PATH.exists():
        raise DataValidationError(
            f"{ATTRIBUTION_RESULTS_PATH} does not exist. Run the attribution engine "
            "(attribution.run_attribution_engine()) before running the suitability engine."
        )
    return pd.read_csv(ATTRIBUTION_RESULTS_PATH)


def _load_portfolio_weights() -> pd.DataFrame:
    if not PORTFOLIO_WEIGHTS_PATH.exists():
        raise DataValidationError(f"{PORTFOLIO_WEIGHTS_PATH} does not exist.")
    df = pd.read_csv(PORTFOLIO_WEIGHTS_PATH)
    _enforce_schema(df, PORTFOLIO_WEIGHTS_COLUMNS, "portfolio_weights.csv")
    return df


def run_suitability_engine() -> pd.DataFrame:
    """
    Full entry point: load metrics_summary.csv, benchmark_metrics.csv (if
    present), stress_results.csv, attribution_results.csv, and
    portfolio_weights.csv, score every (fund, client profile) combination,
    and write 02_processed_data/suitability_results.csv.
    """
    metrics_summary = _load_metrics_summary()
    benchmark_metrics = _load_benchmark_metrics()
    stress_results = _load_stress_results()
    attribution_results = _load_attribution_results()
    portfolio_weights = _load_portfolio_weights()

    result = generate_suitability_results(
        metrics_summary,
        benchmark_metrics,
        stress_results,
        attribution_results,
        portfolio_weights=portfolio_weights,
    )

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(SUITABILITY_RESULTS_PATH, index=False)

    return result
