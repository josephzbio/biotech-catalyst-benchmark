---
license: mit
language:
  - en
tags:
  - biotech
  - pharma
  - fda
  - pdufa
  - clinical-trials
  - sec-filings
  - cash-runway
  - rnpv
  - quantitative-finance
pretty_name: Biotech FDA PDUFA Catalysts & SEC Cash Runway Benchmark
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/biotech_catalysts_runway.csv
---

# BioSniper Open Biotech Toolkit & Catalyst Benchmark Dataset

**Zero-dependency Python toolkit and daily-updated benchmark dataset** for quantitative biotech investment research, clinical trial endpoint verification, SEC Form 10-Q/10-K cash-runway modeling, and risk-adjusted NPV (rNPV) valuation.

- **Live Platform & Evidence Engine**: [BioSniper (`biosniper.co`)](https://biosniper.co?utm_source=github&utm_medium=open_source&utm_campaign=readme_hero)
- **Interactive PDUFA & FDA Calendar**: [PDUFA Target Action Dates](https://biosniper.co/calendar/pdufa?utm_source=github&utm_medium=open_source&utm_campaign=readme_hero)
- **Free SEC Cash Runway Calculator**: [Biotech Cash Runway & Dilution Tool](https://biosniper.co/tools/cash-runway?utm_source=github&utm_medium=open_source&utm_campaign=readme_hero)
- **Launch in Google Colab**: [Open `biotech_rnpv_and_runway_quickstart.ipynb` in Colab](https://colab.research.google.com/github/josephzbio/biotech-catalyst-benchmark/blob/main/notebooks/biotech_rnpv_and_runway_quickstart.ipynb)
- **Live 9-Row Sample Watchlist**: See [`CATALOG.md`](./CATALOG.md), [`data/WEEKLY_DIGEST.md`](./data/WEEKLY_DIGEST.md), and [`data/biotech_catalysts_runway.csv`](./data/biotech_catalysts_runway.csv)

---

## What's Inside

1. **`biosniper_toolkit.py`** — Single-file, zero-dependency Python 3.10+ module & CLI powered by BioSniper's verified dataset:
   - **SEC Form 10-Q/10-K Cash Runway & Catalyst Buffer Calculator** (`calculate_cash_runway`): Computes monthly operating burn, runway months, binary-catalyst buffer, and pre-filled interactive simulation links.
   - **Biotech rNPV Valuation Engine** (`calculate_rnpv`): Risk-adjusted Net Present Value model with therapeutic-area clinical phase transition probabilities (Oncology, Rare Disease, Neurology, All Indications) and a 3×3 WACC × PoS sensitivity matrix.
   - **BioSniper Verified Dataset Loader & Filter** (`load_biosniper_dataset`): Queries BioSniper's cross-verified PDUFA catalysts, clinical readouts, and `< 12m` SEC cash-runway watchlists directly into Python dicts or Pandas DataFrames.
2. **Daily Benchmark Dataset (`data/biotech_catalysts_runway.csv` & `.json`)**:
   - Upcoming FDA PDUFA target action dates, Advisory Committee (AdCom) meetings, and Phase 2/3 clinical readouts paired with verified SEC balance-sheet cash, quarterly burn rate, and cash runway months.
   - Automatically synced via [`sync_dataset.py`](./sync_dataset.py) and [`CATALOG.md`](./CATALOG.md).
3. **Interactive Jupyter / Google Colab Notebook**:
   - [`notebooks/biotech_rnpv_and_runway_quickstart.ipynb`](./notebooks/biotech_rnpv_and_runway_quickstart.ipynb) — End-to-end walkthrough for screening biotech binary events against SEC cash runway and modeling rNPV.

---

## 30-Second Quickstart

### 1. Python API

```python
from biosniper_toolkit import calculate_cash_runway, calculate_rnpv, load_biosniper_dataset

# 1) Audit SEC 10-Q Cash Runway vs. Next Binary Catalyst
runway = calculate_cash_runway(
    cash_usd=185_000_000,
    quarterly_burn_usd=24_000_000,
    next_catalyst_months=8.0,
    ticker="RCKT",
)
print(f"Runway: {runway.runway_months} months | Buffer: {runway.catalyst_buffer_months} months")
print(f"Interactive Simulator: {runway.interactive_calculator_url}")

# 2) Compute Risk-Adjusted NPV (rNPV) with 3x3 WACC/PoS Sensitivity Matrix
valuation = calculate_rnpv(
    peak_sales_millions=1200.0,
    phase="Phase 3",
    therapeutic_area="rare_disease",
    remaining_rd_cost_millions=65.0,
    net_cash_millions=185.0,
    ticker="RCKT",
)
print(f"Base rNPV: ${valuation.rnpv_millions}M | Enterprise rNPV: ${valuation.enterprise_rnpv_millions}M")

# 3) Query BioSniper's Verified PDUFA & Cash-Runway Dataset
pdufa_rows = load_biosniper_dataset(catalyst_type="PDUFA")
for row in pdufa_rows[:5]:
    print(row["ticker"], row["expected_date"], "->", row["company_url"])
```

### 2. Command-Line Interface (CLI)

```bash
# Calculate cash runway & generate pre-filled interactive link
python3 biosniper_toolkit.py runway --cash 185000000 --burn 24000000 --catalyst-months 8 --ticker RCKT

# Run Phase 3 rNPV valuation with sensitivity matrix
python3 biosniper_toolkit.py rnpv --peak-sales 1200 --phase "Phase 3" --area rare_disease --rd-cost 65 --net-cash 185 --ticker RCKT

# Query BioSniper's verified PDUFA & sub-12m cash runway dataset
python3 biosniper_toolkit.py dataset --type PDUFA
python3 biosniper_toolkit.py dataset --max-runway 12

# Refresh daily 9-row public benchmark sample from BioSniper snapshots
python3 sync_dataset.py --upcoming-days 180 --max-tickers 9
```

---

## Public Sample Schema (`data/biotech_catalysts_runway.csv` — 9-Row Teaser Slice)

> **Coverage Note**: This open-source repository ships a **9-row benchmark sample** (3 PDUFA targets, 3 clinical/regulatory catalysts, and 3 `< 12m` cash-runway watch companies). Full 600+ biotech company coverage, exact quarterly operating cash burn, debt schedules, and multi-agent cross-examination are available on [BioSniper (`biosniper.co`)](https://biosniper.co?utm_source=github&utm_medium=open_source&utm_campaign=readme_schema).

| Column | Type | Description |
|---|---|---|
| `ticker` | `string` | Primary exchange ticker symbol (e.g., `BTAI`, `DYN`, `PRAX`) |
| `company_name` | `string` | Legal or display issuer name |
| `exchange` | `string` | Verified listing exchange (`NASDAQ`, `NYSE`, `NYSE American`) |
| `event_id` | `int` | Canonical BioSniper catalyst event identifier |
| `catalyst_type` | `string` | Catalyst classification (`PDUFA`, `Earnings`, `CASH_RUNWAY_WATCH`, etc.) |
| `expected_date` | `string` | Target action date or expected readout date (`YYYY-MM-DD`) |
| `date_kind` | `string` | Date precision (`review_target`, `exact`, `quarter`, etc.) |
| `drug_name` | `string` | Lead drug or biologic candidate name (when publicly unlocked) |
| `indication` | `string` | Target disease indication |
| `event_title` | `string` | Primary-source catalyst summary |
| `cash_and_equivalents_usd` | `int` | Rounded SEC Form 10-Q/10-K cash & equivalents estimate (USD) |
| `runway_months` | `float` | Rounded cash runway estimate in months (populated on `< 12m` watch rows) |
| `runway_band` | `string` | Runway status tier & link prompt to full SEC 10-Q/10-K model on BioSniper |
| `trial_count` | `int` | Count of registered clinical trials tracked |
| `ai_thesis_headline` | `string` | Neutral, citation-backed AI research synthesis headline |
| `company_url` | `string` | Direct URL to full company pipeline, SEC filings & 13F holdings on BioSniper |
| `event_url` | `string` | Direct URL to the catalyst event evidence page |
| `runway_calculator_url` | `string` | Pre-filled interactive SEC cash runway calculator URL |

---

## Primary-Source Reference Hubs & Methodology Guides

All dataset records and calculators cross-reference primary regulatory and financial disclosures (SEC EDGAR Form 10-Q/10-K/8-K, FDA Drugs@FDA, and ClinicalTrials.gov):

- **Live Regulatory Calendars & Leaderboards**:
  - [PDUFA Calendar — Upcoming FDA Target Action Dates](https://biosniper.co/calendar/pdufa?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
  - [FDA Approval Calendar — NDA & BLA Decisions](https://biosniper.co/calendar/approval?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
  - [FDA Advisory Committee (AdCom) Meeting Schedule](https://biosniper.co/calendar/adcom?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
  - [Biotech Stocks & Screener Leaderboards](https://biosniper.co/rankings?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
  - [Upcoming Biotech Catalysts Ranking](https://biosniper.co/rankings/upcoming-catalysts?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
  - [Biotech Cash Runway Sector Report](https://biosniper.co/reports/biotech-cash-runway?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
- **Interactive Tools**:
  - [Biotech Cash Runway & Dilution Calculator](https://biosniper.co/tools/cash-runway?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
  - [FDA Priority vs. Standard Review Mix by Year](https://biosniper.co/tools/fda-timeline?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
- **Analyst Verification Guides**:
  - [Biotech Cash Runway Analysis from Form 10-Q/10-K](https://biosniper.co/blog/biotech-cash-runway-analysis?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
  - [Biotech Valuation: Risk-Adjusted NPV (rNPV) Explained](https://biosniper.co/blog/biotech-valuation-rnpv-explained?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
  - [Reading ClinicalTrials.gov Like an Analyst](https://biosniper.co/blog/reading-clinicaltrials-gov-like-an-analyst?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
  - [FDA Priority Review vs. Standard Review](https://biosniper.co/blog/fda-priority-review-vs-standard-review?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)
  - [Open-Label vs. Double-Blind Clinical Trials](https://biosniper.co/blog/open-label-vs-double-blind-trials?utm_source=github&utm_medium=open_source&utm_campaign=readme_links)

---

## License

Released under the [MIT License](https://opensource.org/licenses/MIT). Data snapshots are derived from public SEC EDGAR, FDA, and ClinicalTrials.gov disclosures via [BioSniper](https://biosniper.co).
