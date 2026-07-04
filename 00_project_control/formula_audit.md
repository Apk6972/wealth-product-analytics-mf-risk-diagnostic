# Formula Audit — MF Risk Diagnostic Module

Every formula used in this project is recorded here with: definition, frequency, inputs, and non-negotiable interpretation rules. No metric may be implemented or displayed without a corresponding entry in this file. This is a planning-stage audit; formulas are not yet implemented in code.

---

## 1. Returns Engine

### 1.1 Daily Fund Return

```text
Daily Return_t = NAV_t / NAV_(previous available observation) - 1
```

- Calculated **within each `fund_label` only** — never across fund boundaries.
- Sort by `fund_label`, then `date`, before computing.
- Do **not** forward-fill NAVs before computing returns.

### 1.2 Monthly Fund NAV

```text
Month-End NAV = latest available NAV observed in that calendar month
```

### 1.3 Monthly Fund Return

```text
Monthly Return_t = Month-End NAV_t / Month-End NAV_(t-1) - 1
```

### 1.4 Benchmark Daily Return

```text
Benchmark Daily Return_t = tri_value_t / tri_value_(t-1) - 1
```

Same month-end/monthly-return logic as §1.2–1.3 applies to benchmark series.

---

## 2. Hybrid Benchmark Construction (`HYBRID_65_35`)

Used only for HDFC Balanced Advantage's primary benchmark.

```text
Hybrid Return_t = 0.65 × NIFTY50_TRI_Return_t + 0.35 × (0.06 / 252)
```

Synthetic index level:

```text
HYBRID_65_35_Value_0   = 100
HYBRID_65_35_Value_t   = HYBRID_65_35_Value_(t-1) × (1 + Hybrid Return_t)
```

- `cash_rate` default = 0.06 (annual), applied as a straight daily accrual (`/252`), overridable.
- Label: `source = INTERNAL_SYNTHETIC_BENCHMARK`, `source_quality = DISCLOSED_APPROXIMATION`.
- Disclosure: "HYBRID_65_35 is a disclosed blended proxy, not an official benchmark."

---

## 3. Core Metrics (`metrics_summary.csv`)

| Metric | Formula | Frequency |
|---|---|---|
| CAGR | `(ending_nav / beginning_nav) ^ (365 / calendar_days) - 1` | Daily NAV |
| Annualized Volatility | `STDEV(daily_return) × SQRT(252)` | Daily |
| Downside Deviation | `STDEV(negative daily returns) × SQRT(252)` | Daily |
| Sharpe Ratio | `(CAGR - RF) / annualized_volatility` | Annual |
| Sortino Ratio | `(CAGR - RF) / downside_deviation` | Annual |
| Max Drawdown | `wealth_index / running_peak(wealth_index) - 1`, take minimum | Daily |
| Recovery Period | Longest peak-to-recovery duration (days/months from drawdown trough back to prior peak) | Daily |
| Best Month | `MAX(monthly_return)` | Monthly |
| Worst Month | `MIN(monthly_return)` | Monthly |
| Positive Month Ratio | `count(monthly_return > 0) / total_months` | Monthly |
| Daily VaR 95 | 5th percentile of the daily return distribution | Daily |
| Daily CVaR 95 | Mean of daily returns ≤ Daily VaR 95 | Daily |
| Monthly VaR 95 | 5th percentile of the monthly return distribution | Monthly |
| Monthly CVaR 95 | Mean of monthly returns ≤ Monthly VaR 95 | Monthly |

Non-negotiable rules:

- Never label a VaR/CVaR figure without stating its frequency (daily vs monthly).
- Never mix daily and monthly annualization within the same ratio.
- `risk_free_rate` default = 0.06, overridable — must be disclosed wherever Sharpe/Sortino is shown.

---

## 4. Rolling Metrics (`rolling_metrics.csv`)

### 4.1 Rolling Monthly Returns

```text
rolling_{N}m_return = PRODUCT(1 + monthly_return over trailing N months) - 1
```
for N ∈ {3, 6, 12, 24, 36}.

### 4.2 Rolling Annualized Returns

```text
rolling_{N}m_return_ann = PRODUCT(1 + monthly_return over trailing N months) ^ (12 / N) - 1
```
for N ∈ {12, 24, 36}.

### 4.3 Rolling Daily Volatility

```text
rolling_{W}d_vol = STDEV(daily_return over trailing W days) × SQRT(252)
```
for W ∈ {63, 126, 252}.

### 4.4 Rolling Sharpe

```text
rolling_252d_sharpe = (rolling_252d_return_ann - risk_free_rate) / rolling_252d_vol
```

Rules:

- Early-window values (insufficient trailing history) remain `NaN`.
- Never forward-fill rolling metrics.

---

## 5. Benchmark-Relative Analytics (`benchmark_metrics.csv`, `rolling_benchmark_metrics.csv`)

| Metric | Formula |
|---|---|
| Excess Return | `fund_return - benchmark_return` (same-frequency, same-date pairing) |
| Beta | `Cov(fund_return, benchmark_return) / Var(benchmark_return)` |
| Tracking Error | `STDEV(excess_return) × annualization_factor` (√252 daily, √12 monthly) |
| Information Ratio | `annualized_excess_return / tracking_error` |
| Upside Capture | `Σ fund_return (when benchmark_return > 0) / Σ benchmark_return (when benchmark_return > 0)`, compounded cumulative basis |
| Downside Capture | `Σ fund_return (when benchmark_return < 0) / Σ benchmark_return (when benchmark_return < 0)`, compounded cumulative basis |
| Rolling 252D Beta | Rolling covariance(fund, benchmark) / rolling variance(benchmark) over trailing 252 days |
| Rolling 252D Tracking Error | Rolling STDEV(excess daily return) × SQRT(252) |
| Rolling 252D Information Ratio | Rolling annualized excess return / rolling tracking error |

Rules:

- Each fund is matched to its **own** primary benchmark per `benchmark_map.csv` — never a single shared benchmark across all funds.
- Dates must be aligned (inner join on trading date) before any covariance/variance/ratio calculation.
- `annualized_excess_return` (Information Ratio's numerator, both static and rolling) = `mean(daily excess_return) × 252` — a simple/arithmetic (linear) annualization of the mean, deliberately different from Tracking Error's `STDEV × SQRT(252)` volatility-style annualization. This is the standard convention for excess-return-based ratios and is implemented in `04_streamlit_app/src/benchmarks.py`.
- Rows with fewer than 20 aligned trading days between a fund and its primary benchmark are excluded from the covariance/variance-based figures (`beta`, `tracking_error`, `information_ratio`, capture ratios are set to `NaN` rather than computed from a near-empty sample) in `benchmark_metrics.csv`.

---

## 6. Stress Testing (`stress_results.csv`)

### 6.1 Historical Replay

Uses actual historical returns (no formula transformation beyond compounding over the identified window):

- Worst 1-month portfolio period
- Worst 3-month portfolio period
- Worst 20-trading-day portfolio period
- Worst small-cap fund period
- Worst benchmark drawdown period (if benchmark data exists)

### 6.2 Deterministic Stress

Fixed illustrative shock inputs from `stress_scenarios.csv` (per-fund % shock):

| Scenario | UTI Nifty 50 | ICICI Bluechip | Parag Parikh Flexi Cap | HDFC Balanced Adv. | Nippon Small Cap |
|---|---:|---:|---:|---:|---:|
| Broad Equity Correction | -15% | -16% | -18% | -8% | -28% |
| Small-cap Unwind | -8% | -10% | -12% | -5% | -35% |
| Correlation Breakdown | -20% | -21% | -23% | -10% | -38% |
| Balanced Risk-Off | -10% | -11% | -12% | -6% | -20% |

Disclosure: "Deterministic stress scenarios are illustrative assumptions, not forecasts."

### 6.3 Interactive Custom Shocks

Function contract accepts: fund-level shocks, portfolio weights, base portfolio value (for Streamlit sliders). No fixed formula beyond attribution math in §7.

---

## 7. Attribution (`attribution_results.csv`)

Default portfolio weights: UTI Nifty 50 Index 25%, ICICI Bluechip 20%, Parag Parikh Flexi Cap 25%, HDFC Balanced Advantage 15%, Nippon India Small Cap 15%.

```text
Fund Loss Contribution        = Fund Weight × Fund Stress Return
Total Portfolio Stress Return = Σ Fund Loss Contribution
Stress Loss Share             = Fund Loss Contribution / Total Portfolio Stress Return
Loss Amount (INR)             = Base Portfolio Value × Fund Loss Contribution
Post-Stress Portfolio Value   = Base Portfolio Value × (1 + Total Portfolio Stress Return)
```

Key insight to preserve in all UI/copy: **allocation weight is not the same as stress loss share.**

---

## 8. Suitability (`suitability_results.csv`)

Not a single formula — a rules/scoring layer over already-computed metrics, implemented in `04_streamlit_app/src/suitability.py`. Inputs (factors):

- Max drawdown
- Volatility
- Daily CVaR 95
- Small-cap exposure
- Rolling beta (from `benchmark_metrics.csv`, produced by `04_streamlit_app/src/benchmarks.py`; degrades gracefully to "not available" for any fund/benchmark pairing lacking aligned data, rather than a guessed value)
- Downside capture (same availability caveat as rolling beta)
- Stress loss share (average of `stress_loss_share_minus_weight` across every scenario in `attribution_results.csv` for the fund)
- Recovery period

Outputs: client profile fit (Conservative / Balanced / Growth / Aggressive) × role (Core / Satellite / Defensive sleeve / Aggressive satellite / Watchlist / Unsuitable for profile) × action (Retain / Cap exposure / Stagger allocation / Pair with defensive sleeve / Review benchmark-relative behaviour / Avoid for low drawdown tolerance). One row is produced per (fund, client profile) pair — the same fund can be "Core" for a Growth investor and "Unsuitable for profile" for a Conservative one.

### 8.1 Step 1 — Per-factor risk tiering (LOW / MEDIUM / HIGH)

A factor that cannot be computed (e.g. no benchmark data yet) is excluded from scoring, never defaulted to a guessed value.

| Factor | LOW | MEDIUM | HIGH |
|---|---|---|---|
| Annualized volatility | < 10% | 10%–18% | > 18% |
| Max drawdown (`\|value\|`) | < 15% | 15%–30% | > 30% |
| Daily CVaR 95 (`\|value\|`) | < 2% | 2%–4% | > 4% |
| Recovery period | < 180 days | 180–450 days | > 450 days, or never fully recovered within the observed window (unless max drawdown is negligible, i.e. `\|max drawdown\| < 1%`, in which case LOW) |
| Small-cap exposure (fund_label contains "small cap") | not small-cap | — | small-cap |
| Rolling beta | < 0.85 | 0.85–1.15 | > 1.15 |
| Downside capture (ratio; 1.0 = 100%, same decimal convention as `monthly_return`/`weight` elsewhere in this project) | < 90% | 90%–110% | > 110% |
| Stress loss share vs. weight (avg. `stress_loss_share_minus_weight`) | ≤ +2pp | +2pp to +8pp | > +8pp |

### 8.2 Step 2 — Overall risk tier

Each available factor tier is mapped to a point value (LOW = 1.0, MEDIUM = 2.5, HIGH = 4.0) and averaged across only the *available* factors. The average is bucketed back into:

```text
overall_risk_tier = LOW      if average_points < 1.75
                   = MEDIUM  if 1.75 <= average_points < 3.25
                   = HIGH    if average_points >= 3.25
```

### 8.3 Step 3 — Profile fit via a risk-appetite "gap"

Each client profile has a risk-appetite point value on the same 1.0–4.0 scale: Conservative = 1.0, Balanced = 2.0, Growth = 3.0, Aggressive = 4.0.

```text
gap = profile_risk_appetite_points - fund_overall_risk_points
```

| Gap | Role | Action |
|---|---|---|
| gap ≥ +1.5 | Defensive sleeve | Retain |
| −0.5 ≤ gap < +1.5 | Core | Retain |
| −1.5 ≤ gap < −0.5, profile ∈ {Growth, Aggressive} | Aggressive satellite (if fund risk = HIGH) else Satellite | Stagger allocation |
| −1.5 ≤ gap < −0.5, profile = Balanced | Satellite | Cap exposure |
| −1.5 ≤ gap < −0.5, profile = Conservative | Watchlist | Cap exposure |
| −2.5 ≤ gap < −1.5, profile ∈ {Growth, Aggressive} | Watchlist | Pair with defensive sleeve |
| −2.5 ≤ gap < −1.5, profile ∈ {Conservative, Balanced} | Watchlist | Cap exposure |
| gap < −2.5 | Unsuitable for profile | Avoid for low drawdown tolerance |

**Override:** if the resulting role is Watchlist and benchmark-relative data (beta, downside capture) was unavailable for the fund, the action becomes **Review benchmark-relative behaviour** instead of the table's default action — Watchlist already signals uncertainty, and missing benchmark context is the most direct way to resolve it.

### 8.4 Narrative fields

`risk_warning` lists only the factors at MEDIUM/HIGH tier (HIGH first) with the actual computed value embedded (e.g. "historical maximum drawdown of -24.2%"). `rationale` is a longer sentence combining the profile, overall risk tier, `risk_warning`, portfolio weight, stress-scenario "largest loss contributor" count, and (if applicable) a note that benchmark-relative data was unavailable — always closing with an explicit "not a forecast or an investment recommendation" disclaimer, per the language rule below.

Language rule: every generated sentence describes trailing *historical* data (never a forecast) and is phrased as an educational diagnostic, never a buy/sell/hold instruction.

---

## 9. Annualization Factor Reference

| Context | Factor |
|---|---|
| Daily → annual (volatility, tracking error) | × √252 |
| Monthly → annual (volatility, tracking error) | × √12 |
| Monthly compounding → annual return | `^(12/N)` over N months |
| Daily CAGR | `^(365/calendar_days)` on total NAV growth |

---

## 10. Formula Change Log

| Date | Change | Reason |
|---|---|---|
| Phase 0 (this document) | Initial formula audit compiled from `master_project_instructions.md.md` | Project lock-in, API-first version |
