# MF Risk Diagnostic Module — API-First Project Instructions

## 0. Version Control Note

This file replaces the earlier manual-data workflow.

The previous instructions treated manual AMFI NAV files and manual benchmark TRI files as the primary data source, with MFAPI as a later V2 convenience layer. This updated version changes the data layer to **API-first**:

- Mutual fund NAV data is fetched programmatically.
- Benchmark / index data is fetched programmatically.
- No manual NAV or TRI file input is required for normal execution.
- All fetched data must be cached to local CSV files before downstream calculations.
- The Streamlit app must read processed/cached data, not make live network calls on every page load.

The project remains an educational analytics proof-of-work project. It is not investment advice.

---

# 1. Final Build Direction

## Project Name

**MF Risk Diagnostic Module**

## Parent Positioning

**Wealth Product Analytics OS — Mutual Fund Risk Diagnostic Module**

## Public Hook

**What Risk Created the Return?**

## Public-Facing Artifact

A **Streamlit-first webapp** supported by:

1. Excel model of record
2. Power BI screenshot deck
3. GitHub README
4. Notion methodology note
5. LinkedIn carousel

## Data Horizon

**1 January 2021 to latest available date.**

## Quant Standard

**Daily backend + monthly/rolling dashboard outputs.**

## Technical Signal

The project must include:

- Daily NAV / price data
- Daily returns
- Monthly NAV / index levels
- Monthly returns
- CAGR
- Annualized volatility
- Downside deviation
- Sharpe ratio
- Sortino ratio
- Max drawdown
- Recovery period
- Daily VaR 95
- Daily CVaR 95
- Monthly VaR 95
- Monthly CVaR 95
- Rolling 3M / 6M / 12M / 24M / 36M returns
- Rolling volatility
- Rolling Sharpe
- Rolling beta
- Rolling tracking error
- Rolling information ratio
- Upside capture
- Downside capture
- Benchmark-relative analytics
- Historical replay stress testing
- Deterministic stress testing
- Stress attribution
- Client suitability interpretation

---

# 2. Core Project Philosophy

This is not a generic mutual fund dashboard.

The project should answer:

> What risk created the return, how painful was the return path, and which client profile can actually sit through it?

Do not position the project as:

> A dashboard to find the best mutual fund.

Position it as:

> A portfolio risk diagnostic system that converts selected Indian mutual fund sleeves into return-path analytics, benchmark-relative behaviour, rolling risk metrics, stress loss, attribution, and suitability insights.

---

# 3. API-First Architecture

```text
API sources / programmatic fetchers
        ↓
Raw API cache layer
        ↓
Schema validation layer
        ↓
Clean daily NAV + benchmark tables
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
Processed CSV database
        ↓
Streamlit webapp
        ↓
Excel model of record
        ↓
Power BI screenshot deck
        ↓
LinkedIn carousel + GitHub/Notion case study
```

## Non-Negotiable Runtime Rule

The public Streamlit app must not fetch live data on every user interaction.

Correct sequence:

```text
User clicks Refresh Data / developer runs refresh script
        ↓
API fetch executes
        ↓
Raw data cached locally
        ↓
Processed CSVs regenerated
        ↓
Streamlit reads processed CSVs
```

Incorrect sequence:

```text
User opens dashboard page
        ↓
Every page load hits MFAPI / NSE / Yahoo endpoints
```

That is slow, brittle, and unprofessional.

---

# 4. Data Source Hierarchy — API-First Version

## 4.1 Mutual Fund NAV Data

Primary programmatic source:

```text
MFAPI.in
Endpoint: https://api.mfapi.in/mf/{scheme_code}
```

Use MFAPI for automated fund NAV history extraction.

Caveat:

MFAPI is a free public convenience API, not the official source-of-record. Therefore the methodology page must state:

> Mutual fund NAV history is fetched programmatically using MFAPI for reproducible educational analytics. AMFI remains the official source for Indian mutual fund NAV disclosures.

## 4.2 Benchmark / Index Data

Benchmark data must also be fetched programmatically.

Use this source priority:

### Priority 1 — Programmatic NSE / Nifty Indices TRI fetcher

Fetch TRI data from NSE/Nifty Indices programmatically using a requests-based session with defensive headers, cookies, retry logic, and local caching.

Target outcome:

```text
benchmark_daily.csv
columns: date, benchmark_label, tri_value, source, source_quality
```

### Priority 2 — Accepted Python wrapper / scraper

If direct NSE/Nifty Indices fetching is unstable, use a maintained Python wrapper or scraper, but the output must still normalize into the same schema.

### Priority 3 — yfinance fallback only if explicitly configured

Yahoo Finance symbols such as `^NSEI` generally represent price index proxies, not TRI series.

Do not silently label Yahoo price index data as TRI.

If yfinance is used, set:

```text
source_quality = PRICE_INDEX_PROXY_NOT_TRI
```

and display a methodology warning.

### Fail-Fast Rule

If benchmark TRI data cannot be fetched and no valid cache exists:

- do not invent benchmark values
- do not silently substitute price index data
- raise a clear error
- show a methodology warning

---

# 5. Final Fund Universe

The funds are selected as **analytics sleeves**, not recommendations.

| Sleeve | Fund | Fund Label | Analytical Role |
|---|---|---|---|
| Passive core equity | UTI Nifty 50 Index Fund — Direct Growth | UTI Nifty 50 Index | Clean market beta |
| Active large-cap | ICICI Prudential Bluechip Fund — Direct Growth | ICICI Bluechip | Active large-cap exposure |
| Flexi-cap allocator | Parag Parikh Flexi Cap Fund — Direct Growth | Parag Parikh Flexi Cap | Diversified equity allocator |
| Hybrid allocation | HDFC Balanced Advantage Fund — Direct Growth | HDFC Balanced Advantage | Lower-volatility allocation sleeve |
| High-risk satellite | Nippon India Small Cap Fund — Direct Growth | Nippon India Small Cap | Small-cap / aggressive satellite |

Disclaimer:

> Funds are selected as category proxies for analytics demonstration, not as investment recommendations.

---

# 6. Scheme Master

Create:

```text
01_raw_data/scheme_master/fund_master.csv
```

Required columns:

```csv
fund_label,scheme_code,expected_scheme_name,category,sleeve,primary_benchmark,secondary_benchmark,include,verification_status
```

Use these codes initially, but keep verification status explicit:

```csv
fund_label,scheme_code,expected_scheme_name,category,sleeve,primary_benchmark,secondary_benchmark,include,verification_status
UTI Nifty 50 Index,120716,UTI Nifty 50 Index Fund - Direct Growth,Passive Large Cap,Core Equity,NIFTY50_TRI,NIFTY500_TRI,TRUE,NEEDS_API_METADATA_VERIFICATION
ICICI Bluechip,119519,ICICI Prudential Bluechip Fund - Direct Growth,Active Large Cap,Core Equity,NIFTY100_TRI,NIFTY500_TRI,TRUE,NEEDS_API_METADATA_VERIFICATION
Parag Parikh Flexi Cap,122639,Parag Parikh Flexi Cap Fund - Direct Growth,Flexi Cap,Diversified Equity,NIFTY500_TRI,NIFTY50_TRI,TRUE,NEEDS_API_METADATA_VERIFICATION
HDFC Balanced Advantage,119062,HDFC Balanced Advantage Fund - Direct Growth,Hybrid / BAF,Hybrid Allocation,HYBRID_65_35,NIFTY50_TRI,TRUE,NEEDS_API_METADATA_VERIFICATION
Nippon India Small Cap,118778,Nippon India Small Cap Fund - Direct Growth,Small Cap,Satellite Equity,NIFTYSMALLCAP250_TRI,NIFTY500_TRI,TRUE,NEEDS_API_METADATA_VERIFICATION
```

## Scheme Verification Rule

The API fetcher must verify the returned scheme metadata against `expected_scheme_name`.

If mismatch is material:

```text
verification_status = FAILED_METADATA_CHECK
```

If acceptable:

```text
verification_status = VERIFIED_VIA_MFAPI_METADATA
```

Do not publish the project while any fund remains `NEEDS_API_METADATA_VERIFICATION` or `FAILED_METADATA_CHECK`.

---

# 7. Benchmark Map

Create:

```text
01_raw_data/scheme_master/benchmark_map.csv
```

Required columns:

```csv
fund_label,primary_benchmark,secondary_benchmark,benchmark_methodology,tri_required,proxy_allowed,proxy_warning
```

Use:

```csv
fund_label,primary_benchmark,secondary_benchmark,benchmark_methodology,tri_required,proxy_allowed,proxy_warning
UTI Nifty 50 Index,NIFTY50_TRI,NIFTY500_TRI,Nifty 50 Total Returns Index,TRUE,FALSE,
ICICI Bluechip,NIFTY100_TRI,NIFTY500_TRI,Nifty 100 Total Returns Index preferred; fallback Nifty 50 TRI only if Nifty 100 TRI unavailable,TRUE,TRUE,Fallback must be disclosed
Parag Parikh Flexi Cap,NIFTY500_TRI,NIFTY50_TRI,Nifty 500 TRI as diversified equity benchmark,TRUE,FALSE,
HDFC Balanced Advantage,HYBRID_65_35,NIFTY50_TRI,65% Nifty 50 TRI + 35% daily 6% cash/debt proxy,TRUE,TRUE,Hybrid benchmark is internally synthesized approximation
Nippon India Small Cap,NIFTYSMALLCAP250_TRI,NIFTY500_TRI,Nifty Smallcap 250 TRI,TRUE,FALSE,
```

---

# 8. Hybrid Benchmark Construction

For HDFC Balanced Advantage, create `HYBRID_65_35` internally.

Formula:

```text
Hybrid Return_t = 0.65 × NIFTY50_TRI_Return_t + 0.35 × (0.06 / 252)
```

Then create synthetic index value:

```text
HYBRID_65_35_Value_0 = 100
HYBRID_65_35_Value_t = HYBRID_65_35_Value_{t-1} × (1 + Hybrid Return_t)
```

Label clearly:

> HYBRID_65_35 is a disclosed blended proxy, not an official benchmark.

---

# 9. Folder Structure

Create:

```text
wealth-product-analytics-mf-risk-diagnostic/
│
├── README.md
├── requirements.txt
├── app.py
├── .gitignore
│
├── 00_project_control/
│   ├── master_project_instructions.md
│   ├── model_governance.md
│   ├── assumptions_log.md
│   ├── data_dictionary.md
│   ├── limitations.md
│   └── formula_audit.md
│
├── 01_raw_data/
│   ├── api_cache/
│   │   ├── mutual_funds/
│   │   ├── benchmarks/
│   │   └── metadata/
│   └── scheme_master/
│       ├── fund_master.csv
│       ├── benchmark_map.csv
│       ├── portfolio_weights.csv
│       └── stress_scenarios.csv
│
├── 02_processed_data/
│   ├── nav_daily_clean.csv
│   ├── returns_daily.csv
│   ├── nav_monthly.csv
│   ├── returns_monthly.csv
│   ├── benchmark_daily.csv
│   ├── benchmark_monthly.csv
│   ├── rolling_metrics.csv
│   ├── benchmark_metrics.csv
│   ├── rolling_benchmark_metrics.csv
│   ├── metrics_summary.csv
│   ├── stress_results.csv
│   ├── attribution_results.csv
│   ├── suitability_results.csv
│   └── data_quality_report.csv
│
├── 03_excel_model/
│   └── MF_Risk_Diagnostic_Model.xlsx
│
├── 04_streamlit_app/
│   ├── pages/
│   │   ├── 1_Executive_Risk_Review.py
│   │   ├── 2_Fund_Due_Diligence.py
│   │   ├── 3_Benchmark_Behaviour.py
│   │   ├── 4_Rolling_Risk_Return.py
│   │   ├── 5_Drawdown_Tail_Risk.py
│   │   ├── 6_Scenario_Stress_Testing.py
│   │   ├── 7_Suitability_Action_Board.py
│   │   └── 8_Methodology.py
│   │
│   ├── src/
│   │   ├── api_fetch.py
│   │   ├── data_loader.py
│   │   ├── data_cleaning.py
│   │   ├── returns.py
│   │   ├── metrics.py
│   │   ├── rolling_metrics.py
│   │   ├── benchmarks.py
│   │   ├── stress.py
│   │   ├── attribution.py
│   │   ├── suitability.py
│   │   ├── charts.py
│   │   └── utils.py
│   │
│   └── assets/
│       └── style_notes.md
│
├── 05_powerbi_dashboard/
│   └── MF_Risk_Diagnostic_Dashboard.pbix
│
├── 06_outputs/
│   ├── charts/
│   ├── dashboard_screenshots/
│   ├── carousel_slides/
│   └── memo_pdf/
│
└── 07_linkedin/
    ├── carousel_script.md
    ├── post_caption.md
    ├── comment_cta.md
    └── recruiter_positioning.md
```

---

# 10. Python Setup

Use Python 3.11 or 3.12.

Create:

```text
requirements.txt
```

Contents:

```txt
pandas
numpy
scipy
statsmodels
plotly
streamlit
openpyxl
kaleido
python-dateutil
requests
yfinance
beautifulsoup4
lxml
```

Install:

```bash
pip install -r requirements.txt
```

---

# 11. API Fetch Module

Create:

```text
04_streamlit_app/src/api_fetch.py
```

This is now a **core V1 module**, not a later V2 module.

## 11.1 Responsibilities

`api_fetch.py` must:

1. Fetch mutual fund NAV history from MFAPI.
2. Verify scheme metadata.
3. Cache raw mutual fund data.
4. Fetch benchmark/index data programmatically.
5. Cache raw benchmark/index data.
6. Create HYBRID_65_35 internally.
7. Generate normalized daily NAV and benchmark CSVs.
8. Never fetch live data automatically on Streamlit page import.

## 11.2 Cache Directory

```text
01_raw_data/api_cache/
```

Subdirectories:

```text
01_raw_data/api_cache/mutual_funds/
01_raw_data/api_cache/benchmarks/
01_raw_data/api_cache/metadata/
```

## 11.3 Cache Rule

For every API call:

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

## 11.4 Mutual Fund Fetch Function

Required function:

```python
def fetch_mutual_fund_nav(scheme_code: str, fund_label: str, expected_scheme_name: str) -> pd.DataFrame:
    """
    Fetch historical NAV data from MFAPI with 24-hour cache.
    Return normalized schema:
    date, fund_label, scheme_code, scheme_name, nav, source, source_quality
    """
```

Required normalized output:

```text
date
fund_label
scheme_code
scheme_name
nav
source
source_quality
```

`source` should be:

```text
MFAPI
```

`source_quality` should be:

```text
API_FETCHED_VERIFIED
API_FETCHED_METADATA_WARNING
CACHE_FRESH
CACHE_EXPIRED_USED_AFTER_FETCH_FAILURE
```

## 11.5 Combined Fund Fetch Function

Required function:

```python
def fetch_all_mutual_funds() -> pd.DataFrame:
    """
    Reads fund_master.csv, fetches all included funds, validates schema,
    and writes 02_processed_data/nav_daily_clean.csv.
    """
```

Output file:

```text
02_processed_data/nav_daily_clean.csv
```

---

# 12. Benchmark API Fetch Module

Benchmark fetching must be part of `api_fetch.py` or `benchmarks.py`, but it must be callable explicitly.

## 12.1 Required Output Schema

```text
02_processed_data/benchmark_daily.csv
```

Columns:

```text
date
benchmark_label
tri_value
source
source_quality
```

## 12.2 Required Benchmarks

```text
NIFTY50_TRI
NIFTY100_TRI
NIFTY500_TRI
NIFTYSMALLCAP250_TRI
HYBRID_65_35
```

## 12.3 Benchmark Fetch Logic

Use this source hierarchy:

```text
1. Direct NSE / Nifty Indices programmatic TRI fetch
2. Maintained Python wrapper/scraper, if available
3. yfinance price-index fallback only if explicitly allowed and disclosed
4. fail fast if no valid source and no cache
```

## 12.4 Mandatory Warning About Yahoo Symbols

Do not label `^NSEI` as Nifty 50 TRI.

If yfinance is used for `^NSEI`, classify it as:

```text
PRICE_INDEX_PROXY_NOT_TRI
```

and show warning:

> Yahoo Finance index symbols are used only as price-index fallback proxies where TRI data cannot be fetched. They are not equivalent to official TRI series.

## 12.5 Required Function

```python
def fetch_benchmark_series(benchmark_label: str) -> pd.DataFrame:
    """
    Fetch benchmark/index data programmatically, validate schema,
    cache output, and return date, benchmark_label, tri_value, source, source_quality.
    """
```

## 12.6 Hybrid Benchmark Function

```python
def build_hybrid_65_35(nifty50_tri: pd.DataFrame, cash_rate: float = 0.06) -> pd.DataFrame:
    """
    Build HYBRID_65_35 using:
    Hybrid Return_t = 0.65 * NIFTY50_TRI_Return_t + 0.35 * (cash_rate / 252)
    """
```

Output:

```text
benchmark_label = HYBRID_65_35
source = INTERNAL_SYNTHETIC_BENCHMARK
source_quality = DISCLOSED_APPROXIMATION
```

---

# 13. Refresh Script

Create:

```text
04_streamlit_app/refresh_data.py
```

This script should execute the full API-first pipeline:

```text
1. Fetch all mutual fund NAV data
2. Fetch all benchmark/index data
3. Build HYBRID_65_35
4. Generate daily returns
5. Generate monthly returns
6. Generate metrics
7. Generate rolling metrics
8. Generate benchmark metrics
9. Generate stress results
10. Generate attribution results
11. Generate suitability results
12. Generate data quality report
```

Run manually:

```bash
python 04_streamlit_app/refresh_data.py
```

Streamlit may include a protected refresh button later, but normal page loads must read processed CSVs only.

---

# 14. Data Quality Report

Create:

```text
02_processed_data/data_quality_report.csv
```

Required checks:

```text
fund_label / benchmark_label
asset_type
source
source_quality
first_date
last_date
observation_count
missing_value_count
duplicate_date_count
suspicious_return_count_gt_10pct
suspicious_return_count_lt_minus_10pct
metadata_verification_status
status
```

Status values:

```text
PASS
WARNING
FAIL
```

Do not proceed to LinkedIn publication if any core fund or benchmark has `FAIL`.

---

# 15. Data Cleaning Module

Create:

```text
04_streamlit_app/src/data_cleaning.py
```

In the API-first version, this file does not read manual AMFI files.

It should:

1. Validate `nav_daily_clean.csv` created by API fetch.
2. Validate `benchmark_daily.csv` created by benchmark fetch.
3. Remove duplicates.
4. Enforce schema.
5. Enforce date range from 2021-01-01.
6. Generate data quality report.

It should not require manual NAV/TRI files.

---

# 16. Return Engine

Create:

```text
04_streamlit_app/src/returns.py
```

Inputs:

```text
02_processed_data/nav_daily_clean.csv
02_processed_data/benchmark_daily.csv
```

Outputs:

```text
02_processed_data/returns_daily.csv
02_processed_data/nav_monthly.csv
02_processed_data/returns_monthly.csv
02_processed_data/benchmark_monthly.csv
```

## Daily Fund Returns

```text
Daily Return = NAV_today / NAV_previous_available_observation - 1
```

Rules:

- Calculate within each `fund_label` only.
- Sort by `fund_label`, then `date`.
- Do not calculate across fund boundaries.
- Do not forward-fill NAVs.

## Monthly Fund NAV

```text
Month-end NAV = latest available NAV in that calendar month
```

## Monthly Fund Return

```text
Monthly Return = Month-End NAV_t / Month-End NAV_t-1 - 1
```

## Benchmark Returns

```text
Benchmark Daily Return = tri_value_t / tri_value_{t-1} - 1
```

Same monthly logic applies to benchmark data.

---

# 17. Metrics Module

Create:

```text
04_streamlit_app/src/metrics.py
```

Output:

```text
02_processed_data/metrics_summary.csv
```

Required metrics:

| Metric | Formula | Frequency |
|---|---|---|
| CAGR | `(ending_nav / beginning_nav) ^ (365 / calendar_days) - 1` | Daily NAV |
| Annualized Volatility | `STDEV(daily_return) × SQRT(252)` | Daily |
| Downside Deviation | `STDEV(negative daily returns) × SQRT(252)` | Daily |
| Sharpe | `(CAGR - RF) / annualized_volatility` | Annual |
| Sortino | `(CAGR - RF) / downside_deviation` | Annual |
| Max Drawdown | `wealth / running_peak - 1` | Daily |
| Recovery Period | Longest peak-to-recovery duration | Daily |
| Best Month | `MAX(monthly_return)` | Monthly |
| Worst Month | `MIN(monthly_return)` | Monthly |
| Positive Month Ratio | Positive monthly returns / total months | Monthly |
| Daily VaR 95 | 5th percentile of daily returns | Daily |
| Daily CVaR 95 | Average daily return ≤ Daily VaR 95 | Daily |
| Monthly VaR 95 | 5th percentile of monthly returns | Monthly |
| Monthly CVaR 95 | Average monthly return ≤ Monthly VaR 95 | Monthly |

Non-negotiable:

- Do not label VaR without frequency.
- Do not mix daily and monthly annualization.
- Use `risk_free_rate = 0.06` as default but allow override.

---

# 18. Rolling Metrics Module

Create:

```text
04_streamlit_app/src/rolling_metrics.py
```

Output:

```text
02_processed_data/rolling_metrics.csv
```

## Monthly Rolling Returns

- rolling_3m_return
- rolling_6m_return
- rolling_12m_return
- rolling_24m_return
- rolling_36m_return

Formula:

```text
PRODUCT(1 + monthly_return over N months) - 1
```

Annualized versions:

- rolling_12m_return_ann
- rolling_24m_return_ann
- rolling_36m_return_ann

Formula:

```text
PRODUCT(1 + monthly_return over N months) ^ (12/N) - 1
```

## Daily Rolling Risk

- rolling_63d_vol
- rolling_126d_vol
- rolling_252d_vol

Formula:

```text
STDEV(daily_return over window) × SQRT(252)
```

## Rolling Sharpe

```text
rolling_252d_sharpe = (rolling_252d_return_ann - risk_free_rate) / rolling_252d_vol
```

Rules:

- Keep early-window values as NaN.
- Do not forward-fill rolling metrics.

---

# 19. Benchmark Analytics Module

Create:

```text
04_streamlit_app/src/benchmarks.py
```

Outputs:

```text
02_processed_data/benchmark_metrics.csv
02_processed_data/rolling_benchmark_metrics.csv
```

Calculate fund-specific benchmark analytics:

| Metric | Formula |
|---|---|
| Excess Return | `fund_return - benchmark_return` |
| Beta | `Cov(fund, benchmark) / Var(benchmark)` |
| Tracking Error | `STDEV(excess_return) × annualization_factor` |
| Information Ratio | `annualized_excess_return / tracking_error` |
| Upside Capture | Fund cumulative return when benchmark > 0 / benchmark cumulative return when benchmark > 0 |
| Downside Capture | Fund cumulative return when benchmark < 0 / benchmark cumulative return when benchmark < 0 |
| Rolling 252D Beta | rolling covariance / rolling benchmark variance |
| Rolling 252D Tracking Error | rolling std of excess daily return × SQRT(252) |
| Rolling 252D Information Ratio | rolling annualized excess return / rolling tracking error |

Rules:

- Match each fund to its own primary benchmark.
- Align dates before calculations.
- Do not use one benchmark for all funds.

---

# 20. Stress Testing Module

Create:

```text
04_streamlit_app/src/stress.py
```

Output:

```text
02_processed_data/stress_results.csv
```

## Stress Types

### A. Historical Replay

Use actual historical returns.

Scenarios:

- Worst 1-month portfolio period
- Worst 3-month portfolio period
- Worst 20-trading-day portfolio period
- Worst small-cap fund period
- Worst benchmark drawdown period if benchmark data exists

### B. Deterministic Stress

Create:

```text
01_raw_data/scheme_master/stress_scenarios.csv
```

Scenarios:

```csv
scenario,UTI Nifty 50 Index,ICICI Bluechip,Parag Parikh Flexi Cap,HDFC Balanced Advantage,Nippon India Small Cap,rationale
Broad Equity Correction,-0.15,-0.16,-0.18,-0.08,-0.28,Equity selloff
Small-cap Unwind,-0.08,-0.10,-0.12,-0.05,-0.35,Size/liquidity shock
Correlation Breakdown,-0.20,-0.21,-0.23,-0.10,-0.38,Diversification failure
Balanced Risk-Off,-0.10,-0.11,-0.12,-0.06,-0.20,Moderate correction
```

Label:

> Deterministic stress scenarios are illustrative assumptions, not forecasts.

### C. Interactive Custom Shocks

Function should accept:

- fund-level shocks
- portfolio weights
- base portfolio value

for Streamlit sliders.

---

# 21. Attribution Module

Create:

```text
04_streamlit_app/src/attribution.py
```

Output:

```text
02_processed_data/attribution_results.csv
```

Default portfolio weights:

| Fund | Weight |
|---|---:|
| UTI Nifty 50 Index | 25% |
| ICICI Bluechip | 20% |
| Parag Parikh Flexi Cap | 25% |
| HDFC Balanced Advantage | 15% |
| Nippon India Small Cap | 15% |

Formulas:

```text
Fund Loss Contribution = Fund Weight × Fund Stress Return
Total Portfolio Stress Return = Σ Fund Loss Contribution
Stress Loss Share = Fund Loss Contribution / Total Portfolio Stress Return
Loss Amount INR = Base Portfolio Value × Fund Loss Contribution
Post-Stress Portfolio Value = Base Portfolio Value × (1 + Total Portfolio Stress Return)
```

Key insight:

> Allocation weight is not the same as stress loss share.

---

# 22. Suitability Module

Create:

```text
04_streamlit_app/src/suitability.py
```

Output:

```text
02_processed_data/suitability_results.csv
```

Client profiles:

- Conservative
- Balanced
- Growth
- Aggressive

Use factors:

- max drawdown
- volatility
- Daily CVaR 95
- small-cap exposure
- rolling beta
- downside capture
- stress loss share
- recovery period

Possible roles:

- Core
- Satellite
- Defensive sleeve
- Aggressive satellite
- Watchlist
- Unsuitable for profile

Possible actions:

- Retain
- Cap exposure
- Stagger allocation
- Pair with defensive sleeve
- Review benchmark-relative behaviour
- Avoid for low drawdown tolerance

Language rule:

Use educational suitability diagnostics. Do not make investment recommendations.

---

# 23. Streamlit App Layout

Pages:

1. Executive Risk Review
2. Fund Due Diligence
3. Benchmark Behaviour
4. Rolling Risk & Return
5. Drawdown & Tail Risk
6. Scenario Stress Testing
7. Suitability & Action Board
8. Methodology

## 23.1 Executive Risk Review

Show:

- Portfolio CAGR
- Portfolio volatility
- Max drawdown
- Daily CVaR 95
- Worst stress loss
- Longest recovery period
- Growth of ₹1 crore
- Scenario loss ranking
- Allocation vs stress loss share

Interpretation:

> The objective is not to rank funds by return. The objective is to understand what risk created the return, how painful the return path was, and which sleeve may break first under stress.

## 23.2 Fund Due Diligence

Show:

- fund selector
- date range selector
- NAV / wealth growth
- drawdown
- monthly return bar chart
- rolling 12M return
- metric cards

## 23.3 Benchmark Behaviour

Show:

- fund vs benchmark growth
- rolling excess return
- rolling beta
- rolling tracking error
- rolling information ratio
- upside/downside capture

## 23.4 Rolling Risk & Return

Show:

- rolling 3M/6M/12M returns
- rolling 1Y volatility
- rolling Sharpe
- rolling beta
- rolling IR

## 23.5 Drawdown & Tail Risk

Show:

- drawdown chart
- worst drawdown table
- daily return distribution
- VaR/CVaR visual
- recovery period chart
- worst 10 daily returns
- worst 10 monthly returns

## 23.6 Scenario Stress Testing

Show:

- scenario selector
- portfolio allocation sliders
- shock sliders
- portfolio stress loss %
- loss amount in ₹
- post-stress value
- fund-wise contribution
- stress waterfall
- allocation vs stress loss share

## 23.7 Suitability & Action Board

Show:

- client profile selector
- suitable sleeve
- risk warning
- action recommendation
- finding / interpretation / action table

## 23.8 Methodology

Show:

- data sources
- API/cache methodology
- date range
- fund universe
- benchmark map
- metric definitions
- formula audit
- stress assumptions
- known limitations
- disclaimer

---

# 24. Excel Model of Record

The Excel model should be generated from processed CSVs, not manual data entry.

Create:

```text
03_excel_model/MF_Risk_Diagnostic_Model.xlsx
```

Sheets:

- 00_Model_Control
- 01_Assumptions
- 02_Fund_Master
- 03_Benchmark_Map
- 04_NAV_Daily_Clean
- 05_Data_QA
- 06_Returns_Daily
- 07_NAV_Monthly
- 08_Returns_Monthly
- 09_Rolling_Metrics
- 10_Wealth_Drawdown
- 11_Benchmark_Relative
- 12_Metrics
- 13_Stress_Historical
- 14_Stress_Deterministic
- 15_Stress_Attribution
- 16_Suitability
- 17_Dashboard
- 18_Memo_Inputs

Each sheet must include:

- clear title
- data source
- date range
- last refresh date
- no unexplained hardcoding

---

# 25. Power BI Screenshot Deck

Power BI is not the main public app. Use it for polished screenshots.

Create three pages:

## Page 1 — Executive Risk Review

- KPI cards
- Growth of ₹1 crore
- Scenario loss ranking
- Metrics table

## Page 2 — Fund Deep Dive

- Fund slicer
- Drawdown chart
- Rolling 12M return
- Risk-return scatter
- Benchmark comparison

## Page 3 — Stress & Suitability

- Stress waterfall
- Allocation vs loss share
- Suitability matrix
- Action board

---

# 26. Cursor Operating Rules

Paste into:

```text
.cursor/rules/project_rules.mdc
```

```text
You are working on an institutional-grade portfolio analytics proof-of-work project.

Project:
MF Risk Diagnostic Module

Final public artifact:
Streamlit-first webapp, supported by an Excel model of record, Power BI screenshot deck, GitHub README, Notion methodology, and LinkedIn carousel.

Data approach:
API-first. The user will not manually input NAV or TRI data. Mutual fund NAV data and benchmark/index data must be fetched programmatically and cached locally.

Rules:
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
```

---

# 27. Build Sequence — API-First

## Phase 0 — Lock decisions

Outputs:

- project name locked
- fund universe locked
- scheme codes marked for API metadata verification
- benchmark map locked
- Jan 2021 onward locked
- Streamlit-first public artifact locked
- API-first data pipeline locked

## Phase 1 — Project scaffold

Create folders and placeholder files.

## Phase 2 — API fetch layer

Implement:

```text
api_fetch.py
```

Tasks:

1. Fetch all mutual fund NAVs from MFAPI.
2. Verify scheme metadata.
3. Cache mutual fund data.
4. Fetch benchmark/index data programmatically.
5. Cache benchmark data.
6. Build HYBRID_65_35.
7. Save clean daily NAV and benchmark CSVs.

Pass condition:

```text
nav_daily_clean.csv and benchmark_daily.csv are generated without manual input.
```

## Phase 3 — Data validation

Implement:

```text
data_cleaning.py
```

Generate:

```text
data_quality_report.csv
```

Pass condition:

```text
No fund or required benchmark has FAIL status.
```

## Phase 4 — Returns engine

Generate:

- daily fund returns
- monthly fund NAV
- monthly fund returns
- daily benchmark returns
- monthly benchmark returns

## Phase 5 — Metrics engine

Generate:

- metrics_summary.csv
- rolling_metrics.csv

## Phase 6 — Benchmark analytics

Generate:

- benchmark_metrics.csv
- rolling_benchmark_metrics.csv

## Phase 7 — Stress and attribution

Generate:

- stress_results.csv
- attribution_results.csv

## Phase 8 — Suitability

Generate:

- suitability_results.csv

## Phase 9 — Streamlit app

Build pages one by one.

## Phase 10 — Excel model

Generate Excel model from processed CSVs.

## Phase 11 — Power BI screenshots

Build screenshot deck.

## Phase 12 — GitHub / Notion / LinkedIn

Publish methodology and carousel.

---

# 28. Final Quality Gates

Do not publish until all are true:

```text
[ ] Fund NAV data is fetched programmatically.
[ ] Benchmark/index data is fetched programmatically.
[ ] No manual NAV/TRI input is required.
[ ] API cache exists.
[ ] Streamlit does not fetch live data on every page load.
[ ] Fund scheme metadata is verified.
[ ] Benchmark source quality is labelled.
[ ] Price-index fallback is not mislabelled as TRI.
[ ] HYBRID_65_35 methodology is disclosed.
[ ] Data quality report is generated.
[ ] Daily returns are calculated correctly.
[ ] Monthly returns are calculated correctly.
[ ] Rolling 3M/6M/12M/24M/36M returns exist.
[ ] Rolling volatility exists.
[ ] Rolling Sharpe exists.
[ ] Rolling beta exists.
[ ] Rolling tracking error exists.
[ ] Rolling information ratio exists.
[ ] Max drawdown uses daily data.
[ ] VaR/CVaR frequency is labelled.
[ ] Benchmarks are fund-specific.
[ ] Stress tests include historical replay and deterministic shocks.
[ ] Attribution shows allocation weight vs stress loss share.
[ ] Suitability page exists.
[ ] Methodology page explains API/cache/data limitations.
[ ] Excel model of record is generated from processed data.
[ ] Streamlit app is deployed.
[ ] Power BI screenshots are exported.
[ ] README is recruiter-ready.
[ ] LinkedIn carousel has one insight per slide.
```

---

# 29. Cursor Prompt Pack — API-First Version

## Prompt 1 — Planning Only

```text
Read @00_project_control/master_project_instructions.md carefully.

Treat it as the authoritative API-first project specification.

Do not write application code yet.

Create or update only:
1. 00_project_control/master_project_brief.md
2. 00_project_control/implementation_plan.md
3. 00_project_control/model_governance.md
4. 00_project_control/formula_audit.md
5. 00_project_control/limitations.md
6. 00_project_control/data_dictionary.md

The user will not manually input NAV or TRI data. The project must fetch mutual fund NAV and benchmark/index data programmatically, cache it, validate it, and then run calculations from processed CSVs.

After writing the files, summarize:
- API-first final architecture
- data source hierarchy
- build phases
- key formulas
- benchmark data risks
- first implementation step
```

## Prompt 2 — Scaffold

```text
Create the initial project scaffold only.

Reference @00_project_control/master_project_instructions.md.

Do not implement financial calculations yet.
Do not fetch data yet.
Do not create fake outputs.

Create the full folder structure and placeholder source/page files exactly as specified in the instruction file.

requirements.txt must include:
pandas
numpy
scipy
statsmodels
plotly
streamlit
openpyxl
kaleido
python-dateutil
requests
yfinance
beautifulsoup4
lxml

app.py should open a basic Streamlit app with navigation placeholders only.
```

## Prompt 3 — Config Files

```text
Create the configuration layer only.

Create:
1. 01_raw_data/scheme_master/fund_master.csv
2. 01_raw_data/scheme_master/benchmark_map.csv
3. 01_raw_data/scheme_master/portfolio_weights.csv
4. 01_raw_data/scheme_master/stress_scenarios.csv

Use the exact fund labels, scheme codes, benchmark map, weights, and stress scenarios from @00_project_control/master_project_instructions.md.

Mark all scheme codes as NEEDS_API_METADATA_VERIFICATION initially.

Do not implement calculations yet.
```

## Prompt 4 — API Fetch Core

```text
Implement only 04_streamlit_app/src/api_fetch.py.

Reference @00_project_control/master_project_instructions.md.

The project is API-first. The user will not manually input NAV or TRI files.

Implement:
1. fetch_mutual_fund_nav()
2. fetch_all_mutual_funds()
3. fetch_benchmark_series()
4. build_hybrid_65_35()
5. fetch_all_benchmarks()
6. cache validation helpers
7. source quality labelling
8. schema validation helpers

Do not make network requests on import.
All fetches must be callable explicitly.

Outputs:
- 02_processed_data/nav_daily_clean.csv
- 02_processed_data/benchmark_daily.csv

Do not implement metrics yet.
Do not modify Streamlit pages.
```

## Prompt 5 — Refresh Script

```text
Create 04_streamlit_app/refresh_data.py.

This script must run the full API-first data and analytics pipeline in order:
1. fetch mutual fund NAVs
2. fetch benchmarks
3. build hybrid benchmark
4. validate data
5. calculate returns
6. calculate metrics
7. calculate rolling metrics
8. calculate benchmark analytics
9. calculate stress results
10. calculate attribution
11. calculate suitability
12. export Excel model if implemented

The script should be executable with:
python 04_streamlit_app/refresh_data.py

Do not fetch data automatically inside Streamlit page imports.
```

---

# 30. Final Public Positioning

Use this exact positioning:

> I built an API-first Streamlit MF Risk Diagnostic Module that fetches selected Indian mutual fund NAV and benchmark data programmatically, converts it into return-path analytics, rolling risk-adjusted behaviour, benchmark-relative metrics, drawdown, tail risk, stress attribution, and client suitability diagnostics.

Sharper LinkedIn hook:

> Most mutual fund comparisons ask: “Which fund gave the highest return?”  
> I wanted to ask: “What risk created that return — and which client can actually sit through it?”

---

# 31. Final Warning

Do not let the project become a brittle live-data app.

The correct professional design is:

```text
API fetch → cache → validate → process → app reads processed outputs
```

not:

```text
app page load → live API call → calculation → chart
```

The first design is institutional. The second design is fragile.
