"""
Utility Module — shared constants and helpers used across src/.

Reference: 00_project_control/formula_audit.md §9 (Annualization Factor
Reference) and 00_project_control/model_governance.md.

Scope: pure, Streamlit-agnostic helpers (no file I/O, no network calls, no
`streamlit` import) so they can be reused by data_loader.py, charts.py, the
calculation engines, and the (future) Streamlit pages alike.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

import pandas as pd

TRADING_DAYS_PER_YEAR = 252
MONTHS_PER_YEAR = 12
DEFAULT_RISK_FREE_RATE = 0.06
DATA_START_DATE = "2021-01-01"
CACHE_MAX_AGE_HOURS = 24

REQUIRED_BENCHMARKS = [
    "NIFTY50_TRI",
    "NIFTY100_TRI",
    "NIFTY500_TRI",
    "NIFTYSMALLCAP250_TRI",
    "HYBRID_65_35",
]

CLIENT_PROFILES = ["Conservative", "Balanced", "Growth", "Aggressive"]

# ---------------------------------------------------------------------------
# Disclaimer text — reused verbatim across chart captions, page footers, and
# the Methodology page so the "educational diagnostic, not advice" language
# rule (master_project_instructions.md.md §3, §22) is applied consistently
# rather than re-worded ad hoc on every page.
# ---------------------------------------------------------------------------

EDUCATIONAL_DISCLAIMER = (
    "This dashboard is an educational risk diagnostic tool built on trailing historical data. "
    "It does not constitute investment advice, a recommendation to buy, sell, or hold any "
    "security, or a forecast of future performance. Past performance is not indicative of "
    "future results."
)

STRESS_TEST_DISCLAIMER = (
    "Stress scenarios are illustrative shocks derived from historical replay or hypothetical "
    "assumptions. They are not forecasts or predictions of future performance."
)

BENCHMARK_PROXY_DISCLAIMER = (
    "Some benchmark series shown here may be price-index proxies or disclosed approximations "
    "rather than true Total Return Index (TRI) data. Check the source_quality label on each "
    "series before drawing conclusions from benchmark-relative comparisons."
)

SUITABILITY_DISCLAIMER = (
    "Suitability labels are educational diagnostics derived from trailing historical risk "
    "metrics. They are not investment recommendations and do not account for an investor's "
    "complete financial situation."
)


def annualization_factor(frequency: str) -> float:
    """Return SQRT(252) for 'daily' or SQRT(12) for 'monthly'."""
    frequency_normalized = str(frequency).strip().lower()
    if frequency_normalized == "daily":
        return TRADING_DAYS_PER_YEAR ** 0.5
    if frequency_normalized == "monthly":
        return MONTHS_PER_YEAR ** 0.5
    raise ValueError(f"Unsupported frequency '{frequency}'; expected 'daily' or 'monthly'.")


# ---------------------------------------------------------------------------
# INR formatting
# ---------------------------------------------------------------------------

def _group_indian_digits(integer_digits: str) -> str:
    """Group a string of digits using the Indian numbering convention:
    the last 3 digits form one group, then digits are grouped in pairs
    moving left (e.g. '123456789' -> '12,34,56,789'), unlike the Western
    convention of grouping every 3 digits."""
    if len(integer_digits) <= 3:
        return integer_digits
    last_three = integer_digits[-3:]
    remaining = integer_digits[:-3]
    groups: List[str] = []
    while len(remaining) > 2:
        groups.insert(0, remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        groups.insert(0, remaining)
    groups.append(last_three)
    return ",".join(groups)


def format_inr(value: Optional[float], decimals: int = 0) -> str:
    """
    Format a numeric value as an Indian Rupee currency string using Indian
    digit grouping (e.g. 12345678 -> '₹1,23,45,678'), not the Western
    3-digit grouping a plain f-string comma would produce.

    Returns 'N/A' for None/NaN inputs rather than raising, since this is
    primarily used to render values straight from possibly-missing/empty
    processed data.
    """
    if value is None or pd.isna(value):
        return "N/A"
    is_negative = value < 0
    western_grouped = f"{abs(value):,.{decimals}f}"
    integer_part, _, decimal_part = western_grouped.partition(".")
    grouped_integer = _group_indian_digits(integer_part.replace(",", ""))
    formatted = f"₹{grouped_integer}" + (f".{decimal_part}" if decimal_part else "")
    return f"-{formatted}" if is_negative else formatted


def format_inr_compact(value: Optional[float], decimals: int = 2) -> str:
    """
    Compact Indian Rupee string using Lakh (L) / Crore (Cr) suffixes, e.g.
    12345678 -> '₹1.23 Cr'. Intended for chart titles/annotations/axis
    labels where a fully digit-grouped value would be too long.
    """
    if value is None or pd.isna(value):
        return "N/A"
    is_negative = value < 0
    magnitude = abs(value)
    if magnitude >= 1_00_00_000:
        formatted = f"₹{magnitude / 1_00_00_000:.{decimals}f} Cr"
    elif magnitude >= 1_00_000:
        formatted = f"₹{magnitude / 1_00_000:.{decimals}f} L"
    elif magnitude >= 1_000:
        formatted = f"₹{magnitude / 1_000:.{decimals}f} K"
    else:
        formatted = f"₹{magnitude:.{decimals}f}"
    return f"-{formatted}" if is_negative else formatted


# ---------------------------------------------------------------------------
# Percent formatting
# ---------------------------------------------------------------------------

def format_percent(
    value: Optional[float],
    decimals: int = 1,
    already_percent: bool = False,
    include_sign: bool = False,
) -> str:
    """
    Format a decimal ratio (e.g. 0.125 -> '12.5%') as a percentage string.
    Every ratio-like column in 02_processed_data/ (returns, weights, VaR,
    volatility, ...) is stored as a decimal, so already_percent defaults to
    False; pass True only for values already scaled to percentage units.

    Returns 'N/A' for None/NaN inputs rather than raising.
    """
    if value is None or pd.isna(value):
        return "N/A"
    percent_value = value if already_percent else value * 100
    sign = "+" if include_sign and percent_value > 0 else ""
    return f"{sign}{percent_value:.{decimals}f}%"


# ---------------------------------------------------------------------------
# Safe DataFrame checks
# ---------------------------------------------------------------------------

def is_dataframe_usable(df: Optional[pd.DataFrame]) -> bool:
    """True only if df is an actual non-empty DataFrame. Use this before
    plotting/aggregating data that may come from data_loader.py's
    "missing file -> empty DataFrame" fallback."""
    return isinstance(df, pd.DataFrame) and not df.empty


def has_required_columns(df: Optional[pd.DataFrame], required_columns: Iterable[str]) -> bool:
    """True only if df is a DataFrame containing every column in required_columns."""
    if not isinstance(df, pd.DataFrame):
        return False
    return all(column in df.columns for column in required_columns)


def safe_filter(df: Optional[pd.DataFrame], column: str, value) -> pd.DataFrame:
    """
    Filter df to rows where column == value, never raising even if df is
    None/empty or the column is missing — returns an empty DataFrame
    (preserving df's columns where possible) instead.
    """
    if not isinstance(df, pd.DataFrame) or column not in df.columns:
        return df.iloc[0:0] if isinstance(df, pd.DataFrame) else pd.DataFrame()
    return df[df[column] == value]


def safe_isin(df: Optional[pd.DataFrame], column: str, values: Iterable) -> pd.DataFrame:
    """Filter df to rows where column is in values, never raising even if
    df is None/empty or the column is missing."""
    if not isinstance(df, pd.DataFrame) or column not in df.columns:
        return df.iloc[0:0] if isinstance(df, pd.DataFrame) else pd.DataFrame()
    return df[df[column].isin(list(values))]
