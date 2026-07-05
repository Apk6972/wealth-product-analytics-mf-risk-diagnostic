# MF Risk Diagnostic Module

**Wealth Product Analytics OS — Mutual Fund Risk Diagnostic Module**

---

## 1. Project Objective

This project is an **API-first, educational analytics proof-of-work** that converts five selected Indian mutual fund sleeves into return-path diagnostics: benchmark-relative behaviour, rolling risk metrics, drawdown and tail risk, stress loss attribution, and client-profile suitability labels.

It is built as a **Streamlit-first webapp**, supported by a processed-CSV data layer, an Excel model-of-record export, and planned Power BI / Notion / LinkedIn artifacts.

**This is not investment advice.** Fund selection is illustrative only.

---

## 2. Public Hook: What Risk Created the Return?

> Most mutual fund comparisons ask: *"Which fund gave the highest return?"*
>
> This project asks: **"What risk created that return — and which client profile can actually sit through it?"**

The objective is not to rank funds by return alone. It is to understand:

- what risk created the return,
- how painful the return path was, and
- which sleeve may break first under stress.

---

## 3. Why This Is Not a Generic MF Dashboard

| Generic MF dashboard | This project |
|---|---|
| Ranks funds by trailing return | Explains return *path* and risk drivers |
| Shows NAV charts without context | Links return to volatility, drawdown, tail risk, and stress |
| Uses a single shared benchmark | Matches each fund to its own primary benchmark |
| Hides data sourcing | Labels every series with `source_quality` (API, cache, proxy, approximation) |
| Implies buy/sell guidance | Outputs educational suitability diagnostics only |

This is a **fixed, small demonstration universe** (5 Direct Growth sleeves), not a representative sample of the broader mutual fund market and not a recommendation set.

---

## 4. Data Architecture

```text
API sources / programmatic fetchers
        ↓
Raw API cache layer                 (01_raw_data/api_cache/)
        ↓
Schema validation layer             (data_cleaning.py → data_quality_report.csv)
        ↓
Clean daily NAV + benchmark tables  (nav_daily_clean.csv, benchmark_daily.csv)
        ↓
Daily returns → Monthly returns → Rolling metrics
        ↓
Benchmark-relative analytics → Stress testing + attribution → Suitability engine
        ↓
Processed CSV database              (02_processed_data/)
        ↓
Streamlit webapp                    (reads processed CSVs only — never live-fetches on page load)
        ↓
Excel model of record               (03_excel_model/MF_Risk_Diagnostic_Model.xlsx)
```

**Non-negotiable runtime rule:** the Streamlit app must **never** fetch live data on page load. Data is fetched, cached, validated, and processed by an explicit refresh step; pages read only from `02_processed_data/`.

Configuration (fund universe, benchmark map, portfolio weights, stress scenarios) lives in `01_raw_data/scheme_master/`. Governance documents live in `00_project_control/`.

---

## 5. API / Cache Methodology

### Mutual fund NAV

- **Source:** [MFAPI](https://api.mfapi.in/mf/{scheme_code}) — a free public convenience API.
- **Official source-of-record:** AMFI remains the official source for Indian mutual fund NAV disclosures. MFAPI is used here for reproducible programmatic extraction, not as a regulatory source-of-record.
- **Cache:** responses stored under `01_raw_data/api_cache/mutual_funds/` with a **24-hour TTL**.
- **Metadata check:** returned scheme names are compared against `expected_scheme_name` in `fund_master.csv` before downstream use.

### Benchmark / index data

Priority order (each step is labelled explicitly — nothing is silently upgraded):

1. **NSE / Nifty Indices TRI endpoints** (priority 1)
2. **Custom NSE India scraper** (priority 2)
3. **yfinance price-index levels** (priority 3, last resort) — labelled `PRICE_INDEX_PROXY_NOT_TRI`. These are **price indices, not Total Return Index (TRI) series**. Dividends are excluded; they understate true TRI returns.
4. **Disclosed synthetic approximation** (priority 4) — e.g. `NIFTYSMALLCAP250_TRI` proxy or internally built `HYBRID_65_35`, labelled `DISCLOSED_APPROXIMATION`.

### Cache fallback rules

| Condition | Behaviour |
|---|---|
| Fresh cache (< 24h) | Reuse cache (`CACHE_FRESH`) |
| Live fetch fails, expired cache exists | Use expired cache with `CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE` warning |
| Live fetch fails, no cache | Fail fast — no invented values |

Every observation carries a `source_quality` label. Check `data_quality_report.csv` and the Streamlit **Methodology** page before drawing conclusions from benchmark-relative metrics.

---

## 6. Fund Universe

Five **Direct Growth** sleeves, chosen as category proxies for analytics demonstration — **not investment recommendations**.

| Sleeve | Fund Label | Category | Analytical Role |
|---|---|---|---|
| Passive core equity | UTI Nifty 50 Index | Passive Large Cap | Clean market beta |
| Active large-cap | ICICI Bluechip | Active Large Cap | Active large-cap exposure |
| Flexi-cap allocator | Parag Parikh Flexi Cap | Flexi Cap | Diversified equity allocator |
| Hybrid allocation | HDFC Balanced Advantage | Hybrid / BAF | Lower-volatility allocation sleeve |
| High-risk satellite | Nippon India Small Cap | Small Cap | Small-cap / aggressive satellite |

**Data horizon:** 1 January 2021 → latest available date (enforced in validation; pre-2021 observations are excluded from calculations).

Default illustrative portfolio weights (stress / attribution only):

| Fund | Weight |
|---|---:|
| UTI Nifty 50 Index | 25% |
| ICICI Bluechip | 20% |
| Parag Parikh Flexi Cap | 25% |
| HDFC Balanced Advantage | 15% |
| Nippon India Small Cap | 15% |

---

## 7. Benchmark Map

Each fund is compared against its **own primary benchmark** — never a single shared index across all funds.

| Fund | Primary Benchmark | Secondary Benchmark | Notes |
|---|---|---|---|
| UTI Nifty 50 Index | NIFTY50_TRI | NIFTY500_TRI | Target: Nifty 50 TRI |
| ICICI Bluechip | NIFTY100_TRI | NIFTY500_TRI | Target: Nifty 100 TRI |
| Parag Parikh Flexi Cap | NIFTY500_TRI | NIFTY50_TRI | Target: Nifty 500 TRI |
| HDFC Balanced Advantage | HYBRID_65_35 | NIFTY50_TRI | Internal synthetic: 65% NIFTY50 + 35% flat 6% daily cash accrual |
| Nippon India Small Cap | NIFTYSMALLCAP250_TRI | NIFTY500_TRI | Target: Nifty Smallcap 250 TRI |

**Important:** several required benchmark labels (`NIFTY50_TRI`, `NIFTY100_TRI`, `NIFTY500_TRI`) may currently be sourced as **price-index proxies** (`PRICE_INDEX_PROXY_NOT_TRI`) when official TRI fetch paths are unavailable. `HYBRID_65_35` and the `NIFTYSMALLCAP250_TRI` fallback are **disclosed approximations**, not official published indices. Benchmark-relative metrics inherit these data-quality caveats.

---

## 8. Metrics Calculated

All formulas are documented in `00_project_control/formula_audit.md`. Summary:

### Core fund metrics (`metrics_summary.csv`)

CAGR, annualized volatility, downside deviation, Sharpe ratio, Sortino ratio, max drawdown, longest recovery period, best/worst month, positive month ratio, Daily VaR 95, Daily CVaR 95, Monthly VaR 95, Monthly CVaR 95.

- Default risk-free rate: **6% annual** (overridable, always disclosed).
- VaR/CVaR are always labelled by frequency (daily vs monthly).

### Rolling metrics (`rolling_metrics.csv`)

Rolling 3M / 6M / 12M / 24M / 36M returns (and annualized 12M / 24M / 36M), rolling 63D / 126D / 252D volatility, rolling 252D Sharpe.

### Benchmark-relative metrics (`benchmark_metrics.csv`, `rolling_benchmark_metrics.csv`)

Excess return, beta, tracking error, information ratio, upside capture, downside capture; rolling 252-day beta, tracking error, and information ratio.

Computed only against each fund's primary benchmark, with date alignment and a minimum observation guard (≥ 20 aligned trading days for static metrics).

---

## 9. Stress Testing Methodology

Three modes (see `04_streamlit_app/src/stress.py` and `attribution.py`):

### A. Historical replay

Uses **actual historical returns** over identified worst-case windows:

- Worst 1-month portfolio period
- Worst 3-month portfolio period
- Worst 20-trading-day portfolio period
- Worst small-cap fund period
- Worst benchmark drawdown period (if benchmark data exists)

Pre-2021 stress events (e.g. 2020 COVID crash) are **not captured** unless a comparably severe window exists after 2021-01-01.

### B. Deterministic stress

Fixed illustrative per-fund shocks from `stress_scenarios.csv` (Broad Equity Correction, Small-cap Unwind, Correlation Breakdown, Balanced Risk-Off).

**These are illustrative assumptions, not forecasts or probability-weighted outcomes.**

### C. Custom interactive shocks

The Streamlit Scenario Stress Testing page accepts user-defined fund shocks and portfolio weights for what-if exploration (computed in-memory, not persisted).

### Attribution

```text
Fund Loss Contribution        = Fund Weight × Fund Stress Return
Total Portfolio Stress Return = Σ Fund Loss Contribution
Stress Loss Share             = Fund Loss Contribution / Total Portfolio Stress Return
```

Default base portfolio value: **₹1 crore** (₹10,000,000).

Key insight preserved throughout: **allocation weight is not the same as stress loss share.**

---

## 10. Suitability Engine

Implemented in `04_streamlit_app/src/suitability.py`. Converts already-computed quantitative outputs into **educational wealth-management diagnostics** — not buy/sell/hold instructions.

**Client profiles:** Conservative, Balanced, Growth, Aggressive.

**Factors used (when available):** max drawdown, volatility, Daily CVaR 95, small-cap exposure, rolling beta, downside capture, stress loss share vs. weight, recovery period. Missing factors are excluded from scoring — never guessed.

**Outputs per (fund, profile):** suitability role (Core / Satellite / Defensive sleeve / Aggressive satellite / Watchlist / Unsuitable for profile), risk warning, recommended educational action, rationale.

Scoring thresholds are a transparent, rules-based approximation documented in `formula_audit.md` §8 — not a regulatory or empirically back-tested suitability framework.

Output file: `02_processed_data/suitability_results.csv`.

---

## 11. How to Run Locally

Requires **Python 3.11 or 3.12**.

```bash
# Clone and enter the repository
cd wealth-product-analytics-mf-risk-diagnostic

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -r requirements.txt
```

Ensure processed data exists under `02_processed_data/` (run the refresh step below on a fresh clone). Then launch the app:

```bash
streamlit run app.py
```

**Eight pages:**

1. Executive Risk Review
2. Fund Due Diligence
3. Benchmark Behaviour
4. Rolling Risk & Return
5. Drawdown & Tail Risk
6. Scenario Stress Testing
7. Suitability & Action Board
8. Methodology

Optional — export the Excel model of record:

```bash
python 04_streamlit_app/export_excel_model.py
```

Output: `03_excel_model/MF_Risk_Diagnostic_Model.xlsx`

---

## 12. How to Refresh Data

Run manually (never triggered automatically on Streamlit page load):

```bash
python 04_streamlit_app/refresh_data.py
```

This executes the 9-step API-first pipeline:

1. Fetch mutual fund NAV (MFAPI → cache → `nav_daily_clean.csv`)
2. Fetch benchmarks (NSE / scraper / yfinance proxy / synthetic → `benchmark_daily.csv`)
3. Validate and clean data → `data_quality_report.csv`
4. Calculate daily and monthly returns
5. Calculate fund-level metrics → `metrics_summary.csv`
6. Calculate rolling metrics → `rolling_metrics.csv`
7. Calculate benchmark-relative analytics → `benchmark_metrics.csv`, `rolling_benchmark_metrics.csv`
8. Run stress engine → `stress_results.csv`
9. Run attribution engine → `attribution_results.csv`

After a successful refresh, regenerate suitability diagnostics if needed (reads upstream processed CSVs):

```bash
python -c "import sys; sys.path.insert(0, '04_streamlit_app/src'); from suitability import run_suitability_engine; run_suitability_engine()"
```

Then optionally re-export the Excel workbook:

```bash
python 04_streamlit_app/export_excel_model.py
```

Review `02_processed_data/data_quality_report.csv` for any `WARNING` or `FAIL` statuses before relying on dashboard figures.

---

## 13. Known Limitations

This is a condensed summary. Full detail: `00_project_control/limitations.md`.

**Data sourcing**

- MFAPI is a convenience API, not the official AMFI source-of-record; uptime and completeness are outside this project's control.
- Benchmark TRI fetching is fragile compared to a paid vendor; endpoint or scraper breakage can occur without notice.
- yfinance fallbacks are **price-index proxies**, not TRI — labelled `PRICE_INDEX_PROXY_NOT_TRI`.
- `HYBRID_65_35` is an internal synthetic approximation, not an official benchmark.

**Coverage**

- Fixed 5-fund demonstration universe; Direct Growth only.
- Data horizon starts 2021-01-01; earlier market stress is excluded from historical replay.
- No survivorship-bias correction.

**Methodology**

- No taxation, exit loads, or SIP cash-flow modelling — lump-sum NAV-to-NAV framing only.
- Flat 6% risk-free rate; fixed 252-day annualization convention.
- Suitability scoring is a documented rules-based approximation, not regulatory advice.
- Benchmark-relative metrics against proxy benchmarks inherit proxy data-quality caveats.

**Operational**

- Dashboard figures are only as fresh as the last manual refresh (nominal 24h cache TTL).
- End-of-day data only; no intraday analytics.

---

## 14. Disclaimer

This project is an **educational analytics proof-of-work project**. It does **not** constitute investment advice, a recommendation to buy, sell, or hold any security, or a forecast of future performance. Past performance is not indicative of future results.

- Fund selection is **illustrative only** — not a recommendation set.
- Deterministic stress scenarios are **illustrative assumptions**, not forecasts.
- Suitability labels are **educational diagnostics** derived from trailing historical risk metrics; they do not account for an investor's complete financial situation.
- Some benchmark series may be **price-index proxies or disclosed approximations** rather than official TRI data — check `source_quality` before interpreting benchmark-relative comparisons.

---

## 15. Screenshots

> Screenshots not yet captured. To generate: run `streamlit run app.py`, navigate each page with processed data loaded, and save images to `06_outputs/dashboard_screenshots/`.

| Page | Screenshot path |
|---|---|
| Executive Risk Review | `06_outputs/dashboard_screenshots/01_executive_risk_review.png` |
| Fund Due Diligence | `06_outputs/dashboard_screenshots/02_fund_due_diligence.png` |
| Benchmark Behaviour | `06_outputs/dashboard_screenshots/03_benchmark_behaviour.png` |
| Rolling Risk & Return | `06_outputs/dashboard_screenshots/04_rolling_risk_return.png` |
| Drawdown & Tail Risk | `06_outputs/dashboard_screenshots/05_drawdown_tail_risk.png` |
| Scenario Stress Testing | `06_outputs/dashboard_screenshots/06_scenario_stress_testing.png` |
| Suitability & Action Board | `06_outputs/dashboard_screenshots/07_suitability_action_board.png` |
| Methodology | `06_outputs/dashboard_screenshots/08_methodology.png` |

---

## Control Documents

| Document | Purpose |
|---|---|
| `00_project_control/master_project_instructions.md.md` | Authoritative project specification |
| `00_project_control/formula_audit.md` | Every metric formula and interpretation rule |
| `00_project_control/limitations.md` | Data caveats and scope boundaries |
| `00_project_control/data_dictionary.md` | Schema for every config and processed file |
| `00_project_control/model_governance.md` | Operating rules and disclosure requirements |
| `00_project_control/implementation_plan.md` | Phased build sequence |

---

## Repository Structure

```text
00_project_control/     Planning, governance, formula audit, data dictionary, limitations
01_raw_data/             API cache + scheme/benchmark/weight/scenario config
02_processed_data/       Calculation outputs (generated by refresh_data.py)
03_excel_model/          Excel model of record (generated by export_excel_model.py)
04_streamlit_app/        Source modules, pages, refresh/export scripts
05_powerbi_dashboard/    Power BI screenshot deck source (planned)
06_outputs/              Charts, dashboard screenshots, carousel slides, memo PDFs
07_linkedin/             Publication copy (planned)
app.py                   Streamlit navigation entry point
requirements.txt         Python dependencies
```
