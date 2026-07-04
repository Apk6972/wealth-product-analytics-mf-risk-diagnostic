# MF Risk Diagnostic Module

**Wealth Product Analytics OS — Mutual Fund Risk Diagnostic Module**

> What Risk Created the Return?

An API-first portfolio risk diagnostic system that converts five selected Indian mutual fund sleeves into return-path analytics, benchmark-relative behaviour, rolling risk metrics, stress loss, attribution, and client suitability insights.

This is **not** a "find the best mutual fund" dashboard. It answers:

> What risk created the return, how painful was the return path, and which client profile can actually sit through it?

This project is an educational analytics proof-of-work project. **It is not investment advice.**

---

## Project Status

**Scaffold stage.** Folder structure, placeholder source modules, placeholder Streamlit pages, and placeholder config files exist. No data has been fetched, no calculations have been implemented, and no outputs are real yet.

See `00_project_control/implementation_plan.md` for the full phase-by-phase build sequence and current progress.

---

## Architecture — API-First

```text
API sources / programmatic fetchers
        ↓
Raw API cache layer                 (01_raw_data/api_cache/)
        ↓
Schema validation layer             (data_cleaning.py → data_quality_report.csv)
        ↓
Clean daily NAV + benchmark tables  (nav_daily_clean.csv, benchmark_daily.csv)
        ↓
Daily returns engine → Monthly returns engine → Rolling metrics engine
        ↓
Benchmark-relative analytics → Stress testing + attribution engine → Suitability engine
        ↓
Processed CSV database              (02_processed_data/)
        ↓
Streamlit webapp (reads processed CSVs only — never live-fetches on page load)
        ↓
Excel model of record → Power BI screenshot deck → LinkedIn / GitHub / Notion case study
```

**Non-negotiable runtime rule:** the public Streamlit app must never fetch live data on every page load. Data is fetched, cached, validated, and processed by an explicit refresh step; the app only reads processed CSVs.

Mutual fund NAV history is fetched programmatically using MFAPI for reproducible educational analytics. AMFI remains the official source for Indian mutual fund NAV disclosures. Benchmark/index TRI data is fetched programmatically with a documented source-priority fallback (see `00_project_control/master_project_instructions.md.md` §4 and `00_project_control/limitations.md`).

---

## Fund Universe (Analytics Sleeves, Not Recommendations)

| Sleeve | Fund | Analytical Role |
|---|---|---|
| Passive core equity | UTI Nifty 50 Index Fund — Direct Growth | Clean market beta |
| Active large-cap | ICICI Prudential Bluechip Fund — Direct Growth | Active large-cap exposure |
| Flexi-cap allocator | Parag Parikh Flexi Cap Fund — Direct Growth | Diversified equity allocator |
| Hybrid allocation | HDFC Balanced Advantage Fund — Direct Growth | Lower-volatility allocation sleeve |
| High-risk satellite | Nippon India Small Cap Fund — Direct Growth | Small-cap / aggressive satellite |

Funds are selected as category proxies for analytics demonstration, not as investment recommendations. Data horizon: 1 January 2021 → latest available date.

---

## Repository Structure

```text
00_project_control/     Planning, governance, formula audit, data dictionary, limitations
01_raw_data/             API cache + scheme/benchmark/weight/scenario config
02_processed_data/       Calculation outputs (generated, not committed by hand)
03_excel_model/          Excel model of record (generated from processed CSVs)
04_streamlit_app/        Streamlit source modules, pages, and assets
05_powerbi_dashboard/    Power BI screenshot deck source
06_outputs/              Charts, dashboard screenshots, carousel slides, memo PDFs
07_linkedin/             Publication copy
app.py                   Streamlit navigation entry point
requirements.txt         Python dependencies
```

---

## Setup

Requires Python 3.11 or 3.12.

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Running the app (once implemented beyond scaffold):

```bash
streamlit run app.py
```

Refreshing data (once implemented — not yet available in scaffold stage):

```bash
python 04_streamlit_app/refresh_data.py
```

---

## Control Documents

- `00_project_control/master_project_brief.md` — locked project identity and architecture
- `00_project_control/implementation_plan.md` — phased build sequence and quality gates
- `00_project_control/model_governance.md` — operating rules, cache/labelling/fail-fast governance
- `00_project_control/formula_audit.md` — every metric formula, frequency, and rule
- `00_project_control/limitations.md` — data caveats and scope boundaries
- `00_project_control/data_dictionary.md` — schema for every raw, cached, and processed file

---

## Disclaimer

This project is an educational analytics proof-of-work project. It does not constitute investment advice. Fund selection is illustrative only. Deterministic stress scenarios are illustrative assumptions, not forecasts. Suitability outputs are educational diagnostics, not investment recommendations.
