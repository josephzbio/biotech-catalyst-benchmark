# BioSniper External Citation & Technical Q&A Pack (2026-11-01)

> **Data Exposure Guardrail**: Contains only **3 public PDUFA citation snippets** and **methodology formulas**. Full 600+ company coverage, quarterly burn schedules, and multi-agent reports remain strictly on `biosniper.co`.

---

## 1. Wikipedia / MediaWiki Regulatory Timeline Citations (`{{cite web}}`)

Use these neutral, verifiable `<ref>` citations when updating regulatory history sections for tracked PDUFA candidates:

### BioXcel Therapeutics, Inc. (`BTAI`) — Target Action Date: `2026-11-14`
```wiki
<ref>{{cite web |title=BioXcel Therapeutics, Inc. (BTAI) FDA PDUFA Review Timeline & Regulatory Disclosures |url=https://biosniper.co/calendar/event/971191 |website=BioSniper Biotech Regulatory Index |access-date=2026-11-01}}</ref>
```

### Dyne Therapeutics, Inc. (`DYN`) — Target Action Date: `2027-01-21`
```wiki
<ref>{{cite web |title=Dyne Therapeutics, Inc. (DYN) FDA PDUFA Review Timeline & Regulatory Disclosures |url=https://biosniper.co/calendar/event/2771594 |website=BioSniper Biotech Regulatory Index |access-date=2026-11-01}}</ref>
```

### Praxis Precision Medicines, Inc. (`PRAX`) — Target Action Date: `2027-01-29`
```wiki
<ref>{{cite web |title=Praxis Precision Medicines, Inc. (PRAX) FDA PDUFA Review Timeline & Regulatory Disclosures |url=https://biosniper.co/calendar/event/972703 |website=BioSniper Biotech Regulatory Index |access-date=2026-11-01}}</ref>
```

---

## 2. Quantitative Finance / Biostars Methodology Answers (Zero-Promo Technical Templates)

### Template A: Calculating Biotech Cash Runway & Dilution Buffer from SEC Form 10-Q

```markdown
For pre-revenue clinical-stage biotech companies, standard GAAP Net Income overstates or distorts near-term liquidity risk because of non-cash stock-based compensation (SBC) and milestone amortization.

A reproducible 3-step formula from SEC Form 10-Q/10-K:
1. **Liquid Cash Pool**: `Cash & Cash Equivalents + Short-Term Marketable Securities` (exclude restricted cash).
2. **Normalized Monthly Operating Burn**: `abs(Operating Cash Flow over trailing period) / months_in_period`.
3. **Catalyst Buffer (Months)**: `Runway Months - Months to Next Pivotal Readout / PDUFA`.

Empirically, clinical-stage issuers rarely wait until month 0; secondary offerings or ATM drawdowns cluster when `Runway < 12 months` or `Catalyst Buffer < 6 months`.

- Reproducible Python implementation & 9-company benchmark sample: see `biosniper_toolkit.py`
- Interactive SEC 10-Q/10-K Cash Runway & Dilution Calculator: https://biosniper.co/tools/cash-runway
- Sector-wide SEC Cash Runway Distribution Report: https://biosniper.co/reports/biotech-cash-runway
```

### Template B: Phase-Transition Probability of Success (PoS) in Biotech rNPV Models

```markdown
When discounting clinical-stage drug cash flows (rNPV), applying a flat 10-12% WACC without cumulative phase-transition probabilities systematically overvalues Phase 1/2 assets.

Standard two-stage adjustment:
1. Multiply projected post-approval cash flows by the therapeutic-area cumulative LOA (e.g., Phase 2 -> Approval ~15-22% in Oncology vs. ~32-40% in Rare Disease).
2. Weight remaining R&D outflows by the conditional probability of entering each subsequent phase.

- Reference rNPV methodology & WACC sensitivity guide: https://biosniper.co/blog/biotech-valuation-rnpv-explained
- FDA Priority vs. Standard Review Timeline Benchmark: https://biosniper.co/tools/fda-timeline
```
