"""
Page: Methodology.

Reads from 02_processed_data/ (via data_loader.py) for the live data-quality
and date-range figures, and directly from the static, checked-in
01_raw_data/scheme_master/ config files (fund_master.csv, benchmark_map.csv)
to display the fund universe / benchmark map exactly as configured — this is
the one page whose purpose is to document that configuration itself, so
reading it directly (never a live network fetch) is the correct exception
to the "processed CSVs only" rule applied to every other page in this app.

Reference: 00_project_control/master_project_instructions.md.md §23.8,
00_project_control/formula_audit.md, 00_project_control/limitations.md,
00_project_control/data_dictionary.md.
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

SCHEME_MASTER_DIR = PROJECT_ROOT / "01_raw_data" / "scheme_master"
FUND_MASTER_PATH = SCHEME_MASTER_DIR / "fund_master.csv"
BENCHMARK_MAP_PATH = SCHEME_MASTER_DIR / "benchmark_map.csv"
STRESS_SCENARIOS_PATH = SCHEME_MASTER_DIR / "stress_scenarios.csv"
PORTFOLIO_WEIGHTS_PATH = SCHEME_MASTER_DIR / "portfolio_weights.csv"

NAV_SOURCE_QUALITY_LEGEND = {
    "API_FETCHED_VERIFIED": "Live MFAPI fetch, and the returned scheme name matched expected_scheme_name.",
    "API_FETCHED_METADATA_WARNING": "Live MFAPI fetch, but the returned scheme name did not cleanly match "
    "expected_scheme_name — treat as provisional pending manual review.",
    "CACHE_FRESH": "Served from local cache (< 24h old); no live fetch was needed for this run.",
    "CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE": "Live fetch failed; an expired (> 24h old) cache copy was used "
    "instead so the app still has data, clearly flagged as stale.",
}
BENCHMARK_SOURCE_QUALITY_LEGEND = {
    "API_FETCHED_VERIFIED": "Live fetch from an official/direct TRI source (NSE / Nifty Indices).",
    "PRICE_INDEX_PROXY_NOT_TRI": "TRI source unavailable; fell back to a yfinance PRICE index (dividends "
    "excluded). Understates true TRI returns — never treat as equivalent to an official TRI series.",
    "DISCLOSED_APPROXIMATION": "An internally synthesized/approximated series (e.g. HYBRID_65_35, or the "
    "NIFTYSMALLCAP250_TRI synthetic proxy) — not a directly observed market series.",
    "CACHE_FRESH": "Served from local cache (< 24h old); no live fetch was needed for this run.",
    "CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE": "Live fetch failed; an expired (> 24h old) cache copy was used "
    "instead, clearly flagged as stale.",
}


def _read_config_csv(path: Path) -> pd.DataFrame:
    """Read a static, checked-in 01_raw_data/scheme_master/ config file (never a live fetch)."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("Methodology")
st.caption("How the numbers on every other page were sourced, cleaned, calculated, and scored.")

disclosures.render_data_quality_banner(stop_on_fail=False)

with st.expander("How to read this page", expanded=False):
    st.markdown(
        "- This page documents **how** every other page's numbers were sourced, cleaned, calculated, and "
        "scored — it does not show fund-level results itself.\n"
        "- Use the tabs below: **Data Sources & Caveats**, **Fund Universe, Benchmark Map & Date Range**, "
        "**Formula Definitions**, **Stress Assumptions**, and **Limitations & Disclaimer**.\n"
        "- If a metric elsewhere in the app is unclear, its exact formula and frequency are in the "
        "**Formula Definitions** tab."
    )

st.warning(EDUCATIONAL_DISCLAIMER)

data_quality_report = dl.load_data_quality_report()
metrics_summary = dl.load_metrics_summary()
fund_master = _read_config_csv(FUND_MASTER_PATH)
benchmark_map = _read_config_csv(BENCHMARK_MAP_PATH)
stress_scenarios = _read_config_csv(STRESS_SCENARIOS_PATH)
portfolio_weights = _read_config_csv(PORTFOLIO_WEIGHTS_PATH)

tab_sources, tab_universe, tab_formulas, tab_stress, tab_limitations = st.tabs(
    [
        "Data Sources & Caveats",
        "Fund Universe, Benchmark Map & Date Range",
        "Formula Definitions",
        "Stress Assumptions",
        "Limitations & Disclaimer",
    ]
)

# ---------------------------------------------------------------------------
# Tab 1: Data sources, API/cache methodology, MFAPI caveat, benchmark
# source-quality logic, price-index fallback warning
# ---------------------------------------------------------------------------

with tab_sources:
    st.markdown("### Data Sources")
    st.markdown(
        """
- **Mutual fund NAV**: [MFAPI](https://api.mfapi.in/mf/{scheme_code}) — a free, community-run API that mirrors
  AMFI's official daily NAV disclosures for Indian mutual fund schemes.
- **Benchmark / index Total Returns Index (TRI) levels**, in priority order:
    1. **NSE / Nifty Indices** direct TRI endpoints (priority 1).
    2. A custom NSE India scraper (priority 2), used if the priority-1 endpoint is unavailable.
    3. **yfinance** price-index levels (priority 3, last resort) — labelled `PRICE_INDEX_PROXY_NOT_TRI`, never
       silently presented as TRI.
    4. A **disclosed synthetic approximation** (priority 4) for series with no reliable live TRI source at all
       (e.g. `NIFTYSMALLCAP250_TRI`), labelled `DISCLOSED_APPROXIMATION`.
- **HYBRID_65_35**: not fetched from anywhere — internally constructed as 65% `NIFTY50_TRI` + 35% a flat 6%
  annualized daily cash accrual (see Formula Definitions tab, §2).
"""
    )

    st.markdown("### API / Cache Methodology")
    st.markdown(
        f"""
- All fetching happens **only** inside `04_streamlit_app/refresh_data.py`, run manually/on a schedule — the
  Streamlit app itself **never** triggers a live fetch on page load; every page you've seen reads exclusively
  from `02_processed_data/*.csv`.
- Every fetch response is cached to `01_raw_data/api_cache/{{mutual_funds,benchmarks,metadata}}/` with a
  **{CACHE_MAX_AGE_HOURS}-hour freshness TTL**.
    - Fresh cache (< {CACHE_MAX_AGE_HOURS}h old) → reused as-is (`source_quality = CACHE_FRESH`), no network call.
    - Live fetch fails, but an expired cache copy exists → the expired cache is used anyway so the app keeps
      working, explicitly labelled `CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE` rather than presented as current.
    - Live fetch fails and no cache exists at all → the pipeline **fails fast** with a clear error rather than
      inventing or substituting a value.
- Mutual fund metadata is verified by a token-set comparison between the API's returned scheme name and each
  fund's `expected_scheme_name` in `fund_master.csv` (case/word-order/filler-word insensitive), to catch a
  wrong `scheme_code` before it silently pollutes downstream numbers.
"""
    )

    st.markdown("### MFAPI Caveat")
    st.info(
        "MFAPI is a **free public convenience API, not an official source-of-record** — AMFI remains the "
        "official source for Indian mutual fund NAV disclosures. Its uptime, availability, and historical "
        "completeness are outside this project's control; a stale/expired cache may be substituted (with an "
        "explicit `CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE` label) if a live fetch fails."
    )

    st.markdown("### Benchmark Source-Quality Logic")
    st.markdown("Every NAV and benchmark observation carries an explicit `source_quality` label:")
    nav_legend_df = pd.DataFrame(
        {"source_quality": list(NAV_SOURCE_QUALITY_LEGEND.keys()), "Meaning": list(NAV_SOURCE_QUALITY_LEGEND.values())}
    )
    st.markdown("**Mutual fund NAV:**")
    st.dataframe(nav_legend_df, width="stretch", hide_index=True)
    benchmark_legend_df = pd.DataFrame(
        {
            "source_quality": list(BENCHMARK_SOURCE_QUALITY_LEGEND.keys()),
            "Meaning": list(BENCHMARK_SOURCE_QUALITY_LEGEND.values()),
        }
    )
    st.markdown("**Benchmark / index:**")
    st.dataframe(benchmark_legend_df, width="stretch", hide_index=True)

    st.markdown("### Price-Index Fallback Warning")
    st.warning(BENCHMARK_PROXY_DISCLAIMER)
    st.markdown(
        "A price index excludes reinvested dividends, so it systematically **understates** the return of the "
        "equivalent Total Returns Index. Any beta / tracking error / information ratio / capture ratio computed "
        "against a `PRICE_INDEX_PROXY_NOT_TRI` benchmark inherits this understatement — see the Benchmark "
        "Behaviour page, which surfaces this warning per-fund based on its live `source_quality`."
    )

    if is_dataframe_usable(data_quality_report):
        st.markdown("### Current `source_quality` Breakdown (from the last `refresh_data.py` run)")
        quality_view = data_quality_report[
            ["fund_label_or_benchmark_label", "asset_type", "source", "source_quality", "status"]
        ].rename(columns={"fund_label_or_benchmark_label": "Fund / Benchmark", "asset_type": "Type"})
        st.dataframe(quality_view, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Tab 2: Date range, fund universe, benchmark map
# ---------------------------------------------------------------------------

with tab_universe:
    st.markdown("### Date Range")
    if is_dataframe_usable(metrics_summary):
        analysis_start = formatting.format_date(pd.to_datetime(metrics_summary["data_start_date"]).min())
        analysis_end = formatting.format_date(pd.to_datetime(metrics_summary["data_end_date"]).max())
        st.markdown(
            f"- **Analysis horizon used for every calculation in this app: {analysis_start} to {analysis_end}** "
            f"(enforced floor: `DATA_START_DATE = {DATA_START_DATE}`)."
        )
    else:
        st.markdown(f"- **Enforced analysis horizon floor: `DATA_START_DATE = {DATA_START_DATE}`.**")
    st.markdown(
        "- `data_quality_report.csv` (Data Sources tab, above) reflects the **raw, pre-filter** fetched range "
        "for data-quality auditing purposes — it can show earlier dates than the analysis horizon above, since "
        "everything before 2021-01-01 is intentionally excluded before any return/metric/stress calculation."
    )
    st.markdown(
        "- Consequence: pre-2021 market stress (e.g. the 2020 COVID crash, 2018 IL&FS stress) is **not** "
        "captured by this app's historical replay stress tests unless a comparably severe window exists after "
        "2021-01-01."
    )

    st.markdown("### Fund Universe")
    if fund_master.empty:
        st.info(f"`{FUND_MASTER_PATH}` not found.")
    else:
        st.dataframe(fund_master, width="stretch", hide_index=True)
        st.caption(
            "Only Direct Growth plans are covered. This is a fixed set of 5 category-proxy sleeves chosen for "
            "demonstration — not a representative sample of the broader mutual fund universe, and not a "
            "recommendation set."
        )

    st.markdown("### Benchmark Map")
    if benchmark_map.empty:
        st.info(f"`{BENCHMARK_MAP_PATH}` not found.")
    else:
        st.dataframe(benchmark_map, width="stretch", hide_index=True)
        st.caption(
            "Every fund is compared only against its own `primary_benchmark` for beta / tracking error / "
            "information ratio / capture ratios — never a single shared benchmark across all funds. Required "
            f"benchmark series: {', '.join(REQUIRED_BENCHMARKS)}."
        )

# ---------------------------------------------------------------------------
# Tab 3: Formula definitions
# ---------------------------------------------------------------------------

with tab_formulas:
    st.markdown("### Core Metrics (`metrics_summary.csv`)")
    core_metrics_df = pd.DataFrame(
        [
            ("CAGR", "(ending_nav / beginning_nav) ^ (365 / calendar_days) - 1", "Daily NAV"),
            ("Annualized Volatility", "STDEV(daily_return) × √252", "Daily"),
            ("Downside Deviation", "STDEV(negative daily returns) × √252", "Daily"),
            ("Sharpe Ratio", "(CAGR - risk_free_rate) / annualized_volatility", "Annual"),
            ("Sortino Ratio", "(CAGR - risk_free_rate) / downside_deviation", "Annual"),
            ("Max Drawdown", "min(wealth_index / running_peak(wealth_index) - 1)", "Daily"),
            ("Recovery Period", "Longest peak-to-recovery duration (days)", "Daily"),
            ("Best / Worst Month", "max / min(monthly_return)", "Monthly"),
            ("Positive Month Ratio", "count(monthly_return > 0) / total_months", "Monthly"),
            ("Daily VaR 95 / CVaR 95", "5th percentile of daily returns / mean of daily returns ≤ VaR", "Daily"),
            ("Monthly VaR 95 / CVaR 95", "5th percentile of monthly returns / mean of monthly returns ≤ VaR", "Monthly"),
        ],
        columns=["Metric", "Formula", "Frequency"],
    )
    st.dataframe(core_metrics_df, width="stretch", hide_index=True)
    st.caption(
        f"risk_free_rate default = {formatting.format_percent(DEFAULT_RISK_FREE_RATE, decimals=0)} (overridable, "
        "always disclosed). VaR/CVaR are never shown without stating daily vs. monthly. Daily and monthly "
        "annualization are never mixed within the same ratio."
    )

    st.markdown("### Rolling Metrics (`rolling_metrics.csv`)")
    st.markdown(
        """
- Rolling returns: `PRODUCT(1 + monthly_return over trailing N months) - 1`, N ∈ {3, 6, 12, 24, 36}.
- Rolling annualized returns: `PRODUCT(1 + monthly_return over trailing N months) ^ (12/N) - 1`, N ∈ {12, 24, 36}.
- Rolling volatility: `STDEV(daily_return over trailing W days) × √252`, W ∈ {63, 126, 252}.
- Rolling Sharpe: `(rolling_252d_return_ann - risk_free_rate) / rolling_252d_vol`.
- Early-window values are `NaN` (insufficient trailing history) — never forward-filled.
"""
    )

    st.markdown("### Benchmark-Relative Analytics (`benchmark_metrics.csv`, `rolling_benchmark_metrics.csv`)")
    benchmark_formula_df = pd.DataFrame(
        [
            ("Excess Return", "fund_return - benchmark_return (same-date pairing)"),
            ("Beta", "Cov(fund_return, benchmark_return) / Var(benchmark_return)"),
            ("Tracking Error", "STDEV(excess_return) × annualization factor (√252 daily)"),
            ("Information Ratio", "annualized_excess_return / tracking_error"),
            ("Upside / Downside Capture", "Compounded cumulative fund return / benchmark return, split by benchmark sign"),
            ("Rolling 252D Beta / TE / IR", "Same formulas, rolling over a trailing 252-trading-day window"),
        ],
        columns=["Metric", "Formula"],
    )
    st.dataframe(benchmark_formula_df, width="stretch", hide_index=True)
    st.caption(
        "annualized_excess_return = mean(daily excess_return) × 252 (linear annualization of the mean, "
        "deliberately distinct from tracking error's STDEV × √252 volatility-style annualization). Each fund is "
        "matched to its own primary benchmark only; dates are inner-joined before any calculation; pairs with "
        "fewer than 20 aligned trading days are excluded (set to NaN) rather than computed from a near-empty sample."
    )

    st.markdown("### Attribution (`attribution_results.csv`)")
    st.markdown(
        """
```text
Fund Loss Contribution        = Fund Weight × Fund Stress Return
Total Portfolio Stress Return = Σ Fund Loss Contribution
Stress Loss Share             = Fund Loss Contribution / Total Portfolio Stress Return
Loss Amount (INR)             = Base Portfolio Value × Fund Loss Contribution
Post-Stress Portfolio Value   = Base Portfolio Value × (1 + Total Portfolio Stress Return)
```
**Key insight preserved throughout the app: allocation weight is not the same as stress loss share** — a fund
can carry a small portfolio weight yet contribute a disproportionate share of a scenario's total loss.
"""
    )

    st.markdown("### Suitability Scoring (`suitability_results.csv`)")
    st.markdown(
        """
A documented rules/scoring layer (not a single formula) over already-computed metrics — see
`00_project_control/formula_audit.md` §8 for the full per-factor LOW/MEDIUM/HIGH tiering table and the
profile-vs-risk "gap" table that maps to a suitability role and recommended educational action. Factors used:
max drawdown, volatility, Daily CVaR 95, small-cap exposure, rolling beta, downside capture, stress loss share
(vs. weight), and recovery period — any factor that cannot be computed is excluded from scoring, never defaulted
to a guessed value.
"""
    )

# ---------------------------------------------------------------------------
# Tab 4: Stress assumptions
# ---------------------------------------------------------------------------

with tab_stress:
    st.warning(STRESS_TEST_DISCLAIMER)

    st.markdown("### A. Historical Replay")
    st.markdown(
        """
Uses **actual historical returns** (no hypothetical transformation) over an identified worst-case window:
- Worst 1-month portfolio period
- Worst 3-month portfolio period
- Worst 20-trading-day portfolio period
- Worst small-cap fund period
- Worst benchmark drawdown period (if benchmark data exists)

Once a window is identified, every portfolio fund's own actual compounded return over that exact window is
reported — not just the fund that anchored the window's discovery.
"""
    )

    st.markdown("### B. Deterministic Stress")
    if stress_scenarios.empty:
        st.info(f"`{STRESS_SCENARIOS_PATH}` not found.")
    else:
        st.dataframe(stress_scenarios, width="stretch", hide_index=True)
    st.caption('Disclosure embedded in every deterministic row\'s rationale: "Deterministic stress scenarios are illustrative assumptions, not forecasts."')

    st.markdown("### C. Interactive Custom Shocks")
    st.markdown(
        "The Scenario Stress Testing page's 'Custom Shock' mode accepts user-defined fund-level shocks and "
        "portfolio allocation sliders, and recomputes the same attribution math live, in-memory — this is "
        "**never** persisted to `stress_results.csv`; it exists only for interactive what-if exploration."
    )

    st.markdown("### Default Portfolio Weights")
    if portfolio_weights.empty:
        st.info(f"`{PORTFOLIO_WEIGHTS_PATH}` not found.")
    else:
        st.dataframe(portfolio_weights, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Tab 5: Known limitations & disclaimer
# ---------------------------------------------------------------------------

with tab_limitations:
    st.markdown("### Known Limitations")
    st.markdown(
        """
- **Fixed, small fund universe** (5 category-proxy sleeves) — not a representative sample and not a
  recommendation set. Only Direct Growth plans are covered.
- **Data horizon starts 2021-01-01** — pre-2021 stress events (2020 COVID crash, 2018 IL&FS) are not captured
  in historical replay unless a comparably severe post-2021 window exists.
- **No survivorship-bias correction** — a discontinued/restructured fund or benchmark would need manual review.
- **Expense ratios, exit loads, and taxation are not modeled** — returns are NAV-to-NAV (already net of expense
  ratio, but not of investor-level tax drag).
- **No SIP cash-flow analytics** — all growth calculations assume a lump-sum entry, not staggered contributions.
- **Risk-free rate is a single flat assumption** (default 6% annual), not a term-structure or T-bill series.
- **Fixed 252-trading-day annualization convention**, though actual NSE trading calendars vary slightly by year.
- **Recovery period uses the fund's own NAV series only** — it does not model an investor's actual entry/exit timing.
- **`HYBRID_65_35` is an internally synthesized approximation** (65% NIFTY50_TRI + 35% flat 6% cash accrual),
  not an official published benchmark; real balanced-advantage funds use dynamic, tactical allocation this
  static blend does not capture.
- **Suitability thresholds are a transparent, documented rules-based approximation** (`formula_audit.md` §8),
  not a regulatory or empirically back-tested framework.
- **Beta / tracking error / information ratio / capture** computed against a `PRICE_INDEX_PROXY_NOT_TRI`
  benchmark inherit that proxy's understatement of true TRI returns.
- **No intraday data** — all analytics are end-of-day; dashboard figures are only as fresh as the last
  `refresh_data.py` run (nominal 24-hour cache TTL, not real-time).
"""
    )
    st.caption("Full detail: `00_project_control/limitations.md`.")

    st.markdown("### Disclaimer")
    st.error(EDUCATIONAL_DISCLAIMER)
    st.warning(STRESS_TEST_DISCLAIMER)
    st.warning(SUITABILITY_DISCLAIMER)
    st.warning(BENCHMARK_PROXY_DISCLAIMER)
