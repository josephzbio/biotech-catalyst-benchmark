#!/usr/bin/env python3
"""BioSniper Public Benchmark Sample Exporter (Value-Gated Teaser Slice).

Exports a strictly capped 9-row public benchmark sample (3 PDUFA targets, 3 near-term
clinical catalysts, and 3 SEC cash-runway watch companies) from BioSniper's verified
snapshots. Deep balance-sheet schedules, exact quarterly burn rates, and full 600+
company coverage remain gated on https://biosniper.co.

Usage:
    python3 sync_dataset.py --upcoming-days 180 --max-tickers 9
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from biosniper_toolkit import SITE_BASE, build_biosniper_url

DEFAULT_API_BASE = os.environ.get(
    "BIOSNIPER_API_BASE",
    "https://biosniper-backend-d2fhdgw7ua-uw.a.run.app/api",
)
KIT_ROOT = Path(__file__).resolve().parent
DATA_DIR = KIT_ROOT / "data"
JSON_OUT = DATA_DIR / "biotech_catalysts_runway.json"
CSV_OUT = DATA_DIR / "biotech_catalysts_runway.csv"
CATALOG_OUT = KIT_ROOT / "CATALOG.md"

# Hard caps so the public open-source repo acts as a high-intent teaser sample,
# never a full database dump that replaces the BioSniper product.
MAX_PUBLIC_SAMPLE_ROWS = 9
MAX_PER_BUCKET = 3

CSV_COLUMNS: tuple[str, ...] = (
    "ticker",
    "company_name",
    "exchange",
    "event_id",
    "catalyst_type",
    "expected_date",
    "date_kind",
    "drug_name",
    "indication",
    "event_title",
    "cash_and_equivalents_usd",
    "runway_months",
    "runway_band",
    "company_url",
    "event_url",
    "runway_calculator_url",
)


def _http_get_json(url: str, *, timeout: float = 20.0) -> dict[str, Any] | None:
    try:
        import httpx  # type: ignore[import-not-found]

        with httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": "BioSniper-OpenDatasetSync/1.0 (+https://biosniper.co)",
                "Accept": "application/json",
            },
        ) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return None
            return resp.json()
    except ImportError:
        pass
    except Exception:
        return None

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BioSniper-OpenDatasetSync/1.0 (+https://biosniper.co)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def _is_event_indexable(ev: dict[str, Any], min_expected_date: str) -> bool:
    idx = ev.get("indexability")
    if not isinstance(idx, dict) or idx.get("is_indexable") is not True:
        return False
    exp = ev.get("expected_date")
    if exp and not ev.get("outcome") and str(exp)[:10] < min_expected_date:
        return False
    return True


def fetch_dataset_rows(
    *,
    api_base: str = DEFAULT_API_BASE,
    site_base: str = SITE_BASE,
    upcoming_days: int = 180,
    max_tickers: int = MAX_PUBLIC_SAMPLE_ROWS,
    utm_source: str = "github",
) -> list[dict[str, Any]]:
    """Export a strictly capped 9-row teaser slice from BioSniper's verified snapshots."""
    capped_total = max(1, min(int(max_tickers), MAX_PUBLIC_SAMPLE_ROWS))
    clean_api = api_base.rstrip("/")
    min_expected_date = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()

    companies_payload = _http_get_json(
        f"{clean_api}/public/companies?indexable_only=true&limit=1000"
    ) or {}
    company_map: dict[str, dict[str, Any]] = {}
    for item in companies_payload.get("items") or []:
        if isinstance(item, dict) and item.get("ticker"):
            company_map[str(item["ticker"]).strip().upper()] = item

    runway_payload = _http_get_json(f"{clean_api}/public/stats/cash-runway") or {}
    runway_map: dict[str, dict[str, Any]] = {}
    for item in runway_payload.get("at_risk") or []:
        if isinstance(item, dict) and item.get("ticker"):
            runway_map[str(item["ticker"]).strip().upper()] = item

    pdufa_payload = _http_get_json(
        f"{clean_api}/calendar?upcoming=true&past_days=0&upcoming_days={int(upcoming_days)}&types=PDUFA&limit=30"
    ) or {}
    cal_payload = _http_get_json(
        f"{clean_api}/calendar?upcoming=true&past_days=0&upcoming_days={int(upcoming_days)}&limit=60"
    ) or {}

    seen_tickers: set[str] = set()
    rows: list[dict[str, Any]] = []

    def _build_teaser_row(
        ticker: str,
        comp: dict[str, Any],
        ev: dict[str, Any] | None,
        rw: dict[str, Any] | None,
        *,
        is_runway_sample: bool,
    ) -> dict[str, Any]:
        sig = comp.get("signature_inputs") or {}
        raw_cash = (
            rw.get("cash_and_equivalents")
            if rw and rw.get("cash_and_equivalents") is not None
            else sig.get("cash")
        )
        raw_runway = (
            rw.get("runway_months")
            if rw and rw.get("runway_months") is not None
            else sig.get("runway_months")
        )
        # Only expose coarse rounded cash & integer runway on the 3 runway watch teaser rows;
        # withhold detailed burn/debt/runway on catalyst rows so users visit BioSniper.
        exposed_cash = (
            int(round(float(raw_cash), -5))
            if isinstance(raw_cash, (int, float)) and raw_cash > 0
            else None
        )
        exposed_runway = (
            round(float(raw_runway), 0)
            if is_runway_sample and isinstance(raw_runway, (int, float))
            else None
        )
        runway_band = (
            "< 12m (Dilution Watch — Full 10-Q Model on BioSniper)"
            if is_runway_sample
            else "Verify Live SEC Runway & Burn on BioSniper"
        )

        event_id = ev.get("id") if ev else None
        event_url_str = ""
        if isinstance(event_id, int) and event_id > 0:
            event_url_str = build_biosniper_url(
                f"/calendar/event/{event_id}",
                utm_source=utm_source,
                utm_medium="open_source",
                utm_campaign="catalyst_dataset",
                utm_content=ticker,
                site=site_base,
            )

        company_url_str = build_biosniper_url(
            f"/company/{ticker}",
            utm_source=utm_source,
            utm_medium="open_source",
            utm_campaign="catalyst_dataset",
            utm_content="company_row",
            site=site_base,
        )
        runway_calc_url = build_biosniper_url(
            "/tools/cash-runway",
            query={"cash": exposed_cash} if exposed_cash else None,
            utm_source=utm_source,
            utm_medium="open_source",
            utm_campaign="catalyst_dataset",
            utm_content=ticker,
            site=site_base,
        )

        raw_title = str((ev or {}).get("title") or "").strip()
        indication_str = (ev or {}).get("indication") or ", ".join((comp.get("therapeutic_areas") or [])[:2])
        if not raw_title or "UNKNOWN" in raw_title.upper():
            ctype_label = (ev or {}).get("catalyst_type") or "Cash Runway"
            clean_title = (
                f"FDA {ctype_label} Review Target ({indication_str})"
                if ev and indication_str
                else (f"FDA {ctype_label} Review Target" if ev else "SEC Cash Runway < 12m Watch")
            )
        else:
            clean_title = raw_title

        return {
            "ticker": ticker,
            "company_name": comp.get("name") or (rw or {}).get("name") or (ev or {}).get("company_name") or ticker,
            "exchange": comp.get("exchange") or "",
            "event_id": event_id if event_url_str else None,
            "catalyst_type": (ev or {}).get("catalyst_type") or "CASH_RUNWAY_WATCH",
            "expected_date": str((ev or {}).get("expected_date") or sig.get("nearest_catalyst_date") or "")[:10],
            "date_kind": (ev or {}).get("date_kind") or (ev or {}).get("date_confidence") or "",
            "drug_name": (ev or {}).get("drug_name") or "",
            "indication": indication_str,
            "event_title": clean_title,
            "cash_and_equivalents_usd": exposed_cash,
            "runway_months": exposed_runway,
            "runway_band": runway_band,
            "company_url": company_url_str,
            "event_url": event_url_str,
            "runway_calculator_url": runway_calc_url,
        }

    # Bucket 1: Up to 3 upcoming PDUFA targets
    pdufa_count = 0
    for ev in pdufa_payload.get("events") or []:
        if not isinstance(ev, dict):
            continue
        ticker = (ev.get("company_ticker") or "").strip().upper()
        if not ticker or ticker in seen_tickers or not _is_event_indexable(ev, min_expected_date):
            continue
        comp = company_map.get(ticker)
        if not comp:
            continue
        rows.append(_build_teaser_row(ticker, comp, ev, runway_map.get(ticker), is_runway_sample=False))
        seen_tickers.add(ticker)
        pdufa_count += 1
        if pdufa_count >= MAX_PER_BUCKET or len(rows) >= capped_total:
            break

    # Bucket 2: Up to 3 upcoming non-PDUFA clinical/regulatory catalysts
    clinical_count = 0
    for ev in cal_payload.get("events") or []:
        if not isinstance(ev, dict) or len(rows) >= capped_total:
            break
        if str(ev.get("catalyst_type") or "") == "PDUFA":
            continue
        ticker = (ev.get("company_ticker") or "").strip().upper()
        if not ticker or ticker in seen_tickers or not _is_event_indexable(ev, min_expected_date):
            continue
        comp = company_map.get(ticker)
        if not comp:
            continue
        rows.append(_build_teaser_row(ticker, comp, ev, runway_map.get(ticker), is_runway_sample=False))
        seen_tickers.add(ticker)
        clinical_count += 1
        if clinical_count >= MAX_PER_BUCKET or len(rows) >= capped_total:
            break

    # Bucket 3: Up to 3 cash-runway watch companies (<12m runway teaser)
    runway_count = 0
    for ticker, rw in runway_map.items():
        if len(rows) >= capped_total or runway_count >= MAX_PER_BUCKET:
            break
        if ticker in seen_tickers:
            continue
        comp = company_map.get(ticker)
        if not comp:
            continue
        rows.append(_build_teaser_row(ticker, comp, None, rw, is_runway_sample=True))
        seen_tickers.add(ticker)
        runway_count += 1

    return rows


def _fmt_usd_millions(val: Any) -> str:
    if not isinstance(val, (int, float)):
        return "—"
    if abs(val) >= 1_000_000_000:
        return f"~${val / 1_000_000_000:.2f}B"
    if abs(val) >= 1_000_000:
        return f"~${val / 1_000_000:.1f}M"
    return f"~${val:,.0f}"


def render_catalog_markdown(rows: list[dict[str, Any]], generated_date: str) -> str:
    """Render a teaser Markdown catalog with canonical backlinks to BioSniper."""
    lines = [
        "# Upcoming Biotech FDA Catalysts & SEC Cash Runway Benchmark (Public Sample)",
        "",
        f"> **Last Verified Sample Snapshot**: `{generated_date}` (UTC) · **Public Sample Size**: {len(rows)} rows (3 PDUFA · 3 Clinical · 3 Runway Watch)  ",
        "> **Full 600+ Biotech Coverage & Exact SEC 10-Q/10-K Burn Models**: [BioSniper Biotech Intelligence Engine](https://biosniper.co?utm_source=github&utm_medium=open_source&utm_campaign=catalyst_dataset)  ",
        "> **Interactive Hubs**: [Full PDUFA Calendar](https://biosniper.co/calendar/pdufa?utm_source=github&utm_medium=open_source&utm_campaign=catalyst_dataset) · "
        "[Biotech Cash Runway Calculator](https://biosniper.co/tools/cash-runway?utm_source=github&utm_medium=open_source&utm_campaign=catalyst_dataset) · "
        "[Biotech Stock Leaderboards](https://biosniper.co/rankings/upcoming-catalysts?utm_source=github&utm_medium=open_source&utm_campaign=catalyst_dataset)",
        "",
        "## Public Benchmark Teaser Sample",
        "",
        "*Note: Exact quarterly operating cash burn, debt maturity schedules, primary NCT trial endpoints, and multi-agent cross-examination are gated on the live BioSniper platform.*",
        "",
        "| Ticker | Company | Signal Type | Target Date | Asset / Indication | Est. Cash | Runway Status | Full Evidence & Model |",
        "|---|---|---|---|---|---:|---|---|",
    ]
    for r in rows:
        ticker = r["ticker"]
        comp_link = f"[**{ticker}**]({r['company_url']})"
        comp_name = str(r["company_name"]).replace("|", "/")
        cat_type = r["catalyst_type"] or "Catalyst"
        exp_date = r["expected_date"] or "—"
        asset_text = (r.get("drug_name") or r.get("event_title") or r.get("indication") or "—").replace("|", "/")
        if len(asset_text) > 42:
            asset_text = asset_text[:39] + "..."
        if r.get("event_url"):
            asset_cell = f"[{asset_text}]({r['event_url']})"
        else:
            asset_cell = asset_text
        cash_str = _fmt_usd_millions(r.get("cash_and_equivalents_usd"))
        runway_val = r.get("runway_months")
        runway_str = (
            f"~{runway_val:.0f}m (<12m Watch)"
            if isinstance(runway_val, (int, float))
            else r.get("runway_band") or "Verify on BioSniper"
        )
        verify_cell = (
            f"[Company Page]({r['company_url']}) · "
            f"[Runway Sim]({r['runway_calculator_url']})"
        )
        lines.append(
            f"| {comp_link} | {comp_name} | `{cat_type}` | `{exp_date}` | {asset_cell} | "
            f"{cash_str} | {runway_str} | {verify_cell} |"
        )

    lines.extend(
        [
            "",
            "## Unlock Full Coverage on BioSniper",
            "",
            "- **FDA Regulatory Calendars (Full Upcoming Schedule)**:",
            "  - [PDUFA Calendar & Target Action Dates](https://biosniper.co/calendar/pdufa?utm_source=github&utm_medium=open_source&utm_campaign=catalyst_dataset)",
            "  - [FDA Drug Approval Calendar](https://biosniper.co/calendar/approval?utm_source=github&utm_medium=open_source&utm_campaign=catalyst_dataset)",
            "  - [FDA Advisory Committee (AdCom) Schedule](https://biosniper.co/calendar/adcom?utm_source=github&utm_medium=open_source&utm_campaign=catalyst_dataset)",
            "- **Quantitative Tools & Sector Benchmarks**:",
            "  - [Biotech Cash Runway & Dilution Calculator](https://biosniper.co/tools/cash-runway?utm_source=github&utm_medium=open_source&utm_campaign=catalyst_dataset)",
            "  - [FDA Priority vs. Standard Review Timeline Benchmark](https://biosniper.co/tools/fda-timeline?utm_source=github&utm_medium=open_source&utm_campaign=catalyst_dataset)",
            "  - [2026 Biotech Cash Runway Sector Report](https://biosniper.co/reports/biotech-cash-runway?utm_source=github&utm_medium=open_source&utm_campaign=catalyst_dataset)",
            "  - [Upcoming Biotech Catalysts Leaderboard](https://biosniper.co/rankings/upcoming-catalysts?utm_source=github&utm_medium=open_source&utm_campaign=catalyst_dataset)",
            "",
        ]
    )
    return "\n".join(lines)


def write_dataset_outputs(
    rows: list[dict[str, Any]],
    *,
    json_path: Path = JSON_OUT,
    csv_path: Path = CSV_OUT,
    catalog_path: Path = CATALOG_OUT,
    generated_date: str | None = None,
) -> None:
    """Persist JSON, CSV, and Markdown catalog files."""
    gen_date = generated_date or datetime.now(UTC).date().isoformat()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "dataset": "biotech-pdufa-catalyst-and-cash-runway-benchmark",
        "provider": "BioSniper (https://biosniper.co)",
        "license": "MIT",
        "coverage_note": (
            "Public 9-row benchmark sample (3 PDUFA, 3 clinical catalysts, 3 cash-runway watch). "
            "Full 600+ biotech coverage, exact quarterly burn rates, debt schedules, and "
            "multi-agent research are available at https://biosniper.co."
        ),
        "generated_date_utc": gen_date,
        "record_count": len(rows),
        "records": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for r in rows:
            writer.writerow({col: r.get(col, "") for col in CSV_COLUMNS})

    catalog_path.write_text(render_catalog_markdown(rows, gen_date), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--upcoming-days", type=int, default=180)
    parser.add_argument("--max-tickers", type=int, default=MAX_PUBLIC_SAMPLE_ROWS)
    parser.add_argument("--api-base", type=str, default=DEFAULT_API_BASE)
    parser.add_argument("--utm-source", type=str, default="github")
    args = parser.parse_args(argv)

    rows = fetch_dataset_rows(
        api_base=args.api_base,
        upcoming_days=args.upcoming_days,
        max_tickers=args.max_tickers,
        utm_source=args.utm_source,
    )
    write_dataset_outputs(rows)
    print(f"[sync_dataset] Exported {len(rows)} teaser sample records to {JSON_OUT.name}, {CSV_OUT.name}, and {CATALOG_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
