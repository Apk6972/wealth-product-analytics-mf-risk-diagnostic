"""
Page: Methodology — Model Governance & Audit Note.

Documents the project's objective, fund universe, data sources, API/cache
design, processed data files, benchmark construction, formula definitions,
stress assumptions, suitability logic, known limitations, and production
upgrade path. Reads from:
  - 02_processed_data/ (via data_loader.py) for live data-quality figures
  - 01_raw_data/scheme_master/ for fund universe and benchmark configuration
  - 00_project_control/assumptions_log.csv for formal assumption records

This is the one page whose purpose is to document the configuration itself,
so reading static config files directly (never a live network fetch) is the
correct exception to the "processed CSVs only" rule applied to every other page.

Reference: 00_project_control/formula_audit.md, limitations.md, data_dictionary.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import data_loader as dl  # noqa: E402
import disclosures  # noqa: E402
import formatting  # noqa: E402
from returns import PROJECT_ROOT  # noqa: E402
from utils import (  # noqa: E402
    BENCHMARK_PROXY_DISCLAIMER,
    CACHE_MAX_AGE_HOURS,
    DATA_START_DATE,
    DEFAULT_RISK_FREE_RATE,
    EDUCATIONAL_DISCLAIMER,
    REQUIRED_BENCHMARKS,
    STRESS_TEST_DISCLAIMER,
    SUITABILITY_DISCLAIMER,
    is_dataframe_usable,
)

# ---------------------------------------------------------------------------
# Config file paths (static, checked-in — never live fetches)
# ---------------------------------------------------------------------------

SCHEME_MASTER_DIR = PROJECT_ROOT / "01_raw_data" / "scheme_master"
FUND_MASTER_PATH = SCHEME_MASTER_DIR / "fund_master.csv"
BENCHMARK_MAP_PATH = SCHEME_MASTER_DIR / "benchmark_map.csv"
STRESS_SCENARIOS_PATH = SCHEME_MASTER_DIR / "stress_scenarios.csv"
PORTFOLIO_WEIGHTS_PATH = SCHEME_MASTER_DIR / "portfolio_weights.csv"
ASSUMPTIONS_LOG_PATH = PROJECT_ROOT / "00_project_control" / "assumptions_log.csv"

# ---------------------------------------------------------------------------
# Source-quality legend (used in Data Sources tab)
# ---------------------------------------------------------------------------

NAV_SOURCE_QUALITY_LEGEND = {
    "API_FETCHED_VERIFIED": (
        "Live MFAPI fetch; returned scheme name matched expected_scheme_name. "
        "Scheme code confirmed correct for this run."
    ),
    "API_FETCHED_METADATA_WARNING": (
        "Live MFAPI fetch; returned scheme name did not cleanly match expected_scheme_name. "
        "Treat as provisional pending manual review."
    ),
    "CACHE_FRESH": (
        f"Served from local cache (< {CACHE_MAX_AGE_HOURS}h old); no live fetch was required."
    ),
    "CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE": (
        f"Live fetch failed; an expired (> {CACHE_MAX_AGE_HOURS}h old) cache copy was used "
        "so the app retains data, but is explicitly flagged as stale."
    ),
}

BENCHMARK_SOURCE_QUALITY_LEGEND = {
    "API_FETCHED_VERIFIED": "Live fetch from an official/direct TRI source (NSE / Nifty Indices).",
    "PRICE_INDEX_PROXY_NOT_TRI": (
        "TRI source unavailable; fell back to a yfinance price index (dividends excluded). "
        "Understates true TRI returns — never equivalent to an official TRI series."
    ),
    "DISCLOSED_APPROXIMATION": (
        "Internally synthesized/approximated series (e.g. HYBRID_65_35 or NIFTYSMALLCAP250_TRI synthetic proxy) — "
        "not a directly observed market series."
    ),
    "CACHE_FRESH": f"Served from local cache (< {CACHE_MAX_AGE_HOURS}h old); no live fetch was required.",
    "CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE": (
        f"Live fetch failed; an expired (> {CACHE_MAX_AGE_HOURS}h old) cache copy was used, "
        "explicitly flagged as stale."
    ),
}

# ---------------------------------------------------------------------------
# Processed data file catalogue
# ---------------------------------------------------------------------------

PROCESSED_FILES_CATALOGUE = [
    ("nav_daily_clean.csv", "Mutual fund NAV", "All funds", "Validated daily NAV after schema checks and gap-detection; primary input for the returns engine."),
    ("returns_daily.csv", "Returns", "All funds", "Daily NAV-to-NAV returns per fund. Benchmarks computed on same date grid."),
    ("returns_monthly.csv", "Returns", "All funds", "Month-end NAV-to-NAV returns per fund. Used for rolling, VaR/CVaR, and suitability calendar analytics."),
    ("metrics_summary.csv", "Risk/return metrics", "All funds", "Full-history CAGR, volatility, downside deviation, Sharpe, Sortino, max drawdown, recovery period, VaR 95, CVaR 95, best/worst month, positive month ratio — one row per fund."),
    ("rolling_metrics.csv", "Rolling analytics", "All funds", "Rolling 3M/6M/12M/24M/36M returns and rolling 63D/126D/252D volatility and Sharpe (long-format, one row per fund × date × window)."),
    ("benchmark_metrics.csv", "Benchmark-relative", "Fund × primary benchmark", "Static excess return, beta, tracking error, information ratio, upside capture, downside capture — each fund against its own primary benchmark only."),
    ("rolling_benchmark_metrics.csv", "Rolling benchmark-relative", "Fund × primary benchmark", "Rolling 252-trading-day beta, tracking error, and information ratio — same fund-to-own-benchmark pairing rule."),
    ("stress_results.csv", "Stress testing", "All funds + portfolio", "Historical replay and deterministic scenario fund returns, fund loss contributions, and portfolio-level total stress return."),
    ("attribution_results.csv", "Stress attribution", "All funds + portfolio", "Fund loss contribution, stress loss share, loss amount (INR), and post-stress portfolio value per scenario. Illustrates that allocation weight ≠ stress loss share."),
    ("suitability_results.csv", "Suitability diagnostics", "All funds × 4 profiles", "Educational suitability role, action, risk warning, and rationale for each (fund, client profile) pair. Not investment advice."),
    ("data_quality_report.csv", "Data quality audit", "All funds + benchmarks", "Source, source_quality, date range, status (PASS/WARNING/FAIL), and completeness flags for every series used by the app."),
]


def _read_config_csv(path: Path) -> pd.DataFrame:
    """Read a static, checked-in config file — never a live fetch."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("Methodology")
st.caption(
    "Model governance and audit note — how every number on every other page "
    "was sourced, constructed, calculated, and scored."
)

disclosures.render_data_quality_banner(stop_on_fail=False)

with st.expander("How to read this page", expanded=False):
    st.markdown(
        "- This page is the project's primary **audit and governance document**. "
        "It does not show fund-level results; those are on the other pages.\n"
        "- Five tabs cover: **Overview**, **Data & Coverage**, "
        "**Formula Definitions**, **Scenarios & Suitability**, and **Governance**.\n"
        "- If a metric elsewhere in the app is unclear, its exact formula and "
        "frequency are in the **Formula Definitions** tab.\n"
        "- All investment language describes trailing historical data and is "
        "framed as an educational diagnostic, not a forecast or recommendation."
    )

st.error(EDUCATIONAL_DISCLAIMER)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

data_quality_report = dl.load_data_quality_report()
metrics_summary = dl.load_metrics_summary()
fund_master = _read_config_csv(FUND_MASTER_PATH)
benchmark_map = _read_config_csv(BENCHMARK_MAP_PATH)
stress_scenarios = _read_config_csv(STRESS_SCENARIOS_PATH)
portfolio_weights = _read_config_csv(PORTFOLIO_WEIGHTS_PATH)
assumptions_log = _read_config_csv(ASSUMPTIONS_LOG_PATH)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_overview, tab_data, tab_formulas, tab_scenarios, tab_governance = st.tabs(
    [
        "Overview",
        "Data & Coverage",
        "Formula Definitions",
        "Scenarios & Suitability",
        "Governance",
    ]
)

# ===========================================================================
# TAB 1 — Overview
# Sections: 1 (project objective), 13 (educational-use disclaimer)
# ===========================================================================

with tab_overview:

    st.markdown("### 1. Project Objective")
    st.markdown(
        """
The **MF Risk Diagnostic Module** is an educational analytics proof-of-work project.
It converts five selected Indian mutual fund schemes into a full quantitative risk
and suitability diagnostic covering:

- Daily and monthly return analytics, CAGR, and growth-of-₹1 crore visualisation
- Annualised volatility, downside deviation, Sharpe ratio, Sortino ratio
- Maximum drawdown, drawdown recovery period, best/worst months
- Historical Value-at-Risk (VaR 95%) and Conditional VaR (CVaR 95%) — daily and monthly
- Rolling returns, rolling volatility, rolling Sharpe (trailing 3M–36M / 63D–252D windows)
- Benchmark-relative analytics: beta, tracking error, information ratio, upside/downside
  capture — each fund benchmarked against its own primary benchmark only
- Historical replay and deterministic scenario stress testing with portfolio-level attribution
- Rules-based educational suitability diagnostics across four client risk profiles

The analytical question driving every page: **"What risk created the return,
how painful was the return path, and which client profile can actually sit through it?"**

This project is **not** a fund-screening tool, not investment advice, and not a
fund-recommendation engine.
"""
    )

    st.markdown("### 2. Fund Universe and Sleeve Rationale")
    if fund_master.empty:
        st.info(f"`{FUND_MASTER_PATH}` not found — run `python 04_streamlit_app/refresh_data.py`.")
    else:
        st.dataframe(fund_master, use_container_width=True, hide_index=True)
    st.markdown(
        """
**Sleeve rationale:**

| Fund | Category | Sleeve | Rationale |
|---|---|---|---|
| UTI Nifty 50 Index | Passive large cap | Core Equity | Establishes the efficient-market baseline; lowest cost, lowest active risk |
| ICICI Prudential Bluechip | Active large cap | Core Equity | Same risk tier as passive; tests whether active management adds excess return over the same benchmark |
| Parag Parikh Flexi Cap | Flexi cap | Diversified Equity | Broad mandate, including overseas equity; tests diversification benefit and correlation break |
| HDFC Balanced Advantage | Hybrid / BAF | Hybrid Allocation | Dynamic equity-debt allocation; tests whether tactical risk management reduces drawdown and tail loss |
| Nippon India Small Cap | Small cap | Satellite Equity | Highest historical volatility sleeve; anchors the high-risk end of the universe for suitability contrast |

All five are **Direct Growth plans** only. This is a fixed demonstration corpus — not a
representative sample of the broader Indian mutual fund universe, and not a recommendation.
"""
    )

    st.markdown("### Data Horizon")
    if is_dataframe_usable(metrics_summary):
        analysis_start = formatting.format_date(pd.to_datetime(metrics_summary["data_start_date"]).min())
        analysis_end = formatting.format_date(pd.to_datetime(metrics_summary["data_end_date"]).max())
        st.markdown(
            f"- **Analysis horizon (all calculations in this app): {analysis_start} to {analysis_end}**  \n"
            f"  Enforced floor: `DATA_START_DATE = {DATA_START_DATE}`."
        )
    else:
        st.markdown(f"- **Enforced analysis horizon floor: `DATA_START_DATE = {DATA_START_DATE}`.**")
    st.markdown(
        "- Pre-2021 market stress events (2020 COVID crash, 2018 IL&FS) are **not** captured in historical "
        "replay stress tests unless a comparably severe window exists after 2021-01-01.\n"
        "- `data_quality_report.csv` can show earlier raw fetched dates for audit purposes; "
        "everything before the floor date is excluded before any return or metric calculation."
    )

    st.markdown("### 13. Educational-Use Disclaimer")
    st.error(EDUCATIONAL_DISCLAIMER)
    st.warning(STRESS_TEST_DISCLAIMER)
    st.warning(SUITABILITY_DISCLAIMER)
    st.warning(BENCHMARK_PROXY_DISCLAIMER)

# ===========================================================================
# TAB 2 — Data & Coverage
# Sections: 3 (data source hierarchy), 4 (API/cache), 5 (processed files),
#           6 (benchmark map), 7 (source-quality caveats)
# ===========================================================================

with tab_data:

    st.markdown("### 3. Data Source Hierarchy")
    st.markdown(
        """
**Mutual fund NAV:** [MFAPI](https://api.mfapi.in/mf/{scheme_code}) — a free,
community-run API that mirrors AMFI's official daily NAV disclosures for Indian
mutual fund schemes. AMFI remains the official source-of-record.

**Benchmark / index Total Returns Index (TRI) levels**, in strict priority order:

| Priority | Source | Label |
|:---:|---|---|
| 1 | NSE / Nifty Indices direct TRI endpoint | `API_FETCHED_VERIFIED` |
| 2 | Custom NSE India scraper (if priority-1 unavailable) | `API_FETCHED_VERIFIED` |
| 3 | yfinance **price index** (last resort) | `PRICE_INDEX_PROXY_NOT_TRI` |
| 4 | Disclosed synthetic approximation (no live TRI source at all) | `DISCLOSED_APPROXIMATION` |

**HYBRID_65_35:** Not fetched from any external source — internally constructed
as 65% NIFTY50_TRI daily return + 35% flat 6% annualised daily cash accrual.
See Formula Definitions tab for the exact construction.
"""
    )

    st.markdown("### 4. API / Cache Methodology")
    st.markdown(
        f"""
All network fetching happens **only** inside `04_streamlit_app/refresh_data.py`,
run manually or on a schedule. The Streamlit app itself **never** triggers a live
network call on page load; every page reads exclusively from `02_processed_data/*.csv`.

**Cache TTL logic (`{CACHE_MAX_AGE_HOURS}`-hour freshness window):**

| Condition | Behaviour | `source_quality` label |
|---|---|---|
| Cache exists and is < {CACHE_MAX_AGE_HOURS}h old | Reused as-is; no network call | `CACHE_FRESH` |
| Live fetch succeeds | Result written to cache and used | `API_FETCHED_VERIFIED` or `API_FETCHED_METADATA_WARNING` |
| Live fetch fails; expired cache exists | Expired cache used; clearly flagged | `CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE` |
| Live fetch fails; no cache at all | Pipeline fails fast with a clear error — no substitution | *(pipeline error, not a label)* |

**Scheme-code metadata verification:** After every live MFAPI fetch, the returned
scheme name is compared against each fund's `expected_scheme_name` in `fund_master.csv`
using a token-set match (case/word-order/filler-word insensitive). A mismatch flags the
fund as `API_FETCHED_METADATA_WARNING` rather than silently accepting a wrong scheme code.
"""
    )

    st.info(
        "**MFAPI caveat:** MFAPI is a free public convenience API, not an official source-of-record. "
        "AMFI remains the official source for Indian mutual fund NAV disclosures. "
        "MFAPI uptime, availability, and historical completeness are outside this project's control; "
        "a stale/expired cache may be substituted (with an explicit label) if a live fetch fails."
    )

    st.markdown("### 5. Processed Data Files")
    processed_files_df = pd.DataFrame(
        PROCESSED_FILES_CATALOGUE,
        columns=["File", "Content type", "Scope", "Description"],
    )
    st.dataframe(processed_files_df, use_container_width=True, hide_index=True)
    st.caption(
        "All files live in `02_processed_data/`. They are produced by "
        "`04_streamlit_app/refresh_data.py` and read by the Streamlit app. "
        "The app never writes to these files."
    )

    st.markdown("### 6. Benchmark Map")
    if benchmark_map.empty:
        st.info(f"`{BENCHMARK_MAP_PATH}` not found.")
    else:
        st.dataframe(benchmark_map, use_container_width=True, hide_index=True)
    st.markdown(
        f"Required benchmark series: `{'`, `'.join(REQUIRED_BENCHMARKS)}`.\n\n"
        "Each fund is compared **only against its own primary benchmark** for beta, "
        "tracking error, information ratio, and capture ratios — a single shared "
        "benchmark across all funds is never used."
    )

    st.markdown("### 7. Source-Quality Caveats")
    st.markdown("Every NAV and benchmark observation carries an explicit `source_quality` label:")
    st.markdown("**Mutual fund NAV labels:**")
    nav_legend_df = pd.DataFrame(
        {"source_quality": list(NAV_SOURCE_QUALITY_LEGEND.keys()), "Meaning": list(NAV_SOURCE_QUALITY_LEGEND.values())}
    )
    st.dataframe(nav_legend_df, use_container_width=True, hide_index=True)
    st.markdown("**Benchmark / index labels:**")
    benchmark_legend_df = pd.DataFrame(
        {"source_quality": list(BENCHMARK_SOURCE_QUALITY_LEGEND.keys()), "Meaning": list(BENCHMARK_SOURCE_QUALITY_LEGEND.values())}
    )
    st.dataframe(benchmark_legend_df, use_container_width=True, hide_index=True)

    st.warning(BENCHMARK_PROXY_DISCLAIMER)
    st.markdown(
        "A price index excludes reinvested dividends, causing it to systematically **understate** "
        "the return of the equivalent Total Returns Index. Any beta, tracking error, information ratio, "
        "or capture ratio computed against a `PRICE_INDEX_PROXY_NOT_TRI` benchmark inherits this "
        "understatement — the Benchmark Behaviour page surfaces this warning per-fund based on live "
        "`source_quality`."
    )

    if is_dataframe_usable(data_quality_report):
        st.markdown("### Current Source-Quality Breakdown")
        st.caption("From the last `refresh_data.py` run — reflects the state of the cache at that time.")
        quality_view = data_quality_report[
            ["fund_label_or_benchmark_label", "asset_type", "source", "source_quality", "status"]
        ].rename(columns={"fund_label_or_benchmark_label": "Fund / Benchmark", "asset_type": "Type"})
        st.dataframe(quality_view, use_container_width=True, hide_index=True)

# ===========================================================================
# TAB 3 — Formula Definitions
# Section 8: all 20 required formulas + attribution
# ===========================================================================

with tab_formulas:

    st.markdown("### 8. Formula Definitions")
    st.caption(
        f"Risk-free rate default = {formatting.format_percent(DEFAULT_RISK_FREE_RATE, decimals=0)} per annum, "
        "overridable on relevant pages. "
        "VaR and CVaR are always labelled daily or monthly — never shown without stating frequency. "
        "Daily and monthly annualisation are never mixed within the same ratio."
    )

    # -----------------------------------------------------------------------
    # 8.1 Returns
    # -----------------------------------------------------------------------

    st.markdown("#### 8.1 Returns")
    returns_df = pd.DataFrame(
        [
            (
                "Daily fund return",
                "NAV_t / NAV_(previous observation) − 1",
                "Daily",
                "Computed within each fund only; NAVs are never forward-filled before computing returns.",
            ),
            (
                "Month-end NAV",
                "Latest available NAV in that calendar month",
                "Monthly",
                "Used as the basis for all monthly return calculations.",
            ),
            (
                "Monthly fund return",
                "Month-end NAV_t / Month-end NAV_(t−1) − 1",
                "Monthly",
                "Same month-end definition applied consistently to fund and benchmark series.",
            ),
            (
                "Benchmark daily return",
                "TRI_value_t / TRI_value_(t−1) − 1",
                "Daily",
                "Same month-end / monthly-return logic applies to benchmark series.",
            ),
        ],
        columns=["Metric", "Formula", "Frequency", "Notes"],
    )
    st.dataframe(returns_df, use_container_width=True, hide_index=True)

    # -----------------------------------------------------------------------
    # 8.2 HYBRID_65_35 construction
    # -----------------------------------------------------------------------

    st.markdown("#### 8.2 HYBRID_65_35 Benchmark Construction")
    st.markdown(
        """
Used exclusively as the primary benchmark for HDFC Balanced Advantage Fund.

```
Hybrid Return_t  = 0.65 × NIFTY50_TRI Return_t + 0.35 × (0.06 / 252)

HYBRID_65_35 Value₀ = 100
HYBRID_65_35 Value_t = HYBRID_65_35 Value_(t−1) × (1 + Hybrid Return_t)
```

- `cash_rate` = 0.06 per annum (default), applied as a straight daily accrual (÷ 252 trading days).
- Label: `source = INTERNAL_SYNTHETIC_BENCHMARK`, `source_quality = DISCLOSED_APPROXIMATION`.
- The 35% sleeve uses a **static flat rate**, not actual debt index or arbitrage returns.
  Real balanced-advantage funds use dynamic tactical allocation that this static blend does not capture.
"""
    )

    # -----------------------------------------------------------------------
    # 8.3 Core risk/return metrics
    # -----------------------------------------------------------------------

    st.markdown("#### 8.3 Core Risk / Return Metrics (`metrics_summary.csv`)")
    core_metrics_df = pd.DataFrame(
        [
            ("CAGR", "(ending_nav / beginning_nav) ^ (365 / calendar_days) − 1", "Daily NAV"),
            ("Annualised volatility", "STDEV(daily_return) × √252", "Daily"),
            ("Downside deviation", "STDEV(daily_returns where daily_return < 0) × √252", "Daily"),
            ("Sharpe ratio", "(CAGR − risk_free_rate) / annualised_volatility", "Annual inputs"),
            ("Sortino ratio", "(CAGR − risk_free_rate) / downside_deviation", "Annual inputs"),
            ("Max drawdown", "min(wealth_index / running_peak(wealth_index) − 1)", "Daily"),
            ("Recovery period", "Longest calendar duration (days) from drawdown trough back to the prior peak NAV level", "Daily"),
            ("Best month / Worst month", "max(monthly_return) / min(monthly_return)", "Monthly"),
            ("Positive month ratio", "count(monthly_return > 0) / total_months", "Monthly"),
            ("Daily VaR 95", "5th percentile of the daily return distribution", "Daily"),
            ("Daily CVaR 95", "Mean of all daily returns ≤ Daily VaR 95 (expected shortfall)", "Daily"),
            ("Monthly VaR 95", "5th percentile of the monthly return distribution", "Monthly"),
            ("Monthly CVaR 95", "Mean of all monthly returns ≤ Monthly VaR 95 (expected shortfall)", "Monthly"),
        ],
        columns=["Metric", "Formula", "Frequency"],
    )
    st.dataframe(core_metrics_df, use_container_width=True, hide_index=True)

    # -----------------------------------------------------------------------
    # 8.4 Rolling metrics
    # -----------------------------------------------------------------------

    st.markdown("#### 8.4 Rolling Metrics (`rolling_metrics.csv`)")
    rolling_df = pd.DataFrame(
        [
            ("Rolling returns", "PRODUCT(1 + monthly_return over trailing N months) − 1", "Monthly", "N ∈ {3, 6, 12, 24, 36}"),
            ("Rolling annualised returns", "PRODUCT(1 + monthly_return over trailing N months) ^ (12/N) − 1", "Monthly", "N ∈ {12, 24, 36}"),
            ("Rolling volatility", "STDEV(daily_return over trailing W days) × √252", "Daily", "W ∈ {63, 126, 252}"),
            ("Rolling Sharpe", "(rolling_252d_return_ann − risk_free_rate) / rolling_252d_vol", "Daily", "252-day trailing window only"),
        ],
        columns=["Metric", "Formula", "Input frequency", "Windows"],
    )
    st.dataframe(rolling_df, use_container_width=True, hide_index=True)
    st.caption(
        "Early-window values (insufficient trailing history) are `NaN` — never forward-filled. "
        "A rolling value is only computed once the full trailing window is available."
    )

    # -----------------------------------------------------------------------
    # 8.5 Benchmark-relative analytics
    # -----------------------------------------------------------------------

    st.markdown(
        "#### 8.5 Benchmark-Relative Analytics (`benchmark_metrics.csv`, `rolling_benchmark_metrics.csv`)"
    )
    benchmark_formula_df = pd.DataFrame(
        [
            ("Excess return", "fund_return − benchmark_return", "Daily (same-date pairing, inner join)"),
            ("Beta", "Cov(fund_return, benchmark_return) / Var(benchmark_return)", "Daily"),
            ("Tracking error", "STDEV(excess_return) × √252", "Daily → annualised"),
            ("Information ratio", "annualised_excess_return / tracking_error", "Annual"),
            ("Upside capture", "Compounded cumulative fund return / benchmark return on days when benchmark_return > 0", "Daily"),
            ("Downside capture", "Compounded cumulative fund return / benchmark return on days when benchmark_return < 0", "Daily"),
            ("Rolling 252D beta", "Rolling Cov(fund, benchmark) / Rolling Var(benchmark) over trailing 252 trading days", "252D window"),
            ("Rolling 252D tracking error", "Rolling STDEV(daily excess_return) × √252 over trailing 252 trading days", "252D window"),
            ("Rolling 252D information ratio", "Rolling annualised excess return / rolling tracking error", "252D window"),
        ],
        columns=["Metric", "Formula", "Frequency / Notes"],
    )
    st.dataframe(benchmark_formula_df, use_container_width=True, hide_index=True)
    st.caption(
        "**annualised_excess_return** (IR numerator) = mean(daily excess_return) × 252 — "
        "a simple arithmetic annualisation of the mean, deliberately distinct from tracking error's "
        "STDEV × √252 volatility-style annualisation. This is the standard convention for excess-return-based ratios. "
        "Fund-benchmark pairs with fewer than 20 aligned trading days are excluded (set to NaN) rather than "
        "computed from a near-empty sample."
    )

    # -----------------------------------------------------------------------
    # 8.6 Attribution formulas
    # -----------------------------------------------------------------------

    st.markdown("#### 8.6 Stress Attribution (`attribution_results.csv`)")
    st.markdown(
        """
```
Fund Loss Contribution        = Fund Weight × Fund Stress Return
Total Portfolio Stress Return = Σ(Fund Loss Contribution across all funds)
Stress Loss Share             = Fund Loss Contribution / Total Portfolio Stress Return
Loss Amount (INR)             = Base Portfolio Value × Fund Loss Contribution
Post-Stress Portfolio Value   = Base Portfolio Value × (1 + Total Portfolio Stress Return)
```

**Key insight preserved throughout the app:** allocation weight is not the same as stress loss
share — a fund with a small portfolio weight can contribute a disproportionate share of total
scenario loss.
"""
    )

    # -----------------------------------------------------------------------
    # Annualisation reference
    # -----------------------------------------------------------------------

    st.markdown("#### Annualisation Factor Reference")
    ann_df = pd.DataFrame(
        [
            ("Daily volatility → annual", "× √252"),
            ("Monthly volatility → annual", "× √12"),
            ("Monthly compounding → annual return", "^ (12/N) over N months"),
            ("Total NAV growth → CAGR", "^ (365 / calendar_days) − 1"),
        ],
        columns=["Context", "Factor"],
    )
    st.dataframe(ann_df, use_container_width=True, hide_index=True)

# ===========================================================================
# TAB 4 — Scenarios & Suitability
# Sections: 9 (stress testing), 10 (suitability logic)
# ===========================================================================

with tab_scenarios:

    # -----------------------------------------------------------------------
    # 9. Stress testing
    # -----------------------------------------------------------------------

    st.markdown("### 9. Stress Testing Assumptions")
    st.warning(STRESS_TEST_DISCLAIMER)

    st.markdown("#### 9A. Historical Replay")
    st.markdown(
        """
Uses **actual historical returns** — no hypothetical shocks, no transformation beyond
compounding over the identified worst-case window. Five anchor windows are identified:

| Window | Anchor criterion |
|---|---|
| Worst 1-month portfolio period | Minimum compounded 1-month portfolio return |
| Worst 3-month portfolio period | Minimum compounded 3-month portfolio return |
| Worst 20-trading-day portfolio period | Minimum compounded 20-day portfolio return |
| Worst small-cap fund period | Worst 1-month return for Nippon India Small Cap |
| Worst benchmark drawdown period | Deepest NIFTY50_TRI drawdown trough-to-recovery window |

Once a window is identified, **every fund's own actual compounded return over that exact
window** is reported — not just the fund that anchored the window's discovery.
"""
    )

    st.markdown("#### 9B. Deterministic Stress Scenarios")
    if stress_scenarios.empty:
        st.info(f"`{STRESS_SCENARIOS_PATH}` not found — run `python 04_streamlit_app/refresh_data.py`.")
    else:
        st.dataframe(stress_scenarios, use_container_width=True, hide_index=True)
    st.caption(
        'Each deterministic row carries the embedded disclosure: '
        '"Deterministic stress scenarios are illustrative assumptions, not forecasts."'
    )

    st.markdown("#### 9C. Interactive Custom Shocks")
    st.markdown(
        "The Scenario Stress Testing page accepts user-defined fund-level shocks and portfolio "
        "allocation sliders, and recomputes the same attribution math in-memory. "
        "This is **never persisted** to `stress_results.csv`; it exists only for interactive "
        "what-if exploration. The same attribution formulas from §8.6 apply."
    )

    st.markdown("#### Default Portfolio Weights")
    if portfolio_weights.empty:
        st.info(f"`{PORTFOLIO_WEIGHTS_PATH}` not found.")
    else:
        st.dataframe(portfolio_weights, use_container_width=True, hide_index=True)
    st.caption(
        "Weights are the default starting point for attribution; the Scenario Stress Testing page "
        "allows interactive overrides that are not persisted."
    )

    # -----------------------------------------------------------------------
    # 10. Suitability logic
    # -----------------------------------------------------------------------

    st.markdown("### 10. Suitability Logic")
    st.warning(SUITABILITY_DISCLAIMER)
    st.markdown(
        """
Suitability scoring is a **documented, rules-based layer** over already-computed trailing
metrics — not a single formula, not a proprietary model, and not a regulatory suitability
assessment. It is implemented in `04_streamlit_app/src/suitability.py`; the full factor
table is in `00_project_control/formula_audit.md` §8.

**Inputs (factors):** max drawdown, annualised volatility, Daily CVaR 95, small-cap exposure
(fund label), rolling beta, downside capture, stress loss share vs. allocation weight,
recovery period. A factor that cannot be computed is **excluded from scoring**, never
substituted with a guessed default.
"""
    )

    st.markdown("#### Step 1 — Per-Factor Risk Tiering (LOW / MEDIUM / HIGH)")
    factor_tiers_df = pd.DataFrame(
        [
            ("Annualised volatility", "< 10%", "10% – 18%", "> 18%"),
            ("Max drawdown (|value|)", "< 15%", "15% – 30%", "> 30%"),
            ("Daily CVaR 95 (|value|)", "< 2%", "2% – 4%", "> 4%"),
            ("Recovery period", "< 180 days", "180 – 450 days", "> 450 days or never recovered (unless |max drawdown| < 1%)"),
            ("Small-cap exposure", "Not small cap", "—", "Fund label contains 'small cap'"),
            ("Rolling beta", "< 0.85", "0.85 – 1.15", "> 1.15"),
            ("Downside capture", "< 90%", "90% – 110%", "> 110%"),
            ("Stress loss share vs. weight (avg. excess pp)", "≤ +2 pp", "+2 pp to +8 pp", "> +8 pp"),
        ],
        columns=["Factor", "LOW", "MEDIUM", "HIGH"],
    )
    st.dataframe(factor_tiers_df, use_container_width=True, hide_index=True)

    st.markdown("#### Step 2 — Overall Risk Tier")
    st.markdown(
        """
Each available factor tier is mapped to a point value (LOW = 1.0, MEDIUM = 2.5, HIGH = 4.0)
and averaged across only the **available** factors.

```
overall_risk_tier = LOW     if average_points < 1.75
                 = MEDIUM   if 1.75 ≤ average_points < 3.25
                 = HIGH     if average_points ≥ 3.25
```
"""
    )

    st.markdown("#### Step 3 — Profile Fit via Risk-Appetite Gap")
    st.markdown(
        "Each client profile has a risk-appetite point value on the same 1.0–4.0 scale: "
        "Conservative = 1.0, Balanced = 2.0, Growth = 3.0, Aggressive = 4.0."
    )
    gap_df = pd.DataFrame(
        [
            ("gap ≥ +1.5", "Defensive sleeve", "Retain"),
            ("−0.5 ≤ gap < +1.5", "Core", "Retain"),
            ("−1.5 ≤ gap < −0.5, profile ∈ {Growth, Aggressive}", "Aggressive satellite (HIGH) / Satellite", "Stagger allocation"),
            ("−1.5 ≤ gap < −0.5, profile = Balanced", "Satellite", "Cap exposure"),
            ("−1.5 ≤ gap < −0.5, profile = Conservative", "Watchlist", "Cap exposure"),
            ("−2.5 ≤ gap < −1.5, profile ∈ {Growth, Aggressive}", "Watchlist", "Pair with defensive sleeve"),
            ("−2.5 ≤ gap < −1.5, profile ∈ {Conservative, Balanced}", "Watchlist", "Cap exposure"),
            ("gap < −2.5", "Unsuitable for profile", "Avoid for low drawdown tolerance"),
        ],
        columns=["Gap (profile points − fund points)", "Role", "Action"],
    )
    st.dataframe(gap_df, use_container_width=True, hide_index=True)
    st.caption(
        "Override: if the resulting role is Watchlist and benchmark-relative data (beta, downside capture) "
        "was unavailable for the fund, the action becomes 'Review benchmark-relative behaviour'. "
        "Every generated rationale sentence describes trailing historical data only and closes with an "
        "explicit 'not a forecast or an investment recommendation' disclaimer."
    )

# ===========================================================================
# TAB 5 — Governance
# Sections: 11 (limitations), 12 (production upgrade), assumptions log
# ===========================================================================

with tab_governance:

    # -----------------------------------------------------------------------
    # 11. Known limitations
    # -----------------------------------------------------------------------

    st.markdown("### 11. Known Limitations")
    st.markdown(
        """
**Data sourcing:**
- MFAPI is a free public convenience API, not the official source-of-record; AMFI remains the
  official source for Indian mutual fund NAV disclosures. MFAPI uptime and historical completeness
  are outside project control.
- Priority-1 NSE/Nifty Indices TRI programmatic fetching is inherently more fragile than a paid
  data vendor (session handling, rate limiting, endpoint changes can break it without notice).
- Several benchmark series currently carry `PRICE_INDEX_PROXY_NOT_TRI` (dividends excluded), which
  systematically understates true TRI returns. Beta, tracking error, information ratio, and capture
  ratios for affected fund-benchmark pairs inherit this caveat.
- HYBRID_65_35 uses a static 65/35 blend with a flat 6% cash proxy for the 35% sleeve; real
  balanced-advantage funds use dynamic tactical allocation that this approximation cannot replicate.

**Coverage and scope:**
- **Fixed, small fund universe (5 sleeves)** — not a representative sample and not a recommendation set.
- Only **Direct Growth** plans are covered; Regular plans, IDCW options, and other share classes
  are out of scope.
- **Data horizon starts 2021-01-01** — the 2020 COVID crash and 2018 IL&FS stress are not captured
  in historical replay unless a comparably severe post-2021 window exists.
- No survivorship-bias correction — a discontinued or restructured fund would need manual review.

**Methodological simplifications:**
- Expense ratios are reflected in NAV-to-NAV returns, but exit loads and investor-level taxation
  (STCG/LTCG, indexation) are **not modeled**.
- All growth calculations assume a lump-sum entry; **no SIP cash-flow analytics** are provided.
- Risk-free rate is a single flat assumption (default 6% annual), not a term-structure or T-bill series.
- Fixed 252-trading-day annualisation convention — actual NSE trading calendars vary slightly by year.
- Recovery period is measured on the fund's NAV series only; it does not model an investor's actual
  entry or exit timing.
- Suitability thresholds are a transparent, documented rules-based approximation, not a regulatory
  or empirically back-tested suitability framework.

**Operational:**
- Dashboard figures are only as fresh as the last `refresh_data.py` run (nominal 24-hour cache TTL).
  The app never fetches live data on page load.
- No intraday data — all analytics are end-of-day.
"""
    )
    st.caption("Full detail: `00_project_control/limitations.md`.")

    # -----------------------------------------------------------------------
    # 12. Production upgrade path
    # -----------------------------------------------------------------------

    st.markdown("### 12. Production Upgrade Path")
    st.markdown(
        """
This project is designed as an educational proof-of-work demonstration. The following
upgrades would be required before any production or client-facing deployment:

**Data sourcing:**
- Replace MFAPI with a licensed, institutional-grade data vendor (e.g. CRISIL, Bloomberg,
  Refinitiv/LSEG, or a direct SEBI-registered data aggregator) for NAV data with SLA guarantees.
- Obtain direct NSE / Nifty Indices TRI data subscriptions to eliminate the
  `PRICE_INDEX_PROXY_NOT_TRI` fallback for all benchmarks.
- Replace the HYBRID_65_35 flat cash proxy with an official published AMFI or SEBI benchmark
  series if and when one becomes available for HDFC Balanced Advantage-style funds.

**Infrastructure:**
- Containerise the pipeline with Docker; deploy on a cloud provider (AWS, GCP, or Azure)
  with managed scheduling (Airflow, Cloud Scheduler, or GitHub Actions cron) to replace
  the manual `refresh_data.py` step.
- Add end-to-end data reconciliation that compares fetched NAVs against official AMFI
  daily disclosures and alerts on mismatches.
- Implement a proper secrets management solution (not plain environment variables) for
  any API keys or data vendor credentials.

**Analytics:**
- Expand the fund universe systematically via a screener-based approach rather than a
  fixed list; add survivorship-bias controls.
- Add SIP cash-flow analytics and investor-specific entry/exit date simulation.
- Add factor-model attribution (size, value, momentum, quality factors for Indian equities).
- Add regime-aware stress testing (VIX-conditional, macro scenario calibration).
- Add peer-group comparison and percentile ranking within SEBI categories.
- Model investor-level tax drag (STCG/LTCG, indexation) for after-tax return analytics.

**Governance:**
- Implement formal model validation and annual review cycles for suitability thresholds.
- Add a versioned change log in `data_quality_report.csv` to track parameter updates.
- Add automated data quality alerts (e.g. if any series carries `FAIL` status for > N days).
- Formal regulatory review before any use for actual investment recommendations or
  compliance purposes.
"""
    )

    # -----------------------------------------------------------------------
    # Assumptions log
    # -----------------------------------------------------------------------

    st.markdown("### Formal Assumptions Log")
    st.caption(
        "Sourced from `00_project_control/assumptions_log.csv`. "
        "Each assumption is recorded with its rationale, analytical impact, and last-reviewed date."
    )
    if assumptions_log.empty:
        st.warning(
            f"`{ASSUMPTIONS_LOG_PATH}` not found or empty. "
            "This file should be present in the repository."
        )
    else:
        st.dataframe(assumptions_log, use_container_width=True, hide_index=True)
