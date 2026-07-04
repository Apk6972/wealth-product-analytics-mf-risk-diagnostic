# Master Project Brief — MF Risk Diagnostic Module

Status: Locked (Phase 0 complete)
Source of truth: `00_project_control/master_project_instructions.md.md`
Version: API-first (supersedes any prior manual-data workflow)

---

## 1. Identity

| Item | Value |
|---|---|
| Project name | MF Risk Diagnostic Module |
| Parent positioning | Wealth Product Analytics OS — Mutual Fund Risk Diagnostic Module |
| Public hook | "What Risk Created the Return?" |
| Nature | Educational analytics proof-of-work project. **Not investment advice.** |

## 2. Core Philosophy

This is **not** a "find the best mutual fund" dashboard.

The system answers:

> What risk created the return, how painful was the return path, and which client profile can actually sit through it?

It converts five selected Indian mutual fund sleeves into return-path analytics, benchmark-relative behaviour, rolling risk metrics, stress loss, attribution, and suitability insights.

## 3. Public-Facing Artifact Stack

1. Streamlit-first webapp (primary public artifact)
2. Excel model of record
3. Power BI screenshot deck (not the main app — used for polished screenshots only)
4. GitHub README
5. Notion methodology note
6. LinkedIn carousel

## 4. Data Horizon & Quant Standard

- **Horizon:** 1 January 2021 → latest available date
- **Standard:** Daily backend, monthly/rolling dashboard outputs
- **Risk-free rate default:** 6% annual, overridable

## 5. Technical Signal (Required Analytics Surface)

Daily NAV/price, daily returns, monthly NAV/index levels, monthly returns, CAGR, annualized volatility, downside deviation, Sharpe, Sortino, max drawdown, recovery period, Daily VaR 95, Daily CVaR 95, Monthly VaR 95, Monthly CVaR 95, rolling 3M/6M/12M/24M/36M returns, rolling volatility, rolling Sharpe, rolling beta, rolling tracking error, rolling information ratio, upside capture, downside capture, benchmark-relative analytics, historical replay stress testing, deterministic stress testing, stress attribution, client suitability interpretation.

## 6. API-First Final Architecture

```text
API sources / programmatic fetchers
        ↓
Raw API cache layer                 (01_raw_data/api_cache/)
        ↓
Schema validation layer             (data_cleaning.py → data_quality_report.csv)
        ↓
Clean daily NAV + benchmark tables  (nav_daily_clean.csv, benchmark_daily.csv)
        ↓
Daily returns engine
        ↓
Monthly returns engine
        ↓
Rolling metrics engine
        ↓
Benchmark-relative analytics
        ↓
Stress testing + attribution engine
        ↓
Suitability engine
        ↓
Processed CSV database              (02_processed_data/)
        ↓
Streamlit webapp                    (reads processed CSVs only)
        ↓
Excel model of record
        ↓
Power BI screenshot deck
        ↓
LinkedIn carousel + GitHub/Notion case study
```

### Non-Negotiable Runtime Rule

The public Streamlit app must **never** fetch live data on every page load.

Correct sequence:

```text
User clicks Refresh Data / developer runs refresh script
        ↓
API fetch executes → raw data cached locally → processed CSVs regenerated
        ↓
Streamlit reads processed CSVs
```

Incorrect (forbidden) sequence: `app page load → live API call → calculation → chart`.

## 7. Data Source Hierarchy (Summary)

| Layer | Primary | Fallback | Fail-fast condition |
|---|---|---|---|
| Mutual fund NAV | MFAPI (`https://api.mfapi.in/mf/{scheme_code}`) | 24h cache; expired cache with warning if live fetch fails | No cache + fetch fails → error |
| Benchmark / index TRI | Programmatic NSE / Nifty Indices TRI fetch | (2) maintained Python wrapper/scraper → (3) yfinance price-index proxy (explicitly labelled `PRICE_INDEX_PROXY_NOT_TRI`, disclosed) | No valid source + no cache → error, no invented values |

AMFI remains the official source-of-record for NAV disclosures; MFAPI is used for reproducible programmatic extraction. This must be disclosed on the Methodology page.

## 8. Final Fund Universe (Analytics Sleeves, Not Recommendations)

| Sleeve | Fund | Fund Label | Analytical Role |
|---|---|---|---|
| Passive core equity | UTI Nifty 50 Index Fund — Direct Growth | UTI Nifty 50 Index | Clean market beta |
| Active large-cap | ICICI Prudential Bluechip Fund — Direct Growth | ICICI Bluechip | Active large-cap exposure |
| Flexi-cap allocator | Parag Parikh Flexi Cap Fund — Direct Growth | Parag Parikh Flexi Cap | Diversified equity allocator |
| Hybrid allocation | HDFC Balanced Advantage Fund — Direct Growth | HDFC Balanced Advantage | Lower-volatility allocation sleeve |
| High-risk satellite | Nippon India Small Cap Fund — Direct Growth | Nippon India Small Cap | Small-cap / aggressive satellite |

> Disclaimer: Funds are selected as category proxies for analytics demonstration, not as investment recommendations.

## 9. Benchmark Map (Summary)

| Fund | Primary Benchmark | Secondary Benchmark |
|---|---|---|
| UTI Nifty 50 Index | NIFTY50_TRI | NIFTY500_TRI |
| ICICI Bluechip | NIFTY100_TRI | NIFTY500_TRI |
| Parag Parikh Flexi Cap | NIFTY500_TRI | NIFTY50_TRI |
| HDFC Balanced Advantage | HYBRID_65_35 (internal synthetic) | NIFTY50_TRI |
| Nippon India Small Cap | NIFTYSMALLCAP250_TRI | NIFTY500_TRI |

`HYBRID_65_35` = 65% NIFTY50_TRI + 35% daily-accrued 6% cash/debt proxy. Disclosed as an internally synthesized approximation, not an official benchmark.

## 10. Streamlit App Layout (8 Pages)

1. Executive Risk Review
2. Fund Due Diligence
3. Benchmark Behaviour
4. Rolling Risk & Return
5. Drawdown & Tail Risk
6. Scenario Stress Testing
7. Suitability & Action Board
8. Methodology

## 11. Final Public Positioning

> I built an API-first Streamlit MF Risk Diagnostic Module that fetches selected Indian mutual fund NAV and benchmark data programmatically, converts it into return-path analytics, rolling risk-adjusted behaviour, benchmark-relative metrics, drawdown, tail risk, stress attribution, and client suitability diagnostics.

LinkedIn hook:

> Most mutual fund comparisons ask: "Which fund gave the highest return?"
> I wanted to ask: "What risk created that return — and which client can actually sit through it?"

## 12. Locked Decisions (Phase 0 Output)

- [x] Project name locked
- [x] Fund universe locked (5 sleeves)
- [x] Scheme codes marked for API metadata verification (`NEEDS_API_METADATA_VERIFICATION`)
- [x] Benchmark map locked
- [x] Data horizon locked (Jan 2021 → latest)
- [x] Streamlit-first public artifact locked
- [x] API-first data pipeline locked

## 13. Related Control Documents

- `implementation_plan.md` — phased build sequence and pass conditions
- `model_governance.md` — operating rules, change control, disclosure requirements
- `formula_audit.md` — every formula, frequency, and interpretation rule
- `limitations.md` — known risks, data caveats, and scope boundaries
- `data_dictionary.md` — schema for every raw, cached, and processed file
