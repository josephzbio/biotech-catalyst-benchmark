#!/usr/bin/env python3
"""Generate a Value-Gated Citation & Q&A Pack (TOP 3 Cold-Start Channel)
from BioSniper's capped 9-row teaser dataset.

Produces ``data/CITATIONS_AND_QA_PACK.md`` containing:
1. Ready-to-paste MediaWiki `<ref>{{cite web ...}}</ref>` snippets for the 3 sample PDUFA
   drug/company Wikipedia pages (referencing primary FDA/SEC timeline pages without leaking
   deep financial/agent data).
2. Quantitative Finance / Bioinformatics Q&A reference answers on rNPV and SEC Form 10-Q
   cash-runway methodology, pointing to the free interactive calculator on biosniper.co.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_URL = "https://biosniper.co"


def build_citations_pack_markdown(
    records: list[dict[str, Any]],
    generated_date: str | None = None,
) -> str:
    date_label = generated_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pdufa_rows = [r for r in records if r.get("catalyst_type") == "PDUFA"][:3]

    lines = [
        f"# BioSniper External Citation & Technical Q&A Pack ({date_label})",
        "",
        "> **Data Exposure Guardrail**: Contains only **3 public PDUFA citation snippets** and **methodology formulas**. Full 600+ company coverage, quarterly burn schedules, and multi-agent reports remain strictly on `biosniper.co`.",
        "",
        "---",
        "",
        "## 1. Wikipedia / MediaWiki Regulatory Timeline Citations (`{{cite web}}`)",
        "",
        "Use these neutral, verifiable `<ref>` citations when updating regulatory history sections for tracked PDUFA candidates:",
        "",
    ]

    for r in pdufa_rows:
        ticker = r["ticker"]
        company = r["company_name"]
        exp_date = r.get("expected_date") or "TBD"
        event_id = r.get("event_id")
        target_url = (
            f"{BASE_URL}/calendar/event/{event_id}"
            if event_id
            else f"{BASE_URL}/company/{ticker}"
        )
        lines.extend(
            [
                f"### {company} (`{ticker}`) — Target Action Date: `{exp_date}`",
                "```wiki",
                f"<ref>{{{{cite web |title={company} ({ticker}) FDA PDUFA Review Timeline & Regulatory Disclosures "
                f"|url={target_url} |website=BioSniper Biotech Regulatory Index "
                f"|access-date={date_label}}}}}</ref>",
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## 2. Quantitative Finance / Biostars Methodology Answers (Zero-Promo Technical Templates)",
            "",
            "### Template A: Calculating Biotech Cash Runway & Dilution Buffer from SEC Form 10-Q",
            "",
            "```markdown",
            "For pre-revenue clinical-stage biotech companies, standard GAAP Net Income overstates or distorts near-term liquidity risk because of non-cash stock-based compensation (SBC) and milestone amortization.",
            "",
            "A reproducible 3-step formula from SEC Form 10-Q/10-K:",
            "1. **Liquid Cash Pool**: `Cash & Cash Equivalents + Short-Term Marketable Securities` (exclude restricted cash).",
            "2. **Normalized Monthly Operating Burn**: `abs(Operating Cash Flow over trailing period) / months_in_period`.",
            "3. **Catalyst Buffer (Months)**: `Runway Months - Months to Next Pivotal Readout / PDUFA`.",
            "",
            "Empirically, clinical-stage issuers rarely wait until month 0; secondary offerings or ATM drawdowns cluster when `Runway < 12 months` or `Catalyst Buffer < 6 months`.",
            "",
            "- Reproducible Python implementation & 9-company benchmark sample: see `biosniper_toolkit.py`",
            "- Interactive SEC 10-Q/10-K Cash Runway & Dilution Calculator: https://biosniper.co/tools/cash-runway",
            "- Sector-wide SEC Cash Runway Distribution Report: https://biosniper.co/reports/biotech-cash-runway",
            "```",
            "",
            "### Template B: Phase-Transition Probability of Success (PoS) in Biotech rNPV Models",
            "",
            "```markdown",
            "When discounting clinical-stage drug cash flows (rNPV), applying a flat 10-12% WACC without cumulative phase-transition probabilities systematically overvalues Phase 1/2 assets.",
            "",
            "Standard two-stage adjustment:",
            "1. Multiply projected post-approval cash flows by the therapeutic-area cumulative LOA (e.g., Phase 2 -> Approval ~15-22% in Oncology vs. ~32-40% in Rare Disease).",
            "2. Weight remaining R&D outflows by the conditional probability of entering each subsequent phase.",
            "",
            "- Reference rNPV methodology & WACC sensitivity guide: https://biosniper.co/blog/biotech-valuation-rnpv-explained",
            "- FDA Priority vs. Standard Review Timeline Benchmark: https://biosniper.co/tools/fda-timeline",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    kit_dir = Path(__file__).resolve().parent
    json_path = kit_dir / "data" / "biotech_catalysts_runway.json"
    out_path = kit_dir / "data" / "CITATIONS_AND_QA_PACK.md"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else payload
    md = build_citations_pack_markdown(records, generated_date=payload.get("generated_date_utc"))
    out_path.write_text(md, encoding="utf-8")
    print(f"Generated {out_path} ({len(records[:3])} PDUFA citation snippets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
