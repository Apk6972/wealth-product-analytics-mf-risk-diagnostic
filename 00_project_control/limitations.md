# Known Limitations — MF Risk Diagnostic Module

This document must be kept current and is surfaced (in condensed form) on the Streamlit Methodology page. It exists so that every analytical claim in the app carries an honest disclosure of its boundaries.

---

## 1. Data Sourcing Limitations

### 1.1 Mutual Fund NAV (MFAPI)

- MFAPI (`https://api.mfapi.in/mf/{scheme_code}`) is a **free public convenience API, not the official source-of-record**. AMFI remains the official source for Indian mutual fund NAV disclosures.
- MFAPI availability, uptime, and historical completeness are outside this project's control. A stale/expired cache may be used (with an explicit warning) if a live fetch fails.
- Scheme codes are fetched under `NEEDS_API_METADATA_VERIFICATION` until the fetcher confirms the returned scheme name matches `expected_scheme_name`. Until verified, downstream numbers should be treated as provisional.

### 1.2 Benchmark / Index TRI Data

- Programmatic NSE / Nifty Indices TRI fetching is the priority-1 source but is inherently more fragile than a paid data vendor (session/cookie handling, rate limiting, and endpoint changes can break it without notice).
- If a maintained Python wrapper/scraper is used instead, that library's own maintenance status becomes an implicit dependency risk.
- If yfinance is used as a last-resort fallback (e.g. `^NSEI`), it represents a **price index, not a Total Returns Index**. It is labelled `source_quality = PRICE_INDEX_PROXY_NOT_TRI` and must never be silently treated as equivalent to an official TRI series. Any metric computed on a proxy benchmark inherits this caveat.
- If no valid TRI source and no usable cache exist, the pipeline fails fast rather than inventing or substituting values — this means some analyses may be temporarily unavailable rather than silently wrong.

### 1.3 Hybrid Benchmark (`HYBRID_65_35`)

- This is an **internally synthesized approximation** (65% NIFTY50_TRI + 35% flat 6% annualized cash accrual), not an official, published benchmark index. Real hybrid/balanced-advantage funds use dynamic equity-debt allocation, tactical hedges, and arbitrage positions that this static blend does not capture. Benchmark-relative metrics for HDFC Balanced Advantage should be read with this simplification in mind.

## 2. Coverage & Scope Limitations

- **Fund universe is fixed and small (5 sleeves)**, chosen as category proxies for demonstration — not a representative sample of the broader mutual fund universe, and not a recommendation set.
- Only **Direct Growth** plans are covered; Regular plans, IDCW options, and other share classes are out of scope.
- Data horizon starts **1 January 2021**; pre-2021 behaviour (e.g. 2020 COVID crash, 2018 IL&FS stress) is not captured in historical replay stress tests unless a fund/benchmark happens to have a comparably severe window after 2021.
- No survivorship-bias correction is performed; if a fund or benchmark series is discontinued or restructured, it would need manual review before continued use.

## 3. Methodological Simplifications

- Expense ratios, exit loads, and taxation (STCG/LTCG, indexation) are **not modeled** — all returns are NAV-to-NAV, which already reflects the fund's expense ratio but not investor-level tax drag.
- No SIP (systematic investment plan) cash-flow analytics — all return/growth calculations assume a lump-sum entry ("Growth of ₹1 crore" style framing), not staggered contributions.
- Risk-free rate is a single flat assumption (default 6% annual) rather than a term-structure or T-bill time series; Sharpe/Sortino are only as good as this simplification.
- Trading-day annualization uses a fixed 252-day convention; actual NSE trading calendars vary slightly year to year.
- Recovery period is measured on the fund's own daily NAV series only; it does not account for an investor's actual entry/exit timing.
- Suitability scoring thresholds (how factor values map to profile/role/action labels) are a rules-based approximation, not a regulatory or empirically back-tested suitability framework. The exact thresholds, point scale, and profile/role/action mapping are numerically defined and documented in `formula_audit.md` §8 (implemented in `04_streamlit_app/src/suitability.py`); they represent one reasonable, transparently-disclosed way to bucket historical risk metrics, not the only valid one. `benchmarks.py` (Phase 6) is now implemented, so rolling beta and downside capture are available as suitability factors for every fund (`benchmark_relative_data_available = True`); the graceful "factor excluded, never defaulted to a guessed value" degradation path in `suitability.py` remains in place for any future fund/benchmark pairing that lacks aligned data.
- `benchmark_metrics.csv` / `rolling_benchmark_metrics.csv` beta, tracking error, and information ratio are computed against each fund's *primary* benchmark only (per `benchmark_map.csv`); several primary benchmarks (`NIFTY50_TRI`, `NIFTY100_TRI`, `NIFTY500_TRI`) are currently `PRICE_INDEX_PROXY_NOT_TRI` rather than true TRI series (see the benchmark data risk note above), so beta/tracking error/capture figures for funds mapped to those benchmarks inherit that same data-quality caveat.

## 4. Operational / Runtime Limitations

- The Streamlit app is designed to read only from `02_processed_data/`; if `refresh_data.py` has not been run recently, dashboard figures can lag real-world NAV/benchmark levels by however long the cache/refresh cadence allows (nominally 24 hours per the cache rule, but only as fresh as the last manual/scheduled refresh).
- Cache-expiry fallback (`CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE`) intentionally trades timeliness for availability — the UI must always surface this state rather than presenting stale data as current.
- No intraday data; all analytics are end-of-day.

## 5. Positioning Limitations (Must Not Be Violated)

- This project is an **educational analytics proof-of-work project**, not investment advice, and not a fund-recommendation engine.
- Deterministic stress scenarios are **illustrative assumptions**, not forecasts or probability-weighted outcomes.
- Suitability output is diagnostic/educational language only (e.g. "Cap exposure", "Review benchmark-relative behaviour") — never a buy/sell/hold instruction.

## 6. Open Items to Resolve Before Publication

- [ ] Confirm final scheme codes pass `VERIFIED_VIA_MFAPI_METADATA` (none may remain `NEEDS_API_METADATA_VERIFICATION` or `FAILED_METADATA_CHECK`).
- [ ] Confirm a working priority-1 (or documented fallback) benchmark TRI fetch path exists for all five required benchmarks (`NIFTY50_TRI`, `NIFTY100_TRI`, `NIFTY500_TRI`, `NIFTYSMALLCAP250_TRI`) plus `HYBRID_65_35`.
- [x] Define exact suitability scoring thresholds and add them to `formula_audit.md` — done in `formula_audit.md` §8, implemented in `04_streamlit_app/src/suitability.py`.
- [x] Implement `benchmarks.py` (Phase 6) and re-score rolling beta / downside capture in `suitability_results.csv` — done; `04_streamlit_app/src/benchmarks.py` is implemented and wired into `refresh_data.py` (Step 7/9), and `suitability_results.csv` has been regenerated with `benchmark_relative_data_available = True` for every fund.
- [ ] Confirm no fund/benchmark carries a `FAIL` status in `data_quality_report.csv`.
- [ ] Re-review this file at the end of each build phase and append any newly discovered limitation.
