#!/usr/bin/env python3
"""Generate a ready-to-publish Biotech Catalyst & SEC Cash Runway Briefing (Teaser Sample)
directly from BioSniper's capped 9-row public dataset (data/biotech_catalysts_runway.json).

Designed as a high-converting teaser for GitHub Discussions, HuggingFace Dataset Cards, and RSS/Atom readers:
shows 3 PDUFA targets, 3 near-term clinical catalysts, and 3 cash-runway watch tickers while
gating full 600+ biotech coverage, exact quarterly burn rates, and debt schedules on BioSniper.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

BASE_URL = "https://biosniper.co"


def _utm_url(path: str, campaign: str, content: str, extra: dict[str, Any] | None = None) -> str:
    params: dict[str, Any] = {
        "utm_source": "github",
        "utm_medium": "digest",
        "utm_campaign": campaign[:64],
        "utm_content": content[:64],
    }
    if extra:
        params.update(extra)
    sep = "&" if "?" in path else "?"
    return f"{BASE_URL}{path}{sep}{urlencode(params)}"


def _fmt_usd_m(val: float | int | None) -> str:
    if val is None:
        return "—"
    return f"~${val / 1e6:.1f}M"


def _row_title(r: dict[str, Any]) -> str:
    parts = [p for p in (r.get("event_title"), r.get("drug_name"), r.get("indication")) if p]
    return " · ".join(parts) if parts else f"{r.get('catalyst_type', 'Catalyst')} Milestone"


def build_digest_markdown(records: list[dict[str, Any]], generated_date: str | None = None) -> str:
    date_label = generated_date or datetime.now(UTC).strftime("%Y-%m-%d")
    pdufa_rows = [r for r in records if r.get("catalyst_type") == "PDUFA"][:3]
    clinical_rows = [
        r for r in records if r.get("catalyst_type") not in ("PDUFA", "CASH_RUNWAY_WATCH")
    ][:3]
    runway_rows = [r for r in records if r.get("catalyst_type") == "CASH_RUNWAY_WATCH"][:3]

    lines = [
        f"# BioSniper Biotech Catalyst & SEC Cash Runway Briefing ({date_label})",
        "",
        "> **Public Sample Note**: Below is a **9-company teaser sample** (3 PDUFA · 3 Clinical · 3 Runway Watch) from [BioSniper](https://biosniper.co/methodology?utm_source=github&utm_medium=digest&utm_campaign=weekly_briefing&utm_content=methodology).",
        "> **Full 600+ Biotech Coverage, Exact SEC 10-Q/10-K Burn Models & Multi-Agent Analysis**: [biosniper.co](https://biosniper.co?utm_source=github&utm_medium=digest&utm_campaign=weekly_briefing&utm_content=hero)",
        "> **Live Feeds**: [RSS 2.0 (`biosniper.co/feed.xml`)](https://biosniper.co/feed.xml) · [Atom 1.0 (`biosniper.co/atom.xml`)](https://biosniper.co/atom.xml)",
        "",
        "---",
        "",
        "## 1. Selected Upcoming FDA PDUFA Targets (Sample: 3 of Full Calendar)",
        "",
        "| Ticker | Company | Target Date | Catalyst / Indication | SEC Runway & Primary Citations |",
        "|---|---|---|---|---|",
    ]

    for r in pdufa_rows:
        ticker = r["ticker"]
        co_link = _utm_url(f"/company/{ticker}", "pdufa_watch", ticker)
        ev_id = r.get("event_id")
        ev_link = (
            _utm_url(f"/calendar/event/{ev_id}", "pdufa_watch", f"{ticker}_{ev_id}")
            if ev_id
            else co_link
        )
        lines.append(
            f"| [**{ticker}**]({co_link}) | {r['company_name']} | `{r['expected_date']}` "
            f"| {_row_title(r)} | [View FDA Filing & SEC Runway →]({ev_link}) |"
        )

    lines.extend(
        [
            "",
            "*Browse all upcoming PDUFA action dates on the [BioSniper PDUFA Calendar](https://biosniper.co/calendar/pdufa?utm_source=github&utm_medium=digest&utm_campaign=weekly_briefing&utm_content=pdufa_hub).*",
            "",
            "---",
            "",
            "## 2. Selected Near-Term Clinical Catalysts (Sample: 3 of Full Calendar)",
            "",
            "| Ticker | Company | Type | Date | Catalyst / Indication | Trial Endpoints & Profile |",
            "|---|---|---|---|---|---|",
        ]
    )

    for r in clinical_rows:
        ticker = r["ticker"]
        co_link = _utm_url(f"/company/{ticker}", "clinical_catalyst", ticker)
        ev_id = r.get("event_id")
        ev_link = (
            _utm_url(f"/calendar/event/{ev_id}", "clinical_catalyst", f"{ticker}_{ev_id}")
            if ev_id
            else co_link
        )
        lines.append(
            f"| [**{ticker}**]({co_link}) | {r['company_name']} | `{r['catalyst_type']}` "
            f"| `{r['expected_date']}` | [{_row_title(r)}]({ev_link}) "
            f"| [Verify NCT & SEC Data →]({co_link}) |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 3. SEC EDGAR Cash Runway Watch (< 12 Months Sample)",
            "",
            "Selected companies flagging `< 12 months` of estimated cash runway (exact quarterly burn rate, debt schedule, and dilution scenarios available in the interactive model):",
            "",
            "| Ticker | Company | Est. Cash | Runway Band | Interactive 10-Q/10-K Model |",
            "|---|---|---:|---|---|",
        ]
    )

    for r in runway_rows:
        ticker = r["ticker"]
        co_link = _utm_url(f"/company/{ticker}", "runway_watch", ticker)
        cash = _fmt_usd_m(r.get("cash_and_equivalents_usd"))
        runway = (
            f"**~{r['runway_months']:.0f} mos (<12m Watch)**"
            if r.get("runway_months") is not None
            else "**< 12 mos Watch**"
        )
        calc_link = r.get("runway_calculator_url") or _utm_url(
            "/tools/cash-runway", "runway_watch", ticker
        )
        lines.append(
            f"| [**{ticker}**]({co_link}) | {r['company_name']} | {cash} "
            f"| {runway} | [Open Burn & Dilution Model →]({calc_link}) |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "### Full Biotech Coverage & Interactive Tools",
            "- **Interactive SEC Cash Runway & Dilution Calculator**: [biosniper.co/tools/cash-runway](https://biosniper.co/tools/cash-runway?utm_source=github&utm_medium=digest&utm_campaign=weekly_briefing&utm_content=footer_tool)",
            "- **Full Biotech Event Calendar**: [biosniper.co/calendar](https://biosniper.co/calendar?utm_source=github&utm_medium=digest&utm_campaign=weekly_briefing&utm_content=footer_calendar)",
            "- **Sector Cash Runway Report**: [biosniper.co/reports/biotech-cash-runway](https://biosniper.co/reports/biotech-cash-runway?utm_source=github&utm_medium=digest&utm_campaign=weekly_briefing&utm_content=footer_report)",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    kit_dir = Path(__file__).resolve().parent
    json_path = kit_dir / "data" / "biotech_catalysts_runway.json"
    out_path = kit_dir / "data" / "WEEKLY_DIGEST.md"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else payload
    md = build_digest_markdown(records, generated_date=payload.get("generated_date_utc"))
    out_path.write_text(md, encoding="utf-8")
    print(f"Generated {out_path} ({len(records)} teaser records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
