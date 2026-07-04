"""
API Fetch Module — programmatic mutual fund NAV and benchmark data acquisition.

This is the core API-first data acquisition layer. The user does not supply
manual NAV or TRI files; every fund and benchmark series is fetched
programmatically, cached locally, and normalized into the schemas below.

Reference: 00_project_control/master_project_instructions.md.md §11 (Mutual
Fund API Fetch) and §12 (Benchmark API Fetch Module).
Related: 00_project_control/model_governance.md (cache rule, source-quality
labelling, fail-fast rule), 00_project_control/data_dictionary.md (normalized
schemas), 00_project_control/limitations.md (benchmark fetch fragility).

Non-negotiable rules enforced by this module:
- No network requests execute on import. Every fetch is an explicit,
  callable function; nothing runs at module load time.
- The 24-hour cache rule applies to every API call:
    fresh cache          -> use cache
    live fetch succeeds  -> cache it, use it
    live fetch fails + expired cache exists -> use expired cache, warn
    live fetch fails + no cache exists      -> raise DataFetchError
- Mutual fund `source` is always "MFAPI". `source_quality` is one of:
    API_FETCHED_VERIFIED, API_FETCHED_METADATA_WARNING,
    CACHE_FRESH, CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE
- Benchmark data must never silently label a price-index proxy as TRI.
  Any yfinance-sourced series is labelled PRICE_INDEX_PROXY_NOT_TRI and is
  only used if explicitly allowed.
- HYBRID_65_35 is always built internally from NIFTY50_TRI; it is never
  fetched from an external source.
"""

from __future__ import annotations

import json
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Paths (resolved relative to the project root, independent of cwd)
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = _THIS_FILE.parents[2]  # .../src -> .../04_streamlit_app -> project root

CACHE_ROOT = PROJECT_ROOT / "01_raw_data" / "api_cache"
MUTUAL_FUND_CACHE_DIR = CACHE_ROOT / "mutual_funds"
BENCHMARK_CACHE_DIR = CACHE_ROOT / "benchmarks"
METADATA_CACHE_DIR = CACHE_ROOT / "metadata"

SCHEME_MASTER_DIR = PROJECT_ROOT / "01_raw_data" / "scheme_master"
FUND_MASTER_PATH = SCHEME_MASTER_DIR / "fund_master.csv"

PROCESSED_DATA_DIR = PROJECT_ROOT / "02_processed_data"
NAV_DAILY_CLEAN_PATH = PROCESSED_DATA_DIR / "nav_daily_clean.csv"
BENCHMARK_DAILY_PATH = PROCESSED_DATA_DIR / "benchmark_daily.csv"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_MAX_AGE_HOURS = 24
TRADING_DAYS_PER_YEAR = 252
DEFAULT_CASH_RATE = 0.06

MFAPI_BASE_URL = "https://api.mfapi.in/mf/{scheme_code}"

REQUIRED_BENCHMARKS = ["NIFTY50_TRI", "NIFTY100_TRI", "NIFTY500_TRI", "NIFTYSMALLCAP250_TRI"]

# Best-effort mapping to official Nifty Indices display names, used by the
# Priority-1 programmatic TRI fetcher. This endpoint is undocumented and can
# change without notice (see 00_project_control/limitations.md §1.2).
NSE_INDEX_NAME_MAP = {
    "NIFTY50_TRI": "NIFTY 50 TRI",
    "NIFTY100_TRI": "NIFTY 100 TRI",
    "NIFTY500_TRI": "NIFTY 500 TRI",
    "NIFTYSMALLCAP250_TRI": "NIFTY SMALLCAP 250 TRI",
}

# Best-effort mapping for NSE India indices-history endpoints where TRI labels
# are sometimes unavailable but the corresponding price index label exists.
# If this fallback is used, it is explicitly labelled as a proxy (never as TRI).
NSE_INDIA_PRICE_INDEX_NAME_MAP = {
    "NIFTY50_TRI": "NIFTY 50",
    "NIFTY100_TRI": "NIFTY 100",
    "NIFTY500_TRI": "NIFTY 500",
    "NIFTYSMALLCAP250_TRI": "NIFTY SMALLCAP 250",
}

# Yahoo Finance only offers price-index proxies, and only for a subset of
# these benchmarks. Where no reasonable ticker exists, the fallback is simply
# unavailable for that benchmark (we never invent a proxy).
YFINANCE_PROXY_TICKERS = {
    "NIFTY50_TRI": "^NSEI",
    "NIFTY100_TRI": "^CNX100",
    "NIFTY500_TRI": "^CRSLDX",
}

# yfinance fallback must be explicitly enabled; it is never used silently.
ALLOW_YFINANCE_FALLBACK_DEFAULT = False

NIFTY_INDICES_HOME_URL = "https://www.niftyindices.com/reports/historical-data"
NIFTY_INDICES_HISTORICAL_URL = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
NSE_INDIA_HOME_URL = "https://www.nseindia.com/"
NSE_INDIA_HISTORICAL_REFERER_URL = "https://www.nseindia.com/reports-indices-historical-index-data"
NSE_INDIA_HISTORICAL_API_URL = "https://www.nseindia.com/api/historical/indicesHistory"

# --- source labels ---------------------------------------------------------

NAV_SOURCE = "MFAPI"
BENCHMARK_SOURCE_NSE = "NSE_TRI_FETCH"
BENCHMARK_SOURCE_WRAPPER = "NSE_WRAPPER_FETCH"
BENCHMARK_SOURCE_YFINANCE = "YFINANCE"
BENCHMARK_SOURCE_INTERNAL = "INTERNAL_SYNTHETIC_BENCHMARK"

# --- source_quality enums ---------------------------------------------------

SOURCE_QUALITY_API_FETCHED_VERIFIED = "API_FETCHED_VERIFIED"
SOURCE_QUALITY_API_FETCHED_METADATA_WARNING = "API_FETCHED_METADATA_WARNING"
SOURCE_QUALITY_CACHE_FRESH = "CACHE_FRESH"
SOURCE_QUALITY_CACHE_EXPIRED = "CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE"
SOURCE_QUALITY_PRICE_INDEX_PROXY_NOT_TRI = "PRICE_INDEX_PROXY_NOT_TRI"
SOURCE_QUALITY_DISCLOSED_APPROXIMATION = "DISCLOSED_APPROXIMATION"

# --- verification_status enums (persisted back to fund_master.csv) ---------

VERIFICATION_STATUS_NEEDS_VERIFICATION = "NEEDS_API_METADATA_VERIFICATION"
VERIFICATION_STATUS_VERIFIED = "VERIFIED_VIA_MFAPI_METADATA"
VERIFICATION_STATUS_FAILED = "FAILED_METADATA_CHECK"

# --- normalized schemas (data_dictionary.md §3) -----------------------------

NAV_SCHEMA_COLUMNS = ["date", "fund_label", "scheme_code", "scheme_name", "nav", "source", "source_quality"]
BENCHMARK_SCHEMA_COLUMNS = ["date", "benchmark_label", "tri_value", "source", "source_quality"]


class DataFetchError(Exception):
    """
    Raised when a live fetch fails and no usable cache exists.

    This is the fail-fast rule from master_project_instructions.md.md §4 and
    §12.3: never invent data, never silently substitute a lower-quality
    source without labelling it, and raise a clear error when no valid data
    can be produced.
    """


class SchemaValidationError(Exception):
    """Raised when a DataFrame does not satisfy a required output schema."""


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_file_path(cache_dir: Path, key: str) -> Path:
    """Build a safe cache file path for a given cache directory and key."""
    safe_key = re.sub(r"[^A-Za-z0-9_.-]", "_", str(key))
    return cache_dir / f"{safe_key}.json"


def _read_cache_envelope(cache_path: Path) -> Optional[Dict[str, Any]]:
    """Read a cache envelope ({fetched_at, payload}) from disk, or None."""
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as fh:
            envelope = json.load(fh)
        if "fetched_at" not in envelope or "payload" not in envelope:
            return None
        return envelope
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache_envelope(cache_path: Path, payload: Dict[str, Any]) -> None:
    """Write a payload to disk wrapped in a {fetched_at, payload} envelope."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(envelope, fh, indent=2, default=str)


def _envelope_age_hours(envelope: Dict[str, Any]) -> float:
    """Age of a cache envelope in hours."""
    fetched_at = datetime.fromisoformat(envelope["fetched_at"])
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - fetched_at
    return delta.total_seconds() / 3600


def _is_envelope_fresh(envelope: Optional[Dict[str, Any]], max_age_hours: int) -> bool:
    if envelope is None:
        return False
    return _envelope_age_hours(envelope) < max_age_hours


def validate_cache(cache_path: str, max_age_hours: int = CACHE_MAX_AGE_HOURS) -> bool:
    """
    Public cache-validation helper: True if a cache file exists at
    `cache_path` and is within `max_age_hours` of its fetch time.
    See model_governance.md §3.1 for the full cache decision rule.
    """
    envelope = _read_cache_envelope(Path(cache_path))
    return _is_envelope_fresh(envelope, max_age_hours)


def cache_exists(cache_path: str) -> bool:
    """True if any cache file (fresh or expired) exists at `cache_path`."""
    return Path(cache_path).exists()


# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------

def validate_schema(df: pd.DataFrame, required_columns: List[str]) -> bool:
    """
    Confirm a DataFrame contains every column in `required_columns` before
    it is cached or written to 02_processed_data/. Raises
    SchemaValidationError on any missing column.
    """
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise SchemaValidationError(f"DataFrame is missing required columns: {missing}")
    return True


def validate_nav_dataframe(df: pd.DataFrame) -> bool:
    """Validate a DataFrame against the normalized mutual fund NAV schema."""
    return validate_schema(df, NAV_SCHEMA_COLUMNS)


def validate_benchmark_dataframe(df: pd.DataFrame) -> bool:
    """Validate a DataFrame against the normalized benchmark schema."""
    return validate_schema(df, BENCHMARK_SCHEMA_COLUMNS)


# ---------------------------------------------------------------------------
# Source quality labelling
# ---------------------------------------------------------------------------

def label_source_quality(is_live_fetch: bool, is_cache_fresh: bool, metadata_ok: bool) -> str:
    """
    Return the correct mutual-fund source_quality enum value.

    Precedence: an unexpired cache read (no live fetch attempted) is
    CACHE_FRESH. A successful live fetch is API_FETCHED_VERIFIED or
    API_FETCHED_METADATA_WARNING depending on scheme-name verification.
    Anything else (live fetch failed, falling back to disk) is
    CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE.
    """
    if is_cache_fresh and not is_live_fetch:
        return SOURCE_QUALITY_CACHE_FRESH
    if is_live_fetch:
        return SOURCE_QUALITY_API_FETCHED_VERIFIED if metadata_ok else SOURCE_QUALITY_API_FETCHED_METADATA_WARNING
    return SOURCE_QUALITY_CACHE_EXPIRED


# ---------------------------------------------------------------------------
# Scheme metadata verification
# ---------------------------------------------------------------------------

# Generic plan/option filler words that vary across MFAPI's inconsistent
# naming conventions (e.g. "... Direct Growth" vs "... Growth Option -
# Direct" vs "... Direct Plan - Growth") but do not identify *which*
# underlying scheme a NAV series belongs to. Excluded from the significant-
# token comparison in verify_scheme_metadata() below.
_SCHEME_NAME_NOISE_WORDS = {
    "fund", "plan", "plans", "direct", "regular", "growth", "option", "options",
    "scheme", "idcw", "dividend", "reinvestment", "payout",
}


def _significant_tokens(name: str) -> set:
    words = re.findall(r"[a-z0-9]+", str(name).lower())
    return {word for word in words if word not in _SCHEME_NAME_NOISE_WORDS}


def verify_scheme_metadata(expected_scheme_name: str, returned_scheme_name: str) -> bool:
    """
    Token-set based, case/punctuation/word-order-insensitive match between
    the expected scheme name (from fund_master.csv) and the scheme name
    actually returned by MFAPI. Returns True if the match is acceptable,
    False if the mismatch should be treated as material.

    MFAPI scheme names carry inconsistent formatting for the very same
    underlying scheme (word order and filler words like "Plan"/"Option"
    vary). Comparing normalized strings via substring containment breaks on
    this reordering (e.g. "...Direct Growth" is not a substring of
    "...Growth Option- Direct"), so instead we strip generic plan/option
    filler words and compare the remaining *significant* tokens (fund
    house, scheme name, category) as sets. A match is accepted if one
    token set is a subset of the other, i.e. every substantive identifying
    word on one side also appears on the other side. This is intentionally
    conservative in the sense that matters for the fail-fast governance
    rule: two schemes with no overlapping significant tokens (a genuinely
    different fund house / strategy) are still correctly rejected.
    """
    expected_tokens = _significant_tokens(expected_scheme_name)
    returned_tokens = _significant_tokens(returned_scheme_name)
    if not expected_tokens or not returned_tokens:
        return False
    return expected_tokens.issubset(returned_tokens) or returned_tokens.issubset(expected_tokens)


def update_fund_master_verification_status(fund_label: str, verification_status: str) -> None:
    """
    Persist the outcome of scheme metadata verification back to
    fund_master.csv for the given fund_label. This is the field that
    model_governance.md's publication gate checks (no fund may remain
    NEEDS_API_METADATA_VERIFICATION or FAILED_METADATA_CHECK at publication).
    """
    if not FUND_MASTER_PATH.exists():
        return
    fund_master = pd.read_csv(FUND_MASTER_PATH)
    if "fund_label" not in fund_master.columns or "verification_status" not in fund_master.columns:
        return
    mask = fund_master["fund_label"] == fund_label
    if mask.any():
        fund_master.loc[mask, "verification_status"] = verification_status
        fund_master.to_csv(FUND_MASTER_PATH, index=False)


def _write_metadata_cache(
    scheme_code: str,
    fund_label: str,
    expected_scheme_name: str,
    returned_scheme_name: str,
    verification_status: str,
) -> None:
    cache_path = _cache_file_path(METADATA_CACHE_DIR, scheme_code)
    _write_cache_envelope(
        cache_path,
        {
            "fund_label": fund_label,
            "scheme_code": str(scheme_code),
            "expected_scheme_name": expected_scheme_name,
            "returned_scheme_name": returned_scheme_name,
            "verification_status": verification_status,
        },
    )


# ---------------------------------------------------------------------------
# Shared HTTP session
# ---------------------------------------------------------------------------

def _build_requests_session() -> requests.Session:
    """A requests session with defensive headers and retry/backoff logic."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "MF-Risk-Diagnostic-Module/1.0 (+educational-analytics-project)"
            ),
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        }
    )
    return session


# ---------------------------------------------------------------------------
# Mutual fund NAV fetch (MFAPI)
# ---------------------------------------------------------------------------

def _fetch_mfapi_raw(scheme_code: str, timeout: int = 15) -> Dict[str, Any]:
    """Raw call to https://api.mfapi.in/mf/{scheme_code}. Raises on failure."""
    url = MFAPI_BASE_URL.format(scheme_code=scheme_code)
    session = _build_requests_session()
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or "data" not in payload or not payload.get("data"):
        raise DataFetchError(f"MFAPI returned an empty or unexpected payload for scheme_code={scheme_code}")
    return payload


def _normalize_mfapi_payload(payload: Dict[str, Any], fund_label: str, scheme_code: str) -> pd.DataFrame:
    """Convert a raw MFAPI payload into the normalized NAV schema (pre source columns)."""
    meta = payload.get("meta", {}) or {}
    scheme_name = meta.get("scheme_name", "")
    records = payload.get("data", [])
    if not records:
        raise DataFetchError(f"MFAPI payload for scheme_code={scheme_code} has no NAV observations")

    df = pd.DataFrame(records)
    if "date" not in df.columns or "nav" not in df.columns:
        raise DataFetchError(f"MFAPI payload for scheme_code={scheme_code} is missing date/nav fields")

    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df = df.dropna(subset=["date", "nav"])
    if df.empty:
        raise DataFetchError(f"MFAPI payload for scheme_code={scheme_code} had no parseable NAV rows")

    df["fund_label"] = fund_label
    df["scheme_code"] = str(scheme_code)
    df["scheme_name"] = scheme_name
    df = df.sort_values("date").drop_duplicates(subset="date", keep="last").reset_index(drop=True)
    return df[["date", "fund_label", "scheme_code", "scheme_name", "nav"]]


def fetch_mutual_fund_nav(scheme_code: str, fund_label: str, expected_scheme_name: str) -> pd.DataFrame:
    """
    Fetch historical NAV data from MFAPI with 24-hour cache.

    Cache decision sequence (model_governance.md §3.1):
        fresh cache               -> use cache (source_quality = CACHE_FRESH)
        else live fetch succeeds  -> verify metadata, cache, use it
        else live fetch fails and cache (any age) exists -> use expired cache with warning
        else live fetch fails and no cache exists -> raise DataFetchError

    Return normalized schema:
    date, fund_label, scheme_code, scheme_name, nav, source, source_quality
    """
    scheme_code = str(scheme_code)
    cache_path = _cache_file_path(MUTUAL_FUND_CACHE_DIR, scheme_code)
    cached_envelope = _read_cache_envelope(cache_path)

    if _is_envelope_fresh(cached_envelope, CACHE_MAX_AGE_HOURS):
        df = _normalize_mfapi_payload(cached_envelope["payload"], fund_label, scheme_code)
        df["source"] = NAV_SOURCE
        df["source_quality"] = SOURCE_QUALITY_CACHE_FRESH
        return df[NAV_SCHEMA_COLUMNS]

    try:
        payload = _fetch_mfapi_raw(scheme_code)
    except (requests.RequestException, DataFetchError, ValueError) as exc:
        if cached_envelope is not None:
            warnings.warn(
                f"Live MFAPI fetch failed for '{fund_label}' (scheme_code={scheme_code}): {exc}. "
                "Using expired cache instead."
            )
            df = _normalize_mfapi_payload(cached_envelope["payload"], fund_label, scheme_code)
            df["source"] = NAV_SOURCE
            df["source_quality"] = SOURCE_QUALITY_CACHE_EXPIRED
            return df[NAV_SCHEMA_COLUMNS]
        raise DataFetchError(
            f"Live MFAPI fetch failed for '{fund_label}' (scheme_code={scheme_code}) and no cache "
            f"exists. Refusing to invent NAV data (fail-fast rule). Underlying error: {exc}"
        ) from exc

    returned_scheme_name = (payload.get("meta", {}) or {}).get("scheme_name", "")
    metadata_ok = verify_scheme_metadata(expected_scheme_name, returned_scheme_name)
    verification_status = VERIFICATION_STATUS_VERIFIED if metadata_ok else VERIFICATION_STATUS_FAILED
    update_fund_master_verification_status(fund_label, verification_status)
    _write_metadata_cache(scheme_code, fund_label, expected_scheme_name, returned_scheme_name, verification_status)

    if not metadata_ok:
        warnings.warn(
            f"Scheme metadata mismatch for '{fund_label}' (scheme_code={scheme_code}): "
            f"expected '{expected_scheme_name}', MFAPI returned '{returned_scheme_name}'."
        )

    _write_cache_envelope(cache_path, payload)

    df = _normalize_mfapi_payload(payload, fund_label, scheme_code)
    df["source"] = NAV_SOURCE
    df["source_quality"] = label_source_quality(is_live_fetch=True, is_cache_fresh=False, metadata_ok=metadata_ok)
    return df[NAV_SCHEMA_COLUMNS]


def fetch_all_mutual_funds() -> pd.DataFrame:
    """
    Read fund_master.csv, fetch NAV history for every included fund, validate
    schema, and write 02_processed_data/nav_daily_clean.csv.

    A fund whose fetch fails (no live data and no cache) is skipped with a
    warning rather than aborting the whole run; if every fund fails, this
    raises DataFetchError.
    """
    if not FUND_MASTER_PATH.exists():
        raise DataFetchError(f"fund_master.csv not found at {FUND_MASTER_PATH}")

    fund_master = pd.read_csv(FUND_MASTER_PATH)
    validate_schema(fund_master, ["fund_label", "scheme_code", "expected_scheme_name", "include"])

    included = fund_master[fund_master["include"].astype(str).str.upper() == "TRUE"]
    if included.empty:
        raise DataFetchError("No funds are marked include=TRUE in fund_master.csv")

    frames: List[pd.DataFrame] = []
    errors: List[str] = []
    for _, row in included.iterrows():
        try:
            df = fetch_mutual_fund_nav(
                scheme_code=str(row["scheme_code"]),
                fund_label=row["fund_label"],
                expected_scheme_name=row["expected_scheme_name"],
            )
            frames.append(df)
        except DataFetchError as exc:
            errors.append(f"{row['fund_label']}: {exc}")

    if not frames:
        raise DataFetchError(f"Failed to fetch NAV data for every fund in fund_master.csv: {errors}")

    combined = pd.concat(frames, ignore_index=True)
    validate_nav_dataframe(combined)
    combined = combined[NAV_SCHEMA_COLUMNS].sort_values(["fund_label", "date"]).reset_index(drop=True)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_csv(NAV_DAILY_CLEAN_PATH, index=False)

    if errors:
        warnings.warn(f"fetch_all_mutual_funds completed with {len(errors)} fund(s) failing: {errors}")

    return combined


# ---------------------------------------------------------------------------
# Benchmark fetch — Priority 1: NSE / Nifty Indices programmatic TRI fetch
# ---------------------------------------------------------------------------

def _fetch_nse_tri_raw(benchmark_label: str, start_date: str = "01-Jan-2021") -> Optional[pd.DataFrame]:
    """
    Best-effort programmatic fetch of official NSE/Nifty Indices TRI history.

    This targets niftyindices.com's historical-data endpoint using a
    requests session with browser-like headers and retry/backoff logic, per
    master_project_instructions.md.md §4.2 Priority 1. The endpoint is
    undocumented, session/cookie-dependent, and can change or rate-limit
    without notice (see 00_project_control/limitations.md §1.2). Any failure
    here returns None so the caller can fall through the source hierarchy —
    it never raises and never fabricates data.
    """
    index_name = NSE_INDEX_NAME_MAP.get(benchmark_label)
    if index_name is None:
        return None

    end_date = datetime.now().strftime("%d-%b-%Y")
    session = _build_requests_session()
    session.headers.update(
        {
            "Referer": NIFTY_INDICES_HOME_URL,
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
    )

    try:
        session.get(NIFTY_INDICES_HOME_URL, timeout=15)  # establish session cookies

        cinfo = json.dumps(
            {
                "name": index_name,
                "startDate": start_date,
                "endDate": end_date,
                "indexName": index_name,
            }
        )
        response = session.post(
            NIFTY_INDICES_HISTORICAL_URL,
            data=json.dumps({"cinfo": cinfo}),
            timeout=20,
        )
        response.raise_for_status()

        outer = response.json()
        inner_raw = outer.get("d") if isinstance(outer, dict) else None
        if inner_raw is None:
            return None
        inner = json.loads(inner_raw) if isinstance(inner_raw, str) else inner_raw
        rows = inner.get("data", inner) if isinstance(inner, dict) else inner

        df = pd.DataFrame(rows)
        if df.empty:
            return None

        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        value_col = next(
            (c for c in df.columns if any(token in c.lower() for token in ("close", "tri", "index"))),
            None,
        )
        if date_col is None or value_col is None:
            return None

        df["date"] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
        df["tri_value"] = pd.to_numeric(df[value_col], errors="coerce")
        df = df.dropna(subset=["date", "tri_value"]).sort_values("date").reset_index(drop=True)
        if df.empty:
            return None

        df["benchmark_label"] = benchmark_label
        return df[["date", "benchmark_label", "tri_value"]]

    except Exception as exc:  # noqa: BLE001 - deliberate: any failure here is a fallback trigger
        warnings.warn(f"Priority-1 NSE/Nifty Indices TRI fetch failed for {benchmark_label}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Benchmark fetch — Priority 2: maintained Python wrapper/scraper
# ---------------------------------------------------------------------------

def _fetch_benchmark_via_wrapper(benchmark_label: str) -> Optional[pd.DataFrame]:
    """
    Priority-2 fallback scraper for NSE India index-history endpoints.
    This path exists specifically for cases where niftyindices Priority-1
    endpoint is unavailable.

    It attempts:
      1) TRI index name (e.g. "NIFTY SMALLCAP 250 TRI")
      2) non-TRI index name (e.g. "NIFTY SMALLCAP 250") as a last resort

    Return schema is always normalized to [date, benchmark_label, tri_value].
    If a non-TRI fallback is used, the returned DataFrame carries an attrs
    hint (`source_quality_hint = PRICE_INDEX_PROXY_NOT_TRI`) so caller logic
    can label it transparently (never as official TRI).
    """
    def _normalize_nse_india_history_rows(
        rows: List[Dict[str, Any]], benchmark_label: str
    ) -> Optional[pd.DataFrame]:
        if not rows:
            return None

        df = pd.DataFrame(rows)
        if df.empty:
            return None

        date_candidates = [
            "CH_TIMESTAMP",
            "HistoricalDate",
            "historicalDate",
            "Date",
            "date",
            "TIMESTAMP",
        ]
        date_col = next((column for column in date_candidates if column in df.columns), None)
        if date_col is None:
            date_col = next((column for column in df.columns if "date" in column.lower()), None)
        if date_col is None:
            return None

        tri_preferred_patterns = ("tri", "total return", "tr index", "totalreturns")
        close_fallback_patterns = ("close", "index value", "index_val", "last", "ltp")

        value_col = None
        for pattern in tri_preferred_patterns:
            value_col = next((column for column in df.columns if pattern in column.lower()), None)
            if value_col:
                break
        if value_col is None:
            for pattern in close_fallback_patterns:
                value_col = next((column for column in df.columns if pattern in column.lower()), None)
                if value_col:
                    break
        if value_col is None:
            return None

        normalized = pd.DataFrame(
            {
                "date": pd.to_datetime(df[date_col], errors="coerce", dayfirst=True),
                "benchmark_label": benchmark_label,
                "tri_value": pd.to_numeric(df[value_col], errors="coerce"),
            }
        )
        normalized = (
            normalized.dropna(subset=["date", "tri_value"])
            .drop_duplicates(subset=["date"])
            .sort_values("date")
            .reset_index(drop=True)
        )
        if normalized.empty:
            return None
        return normalized[["date", "benchmark_label", "tri_value"]]

    def _fetch_nse_india_indices_history(index_type: str, benchmark_label: str) -> Optional[pd.DataFrame]:
        session = _build_requests_session()
        session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Referer": NSE_INDIA_HISTORICAL_REFERER_URL,
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        end_date = datetime.now().strftime("%d-%m-%Y")
        params = {
            "indexType": index_type,
            "from": "01-01-2021",
            "to": end_date,
        }

        try:
            # Warm-up requests to establish anti-bot/session cookies.
            session.get(NSE_INDIA_HOME_URL, timeout=15)
            session.get(NSE_INDIA_HISTORICAL_REFERER_URL, timeout=15)

            response = session.get(NSE_INDIA_HISTORICAL_API_URL, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("data", []) if isinstance(payload, dict) else []
            return _normalize_nse_india_history_rows(rows, benchmark_label)
        except Exception as exc:  # noqa: BLE001 - expected to fail intermittently due anti-bot/rate-limits
            warnings.warn(
                f"NSE India wrapper fetch failed for '{benchmark_label}' "
                f"(indexType='{index_type}'): {exc}"
            )
            return None

    tri_index_name = NSE_INDEX_NAME_MAP.get(benchmark_label)
    if tri_index_name:
        tri_df = _fetch_nse_india_indices_history(tri_index_name, benchmark_label)
        if tri_df is not None:
            return tri_df

    price_index_name = NSE_INDIA_PRICE_INDEX_NAME_MAP.get(benchmark_label)
    if price_index_name:
        proxy_df = _fetch_nse_india_indices_history(price_index_name, benchmark_label)
        if proxy_df is not None:
            proxy_df.attrs["source_quality_hint"] = SOURCE_QUALITY_PRICE_INDEX_PROXY_NOT_TRI
            warnings.warn(
                f"Wrapper fallback for '{benchmark_label}' used NSE India price-index "
                "history (non-TRI). Labelled PRICE_INDEX_PROXY_NOT_TRI."
            )
            return proxy_df

    return None


# ---------------------------------------------------------------------------
# Benchmark fetch — Priority 3: yfinance price-index proxy (explicit opt-in)
# ---------------------------------------------------------------------------

def _fetch_yfinance_price_index(benchmark_label: str, start_date: str = "2021-01-01") -> Optional[pd.DataFrame]:
    """
    Price-index proxy fallback via yfinance. Only called when explicitly
    allowed by the caller. Never labelled as TRI — the caller assigns
    source_quality = PRICE_INDEX_PROXY_NOT_TRI to anything returned here.
    """
    ticker_symbol = YFINANCE_PROXY_TICKERS.get(benchmark_label)
    if ticker_symbol is None:
        return None

    try:
        import yfinance as yf  # imported lazily: heavy dependency, network-capable

        history = yf.Ticker(ticker_symbol).history(start=start_date)
        if history is None or history.empty:
            return None

        df = history.reset_index()[["Date", "Close"]].rename(columns={"Date": "date", "Close": "tri_value"})
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df["benchmark_label"] = benchmark_label
        return df[["date", "benchmark_label", "tri_value"]]
    except Exception as exc:  # noqa: BLE001 - deliberate: any failure here is a fallback trigger
        warnings.warn(f"yfinance price-index fallback failed for {benchmark_label} ({ticker_symbol}): {exc}")
        return None


# ---------------------------------------------------------------------------
# Benchmark fetch — orchestration
# ---------------------------------------------------------------------------

# source_quality values that disclose something about the *nature* of the
# underlying data (not a true TRI series, or an internally synthesized
# approximation). These disclosures are more important than cache freshness
# and must never be silently replaced by a generic CACHE_FRESH /
# CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE label when the value is re-served
# from cache.
DISCLOSURE_PRESERVING_SOURCE_QUALITIES = {
    SOURCE_QUALITY_PRICE_INDEX_PROXY_NOT_TRI,
    SOURCE_QUALITY_DISCLOSED_APPROXIMATION,
}


def _resolve_cached_benchmark_source_quality(original_source_quality: str, cache_state_quality: str) -> str:
    """
    Decide the source_quality to report when a benchmark is served from
    cache (fresh or expired).

    A cache read must never erase a standing disclosure: if the cached
    value was originally sourced as a price-index proxy
    (PRICE_INDEX_PROXY_NOT_TRI) or an internally synthesized approximation
    (DISCLOSED_APPROXIMATION), that label is preserved as-is. Only a
    genuinely-fetched TRI series (e.g. API_FETCHED_VERIFIED) is relabelled
    with the generic cache-state quality (CACHE_FRESH or
    CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE).
    """
    if original_source_quality in DISCLOSURE_PRESERVING_SOURCE_QUALITIES:
        return original_source_quality
    return cache_state_quality


def _benchmark_df_from_cache_payload(payload: Dict[str, Any], cache_state_quality: str) -> pd.DataFrame:
    """
    Build a benchmark DataFrame from a cached payload envelope.

    `cache_state_quality` is the default label for this cache read
    (CACHE_FRESH or CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE). See
    _resolve_cached_benchmark_source_quality() for why a proxy/approximation
    disclosure on the cached payload takes precedence over this default.
    """
    records = payload.get("records", [])
    df = pd.DataFrame(records)
    if df.empty:
        raise DataFetchError("Cached benchmark payload contains no records")

    original_source_quality = payload.get("source_quality", "")
    resolved_source_quality = _resolve_cached_benchmark_source_quality(original_source_quality, cache_state_quality)

    df["date"] = pd.to_datetime(df["date"])
    df["source"] = payload.get("source", "UNKNOWN")
    df["source_quality"] = resolved_source_quality
    return df[BENCHMARK_SCHEMA_COLUMNS]


def fetch_benchmark_series(benchmark_label: str, allow_yfinance_fallback: Optional[bool] = None) -> pd.DataFrame:
    """
    Fetch benchmark/index data programmatically, validate schema, cache
    output, and return date, benchmark_label, tri_value, source,
    source_quality.

    Source hierarchy (master_project_instructions.md.md §4.2 / §12.3):
        1. Direct NSE / Nifty Indices programmatic TRI fetch
        2. Maintained Python wrapper/scraper, if available
        3. yfinance price-index fallback, only if `allow_yfinance_fallback`
           is True (labelled PRICE_INDEX_PROXY_NOT_TRI, never as TRI)
        4. Fail fast (DataFetchError) if no source succeeds and no cache
           exists; use an expired cache with a warning if one does exist.

    Cache accuracy rule: whether a cached value is read fresh or reused
    after an expired/failed live fetch, a standing PRICE_INDEX_PROXY_NOT_TRI
    or DISCLOSED_APPROXIMATION disclosure on that cached value is always
    preserved. It is never silently replaced by a generic CACHE_FRESH or
    CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE label — see
    _resolve_cached_benchmark_source_quality().

    HYBRID_65_35 is not fetched here — call build_hybrid_65_35() instead.
    """
    if benchmark_label == "HYBRID_65_35":
        raise ValueError(
            "HYBRID_65_35 is built internally via build_hybrid_65_35(); it is "
            "not fetched from an external source. Use fetch_all_benchmarks() "
            "to build it as part of the full benchmark pipeline."
        )

    if allow_yfinance_fallback is None:
        allow_yfinance_fallback = ALLOW_YFINANCE_FALLBACK_DEFAULT

    cache_path = _cache_file_path(BENCHMARK_CACHE_DIR, benchmark_label)
    cached_envelope = _read_cache_envelope(cache_path)

    if _is_envelope_fresh(cached_envelope, CACHE_MAX_AGE_HOURS):
        # CACHE_FRESH is only the *default* label here — a standing proxy or
        # approximation disclosure on the cached payload takes precedence.
        return _benchmark_df_from_cache_payload(cached_envelope["payload"], SOURCE_QUALITY_CACHE_FRESH)

    df: Optional[pd.DataFrame] = None
    source = ""
    source_quality = ""

    df = _fetch_nse_tri_raw(benchmark_label)
    if df is not None:
        source, source_quality = BENCHMARK_SOURCE_NSE, SOURCE_QUALITY_API_FETCHED_VERIFIED

    if df is None:
        df = _fetch_benchmark_via_wrapper(benchmark_label)
        if df is not None:
            source = BENCHMARK_SOURCE_WRAPPER
            source_quality = df.attrs.get("source_quality_hint", SOURCE_QUALITY_API_FETCHED_VERIFIED)

    if df is None and allow_yfinance_fallback:
        df = _fetch_yfinance_price_index(benchmark_label)
        if df is not None:
            source, source_quality = BENCHMARK_SOURCE_YFINANCE, SOURCE_QUALITY_PRICE_INDEX_PROXY_NOT_TRI
            warnings.warn(
                f"'{benchmark_label}' was sourced from a Yahoo Finance price-index proxy, not an "
                "official Total Returns Index. It is labelled PRICE_INDEX_PROXY_NOT_TRI."
            )

    if df is not None and not df.empty:
        cache_payload = {
            "records": df.assign(date=df["date"].dt.strftime("%Y-%m-%d")).to_dict(orient="records"),
            "source": source,
            "source_quality": source_quality,
        }
        _write_cache_envelope(cache_path, cache_payload)

        df = df.copy()
        df["source"] = source
        df["source_quality"] = source_quality
        return df[BENCHMARK_SCHEMA_COLUMNS]

    if cached_envelope is not None:
        cached_source_quality = cached_envelope["payload"].get("source_quality", "")
        if cached_source_quality in DISCLOSURE_PRESERVING_SOURCE_QUALITIES:
            warnings.warn(
                f"Live benchmark fetch failed for '{benchmark_label}'. Using expired cache instead, "
                f"which itself carries the disclosure '{cached_source_quality}' — that disclosure is "
                "preserved and is not overwritten by a generic expired-cache label."
            )
        else:
            warnings.warn(f"Live benchmark fetch failed for '{benchmark_label}'. Using expired cache instead.")
        return _benchmark_df_from_cache_payload(cached_envelope["payload"], SOURCE_QUALITY_CACHE_EXPIRED)

    sources_tried = "NSE TRI fetch, wrapper fallback" + (
        ", yfinance proxy" if allow_yfinance_fallback else " (yfinance fallback disabled)"
    )
    raise DataFetchError(
        f"Could not fetch benchmark '{benchmark_label}' from any configured source ({sources_tried}) "
        "and no cache exists. Refusing to invent benchmark values (fail-fast rule)."
    )


def fetch_all_benchmarks(allow_yfinance_fallback: Optional[bool] = None) -> pd.DataFrame:
    """
    Fetch all required benchmarks (NIFTY50_TRI, NIFTY100_TRI, NIFTY500_TRI,
    NIFTYSMALLCAP250_TRI), build HYBRID_65_35 from the fetched NIFTY50_TRI
    series, validate schema, and write 02_processed_data/benchmark_daily.csv.
    """
    frames: List[pd.DataFrame] = []
    errors: List[str] = []
    nifty50_df: Optional[pd.DataFrame] = None
    nifty500_df: Optional[pd.DataFrame] = None
    smallcap250_df: Optional[pd.DataFrame] = None

    for benchmark_label in REQUIRED_BENCHMARKS:
        try:
            df = fetch_benchmark_series(benchmark_label, allow_yfinance_fallback=allow_yfinance_fallback)
            frames.append(df)
            if benchmark_label == "NIFTY50_TRI":
                nifty50_df = df
            if benchmark_label == "NIFTY500_TRI":
                nifty500_df = df
            if benchmark_label == "NIFTYSMALLCAP250_TRI":
                smallcap250_df = df
        except DataFetchError as exc:
            errors.append(f"{benchmark_label}: {exc}")

    if nifty50_df is None:
        raise DataFetchError(
            f"Cannot build HYBRID_65_35 because NIFTY50_TRI could not be fetched. Errors so far: {errors}"
        )

    hybrid_df = build_hybrid_65_35(nifty50_df)
    frames.append(hybrid_df)

    if smallcap250_df is None:
        if nifty500_df is not None:
            smallcap_proxy_df = build_smallcap250_proxy_from_nifty500(nifty500_df)
            frames.append(smallcap_proxy_df)
            errors = [entry for entry in errors if not entry.startswith("NIFTYSMALLCAP250_TRI:")]
            warnings.warn(
                "NIFTYSMALLCAP250_TRI could not be fetched from configured sources. "
                "Used disclosed internal approximation from NIFTY500_TRI returns "
                "(source=INTERNAL_SYNTHETIC_BENCHMARK, source_quality=DISCLOSED_APPROXIMATION)."
            )
        else:
            warnings.warn(
                "NIFTYSMALLCAP250_TRI could not be fetched and NIFTY500_TRI was unavailable, "
                "so no disclosed approximation could be built either."
            )

    combined = pd.concat(frames, ignore_index=True)
    validate_benchmark_dataframe(combined)
    combined = combined[BENCHMARK_SCHEMA_COLUMNS].sort_values(["benchmark_label", "date"]).reset_index(drop=True)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_csv(BENCHMARK_DAILY_PATH, index=False)

    if errors:
        warnings.warn(f"fetch_all_benchmarks completed with {len(errors)} benchmark(s) failing: {errors}")

    return combined


# ---------------------------------------------------------------------------
# Hybrid benchmark construction
# ---------------------------------------------------------------------------

def build_hybrid_65_35(nifty50_tri: pd.DataFrame, cash_rate: float = DEFAULT_CASH_RATE) -> pd.DataFrame:
    """
    Build HYBRID_65_35 using:
    Hybrid Return_t = 0.65 * NIFTY50_TRI_Return_t + 0.35 * (cash_rate / 252)

    Synthetic index level:
        HYBRID_65_35_Value_0 = 100
        HYBRID_65_35_Value_t = HYBRID_65_35_Value_(t-1) * (1 + Hybrid Return_t)

    HYBRID_65_35 is a disclosed blended proxy, not an official benchmark
    (source = INTERNAL_SYNTHETIC_BENCHMARK, source_quality =
    DISCLOSED_APPROXIMATION).
    """
    validate_schema(nifty50_tri, ["date", "tri_value"])

    base = (
        nifty50_tri[["date", "tri_value"]]
        .assign(date=lambda d: pd.to_datetime(d["date"]))
        .drop_duplicates(subset="date")
        .sort_values("date")
        .reset_index(drop=True)
    )

    nifty_daily_return = base["tri_value"] / base["tri_value"].shift(1) - 1
    hybrid_return = 0.65 * nifty_daily_return + 0.35 * (cash_rate / TRADING_DAYS_PER_YEAR)
    hybrid_return.iloc[0] = 0.0  # first observation anchors HYBRID_65_35_Value_0 = 100

    hybrid_value = 100.0 * (1 + hybrid_return.fillna(0.0)).cumprod()

    hybrid_df = pd.DataFrame(
        {
            "date": base["date"],
            "benchmark_label": "HYBRID_65_35",
            "tri_value": hybrid_value,
            "source": BENCHMARK_SOURCE_INTERNAL,
            "source_quality": SOURCE_QUALITY_DISCLOSED_APPROXIMATION,
        }
    )

    cache_path = _cache_file_path(BENCHMARK_CACHE_DIR, "HYBRID_65_35")
    cache_payload = {
        "records": hybrid_df.assign(date=hybrid_df["date"].dt.strftime("%Y-%m-%d")).to_dict(orient="records"),
        "source": BENCHMARK_SOURCE_INTERNAL,
        "source_quality": SOURCE_QUALITY_DISCLOSED_APPROXIMATION,
        "cash_rate": cash_rate,
    }
    _write_cache_envelope(cache_path, cache_payload)

    return hybrid_df[BENCHMARK_SCHEMA_COLUMNS]


def build_smallcap250_proxy_from_nifty500(nifty500_tri: pd.DataFrame) -> pd.DataFrame:
    """
    Build a disclosed fallback approximation for NIFTYSMALLCAP250_TRI from
    NIFTY500_TRI returns when live/cached smallcap data is unavailable.

    Construction:
      proxy_return_t = NIFTY500_TRI_Return_t
      proxy_value_0 = 100
      proxy_value_t = proxy_value_(t-1) * (1 + proxy_return_t)

    This is intentionally labelled as a disclosed approximation, never as an
    official TRI series.
    """
    validate_schema(nifty500_tri, ["date", "tri_value"])

    base = (
        nifty500_tri[["date", "tri_value"]]
        .assign(date=lambda d: pd.to_datetime(d["date"]))
        .drop_duplicates(subset="date")
        .sort_values("date")
        .reset_index(drop=True)
    )

    base_return = base["tri_value"] / base["tri_value"].shift(1) - 1
    base_return.iloc[0] = 0.0
    proxy_value = 100.0 * (1 + base_return.fillna(0.0)).cumprod()

    proxy_df = pd.DataFrame(
        {
            "date": base["date"],
            "benchmark_label": "NIFTYSMALLCAP250_TRI",
            "tri_value": proxy_value,
            "source": BENCHMARK_SOURCE_INTERNAL,
            "source_quality": SOURCE_QUALITY_DISCLOSED_APPROXIMATION,
        }
    )

    cache_path = _cache_file_path(BENCHMARK_CACHE_DIR, "NIFTYSMALLCAP250_TRI")
    cache_payload = {
        "records": proxy_df.assign(date=proxy_df["date"].dt.strftime("%Y-%m-%d")).to_dict(orient="records"),
        "source": BENCHMARK_SOURCE_INTERNAL,
        "source_quality": SOURCE_QUALITY_DISCLOSED_APPROXIMATION,
        "method": "NIFTY500_TRI_return_proxy_anchor_100",
    }
    _write_cache_envelope(cache_path, cache_payload)

    return proxy_df[BENCHMARK_SCHEMA_COLUMNS]
