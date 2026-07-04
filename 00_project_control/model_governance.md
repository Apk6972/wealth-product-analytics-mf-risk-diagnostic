# Model Governance — MF Risk Diagnostic Module

This document defines the operating rules, change-control discipline, and disclosure obligations for the project. It governs both human and AI-assisted (Cursor) contributions.

---

## 1. Governing Identity

Institutional-grade portfolio analytics proof-of-work project. Final public artifact: Streamlit-first webapp, supported by an Excel model of record, Power BI screenshot deck, GitHub README, Notion methodology, and LinkedIn carousel.

Data approach: **API-first**. The user does not manually input NAV or TRI data. Mutual fund NAV data and benchmark/index data must be fetched programmatically and cached locally.

## 2. Operating Rules (Cursor Rules — canonical copy)

These rules should also be mirrored into `.cursor/rules/project_rules.mdc` during scaffold:

1. Do not invent data.
2. Do not hardcode final outputs.
3. Do not require manual NAV/TRI file input for normal execution.
4. MFAPI is used for automated mutual fund NAV extraction.
5. Benchmark/index data must be fetched programmatically and cached.
6. Do not silently label price-index proxies as TRI.
7. Yahoo/yfinance fallbacks must be labelled as price-index proxies, not TRI.
8. Never make the public Streamlit app fetch live API data on every page load.
9. Every metric must disclose formula, frequency, interpretation, and limitation.
10. Daily and monthly returns must not be mixed incorrectly.
11. Benchmarks must be fund-specific.
12. VaR and CVaR must be labelled by frequency.
13. Stress-test assumptions must be labelled illustrative, not forecasts.
14. Every chart must answer an investment question.
15. Every page must end with interpretation, not just visuals.
16. Keep code modular.
17. Do not modify more than 3 files at once unless explicitly asked.
18. Never rewrite the full repo unless explicitly requested.
19. Keep model auditability higher priority than UI decoration.
20. Maintain README, data dictionary, assumptions log, formula audit, model governance, and limitations files.
21. If uncertain about a financial formula or benchmark source, stop and ask before implementing.

## 3. Data Governance

### 3.1 Cache Rule (applies to every API call)

```text
if cache exists and age < 24 hours:
    use cache
elif cache exists and live fetch fails:
    use expired cache with warning
elif no cache exists and live fetch fails:
    fail with clear error
else:
    fetch live, validate, cache, proceed
```

### 3.2 Source Quality Labelling (mandatory, never silent)

Mutual fund NAV `source_quality` values:

- `API_FETCHED_VERIFIED`
- `API_FETCHED_METADATA_WARNING`
- `CACHE_FRESH`
- `CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE`

Benchmark `source` / `source_quality` values:

- `source = MFAPI` for fund NAV
- `source = INTERNAL_SYNTHETIC_BENCHMARK`, `source_quality = DISCLOSED_APPROXIMATION` for `HYBRID_65_35`
- `source_quality = PRICE_INDEX_PROXY_NOT_TRI` for any Yahoo/yfinance index fallback (e.g. `^NSEI`) — must also trigger a UI methodology warning

### 3.3 Scheme Metadata Verification Gate

`verification_status` values on `fund_master.csv`:

- `NEEDS_API_METADATA_VERIFICATION` (initial state for all funds)
- `VERIFIED_VIA_MFAPI_METADATA` (acceptable match to `expected_scheme_name`)
- `FAILED_METADATA_CHECK` (material mismatch)

**Publication block:** the project must not be published while any fund remains `NEEDS_API_METADATA_VERIFICATION` or `FAILED_METADATA_CHECK`.

### 3.4 Benchmark Fail-Fast Rule

If benchmark TRI data cannot be fetched and no valid cache exists:

- Do not invent benchmark values.
- Do not silently substitute price index data.
- Raise a clear error.
- Show a methodology warning.

### 3.5 Data Quality Gate

`data_quality_report.csv` status values: `PASS`, `WARNING`, `FAIL`.

**Publication block:** do not proceed to LinkedIn publication if any core fund or benchmark has `FAIL`.

## 4. Change Control

- Do not modify more than 3 files at once unless the user explicitly asks for a broader change.
- Never rewrite the full repository unless explicitly requested.
- Each build phase (see `implementation_plan.md`) should be implemented as an isolated, reviewable step — one module or one page at a time.
- No network requests may execute on module import; every fetch must be an explicit, callable function.
- No application code, Python modules, or Streamlit pages are created until this planning phase is explicitly approved and a subsequent scaffold prompt is issued.

## 5. Disclosure Obligations

Every metric surfaced anywhere in the app, Excel model, or Power BI deck must disclose:

1. Formula
2. Frequency (daily vs monthly — never ambiguous)
3. Interpretation
4. Limitation

Every page must end with an interpretation, not just charts/tables.

The Methodology page is the canonical disclosure surface and must cover: data sources, API/cache methodology, date range, fund universe, benchmark map, metric definitions, formula audit, stress assumptions, known limitations, and the standing disclaimer.

## 6. Language Governance

- The project is positioned as a **risk diagnostic system**, never as "find the best fund."
- Suitability output must use educational diagnostic language (Retain / Cap exposure / Stagger allocation / Pair with defensive sleeve / Review benchmark-relative behaviour / Avoid for low drawdown tolerance) — never phrased as investment advice or a recommendation to buy/sell.
- Deterministic stress scenarios must always be labelled illustrative assumptions, not forecasts.
- `HYBRID_65_35` must always be labelled a disclosed blended proxy, not an official benchmark.

## 7. Escalation Rule

If there is uncertainty about a financial formula, a benchmark source, or a data labelling decision, implementation must stop and the ambiguity must be raised for a decision before any code is written. This document set (and its sibling control docs) is the reference to check first.

## 8. Version Control Note

This governance model supersedes any earlier manual-data workflow. Manual AMFI NAV files and manual benchmark TRI files are no longer the primary data source; MFAPI (fund NAV) and programmatic NSE/Nifty Indices fetches (benchmark) are the API-first V1 data layer, not a later V2 convenience layer.
