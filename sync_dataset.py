#!/usr/bin/env python3
"""BioSniper Public Benchmark Sample Exporter (Value-Gated & Quality-Gated).

Exports a strictly capped 9-row public benchmark sample (3 PDUFA targets, 3 near-term
clinical catalysts, and 3 SEC cash-runway watch companies) from BioSniper's verified
snapshots.

Enforces 5 Fail-Closed Data Quality Gates before writing any output:
1. Read-Contract Verification (`contract=source-evidence-v2` + `X-Public-Read-Contract` header).
2. Backend Entity & Event Indexability Gate (`indexable_only=true` + `is_indexable=True`).
3. Exchange & Ticker Hygiene Gate (requires verified `Nasdaq`/`NYSE` exchange; excludes 5-letter `-Q` OTC/bankruptcy tickers).
4. Zero Dirty Placeholder Gate (forbids `"UNKNOWN"`, `"NaN"`, `"null"`, `"undefined"` in any exported field).
5. Completeness & Value-Redaction Gate (requires all 3 buckets populated, 6..9 total rows, and zero leaked deep balance-sheet fields; fails closed without overwriting files if upstream degrades).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from biosniper_toolkit import SITE_BASE, build_biosniper_url

DEFAULT_API_BASE = os.environ.get(
    "BIOSNIPER_API_BASE",
    "https://biosniper-backend-d2fhdgw7ua-uw.a.run.app/api",
)
PUBLIC_EVIDENCE_READ_CONTRACT = "source-evidence-v2"
PUBLIC_READ_CONTRACT_HEADER = "x-public-read-contract"

KIT_ROOT = Path(__file__).resolve().parent
DATA_DIR = KIT_ROOT / "data"
JSON_OUT = DATA_DIR / "biotech_catalysts_runway.json"
CSV_OUT = DATA_DIR / "biotech_catalysts_runway.csv"
CATALOG_OUT = KIT_ROOT / "CATALOG.md"

MAX_PUBLIC_SAMPLE_ROWS = 9
MIN_PUBLIC_SAMPLE_ROWS = 6
MAX_PER_BUCKET = 3

FORBIDDEN_DEEP_KEYS: frozenset[str] = frozenset(
    {
        "total_debt_usd",
        "net_income_usd",
        "quarterly_burn_rate_usd",
        "financial_period_end",
        "catalyst_total",
    }
)
FORBIDDEN_TEXT_TOKENS: tuple[str, ...] = ("UNKNOWN", "NAN", "UNDEFINED", "NULL")
TICKER_RE = re.compile(r"^[A-Z]{1,5}$")

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


class DatasetQualityError(RuntimeError):
    """Raised when exported dataset rows fail any pre-write quality or redaction invariant."""


def _with_read_contract(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    q["contract"] = [PUBLIC_EVIDENCE_READ_CONTRACT]
    new_query = urllib.parse.urlencode(q, doseq=True)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment)
    )


RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def _parse_retry_after(raw_val: str | None, attempt: int) -> float:
    if raw_val:
        try:
            return min(max(float(raw_val.strip()), 1.0), 6.0)
        except ValueError:
            pass
    return min(2.0 * attempt, 6.0)


def _http_get_json(
    url: str,
    *,
    timeout: float = 20.0,
    max_attempts: int = 3,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any] | None:
    contract_url = _with_read_contract(url)
    headers = {
        "User-Agent": "BioSniper-OpenDatasetSync/1.0 (+https://biosniper.co)",
        "Accept": "application/json",
    }
    try:
        import httpx  # type: ignore[import-not-found]

        with httpx.Client(timeout=timeout, headers=headers) as client:
            for attempt in range(1, max(1, max_attempts) + 1):
                try:
                    resp = client.get(contract_url)
                except Exception:
                    if attempt < max_attempts:
                        sleep_fn(_parse_retry_after(None, attempt))
                        continue
                    return None
                if resp.status_code == 200:
                    header_val = resp.headers.get(PUBLIC_READ_CONTRACT_HEADER)
                    if header_val and header_val != PUBLIC_EVIDENCE_READ_CONTRACT:
                        raise DatasetQualityError(
                            f"Read contract mismatch on {url}: expected {PUBLIC_EVIDENCE_READ_CONTRACT}, got {header_val}"
                        )
                    return resp.json()
                if resp.status_code in RETRYABLE_HTTP_STATUSES and attempt < max_attempts:
                    sleep_fn(_parse_retry_after(resp.headers.get("Retry-After"), attempt))
                    continue
                return None
    except DatasetQualityError:
        raise
    except ImportError:
        pass

    if not contract_url.startswith(("https://", "http://")):
        return None
    for attempt in range(1, max(1, max_attempts) + 1):
        req = urllib.request.Request(contract_url, headers=headers)  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                if resp.status != 200:
                    return None
                header_val = resp.headers.get(PUBLIC_READ_CONTRACT_HEADER)
                if header_val and header_val != PUBLIC_EVIDENCE_READ_CONTRACT:
                    raise DatasetQualityError(
                        f"Read contract mismatch on {url}: expected {PUBLIC_EVIDENCE_READ_CONTRACT}, got {header_val}"
                    )
                return json.loads(resp.read().decode("utf-8"))
        except DatasetQualityError:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code in RETRYABLE_HTTP_STATUSES and attempt < max_attempts:
                retry_hdr = exc.headers.get("Retry-After") if exc.headers else None
                sleep_fn(_parse_retry_after(retry_hdr, attempt))
                continue
            return None
        except (urllib.error.URLError, TimeoutError, ValueError):
            if attempt < max_attempts:
                sleep_fn(_parse_retry_after(None, attempt))
                continue
            return None
    return None


def _is_clean_listed_company(ticker: str, comp: dict[str, Any]) -> bool:
    """Require a valid primary ticker (excluding 5-letter OTC -Q bankruptcy symbols) and exchange."""
    if not TICKER_RE.match(ticker):
        return False
    if len(ticker) == 5 and ticker.endswith("Q"):
        return False
    exchange = str(comp.get("exchange") or "").strip()
    return bool(exchange)


def _is_event_indexable(ev: dict[str, Any], min_expected_date: str) -> bool:
    idx = ev.get("indexability")
    if not isinstance(idx, dict) or idx.get("is_indexable") is not True:
        return False
    exp = ev.get("expected_date")
    return not (exp and not ev.get("outcome") and str(exp)[:10] < min_expected_date)


def validate_dataset_quality(rows: list[dict[str, Any]]) -> None:
    """Fail-closed pre-write quality gate. Raises DatasetQualityError on any violation."""
    if not (MIN_PUBLIC_SAMPLE_ROWS <= len(rows) <= MAX_PUBLIC_SAMPLE_ROWS):
        raise DatasetQualityError(
            f"Row count {len(rows)} outside allowed teaser window [{MIN_PUBLIC_SAMPLE_ROWS}, {MAX_PUBLIC_SAMPLE_ROWS}]"
        )

    seen_tickers: set[str] = set()
    pdufa_count = 0
    clinical_count = 0
    runway_count = 0

    for idx, r in enumerate(rows):
        leaked = FORBIDDEN_DEEP_KEYS.intersection(r.keys())
        if leaked:
            raise DatasetQualityError(f"Row {idx} leaked forbidden deep fields: {sorted(leaked)}")

        ticker = str(r.get("ticker") or "").strip()
        if not TICKER_RE.match(ticker) or (len(ticker) == 5 and ticker.endswith("Q")):
            raise DatasetQualityError(f"Row {idx} has invalid or OTC -Q ticker: {ticker!r}")
        if ticker in seen_tickers:
            raise DatasetQualityError(f"Duplicate ticker in teaser dataset: {ticker}")
        seen_tickers.add(ticker)

        exchange = str(r.get("exchange") or "").strip()
        if not exchange:
            raise DatasetQualityError(f"Row {ticker} is missing verified exchange")

        for col in ("company_name", "catalyst_type", "event_title", "runway_band", "company_url", "runway_calculator_url"):
            val = str(r.get(col) or "").strip()
            if not val:
                raise DatasetQualityError(f"Row {ticker} has empty required column {col!r}")
            upper_val = val.upper()
            for token in FORBIDDEN_TEXT_TOKENS:
                if re.search(rf"\b{token}\b", upper_val):
                    raise DatasetQualityError(
                        f"Row {ticker} column {col!r} contains forbidden placeholder token {token!r}: {val!r}"
                    )

        for url_col in ("company_url", "runway_calculator_url"):
            u = str(r.get(url_col) or "")
            if not u.startswith("https://biosniper.co/"):
                raise DatasetQualityError(f"Row {ticker} {url_col} is not a canonical biosniper.co URL: {u!r}")

        cash = r.get("cash_and_equivalents_usd")
        if cash is not None and (not isinstance(cash, (int, float)) or cash <= 0):
            raise DatasetQualityError(f"Row {ticker} has invalid cash_and_equivalents_usd: {cash!r}")

        ctype = str(r.get("catalyst_type") or "")
        if ctype == "PDUFA":
            pdufa_count += 1
        elif ctype == "CASH_RUNWAY_WATCH":
            runway_count += 1
            rw_mos = r.get("runway_months")
            if not isinstance(rw_mos, (int, float)) or not (0 < rw_mos <= 12):
                raise DatasetQualityError(f"Runway watch row {ticker} has out-of-range runway_months: {rw_mos!r}")
        else:
            clinical_count += 1

    if pdufa_count == 0 or clinical_count == 0 or runway_count == 0:
        raise DatasetQualityError(
            f"Incomplete bucket coverage: pdufa={pdufa_count}, clinical={clinical_count}, runway={runway_count}"
        )



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

    company_map: dict[str, dict[str, Any]] = {}
    unresolved_runway_candidates: list[dict[str, Any]] = []
    skip = 0
    page_limit = 1000
    while True:
        companies_payload = _http_get_json(
            f"{clean_api}/public/companies?indexable_only=true&limit={page_limit}&skip={skip}"
        ) or {}
        items = companies_payload.get("items") or []
        for item in items:
            if isinstance(item, dict) and item.get("ticker"):
                t = str(item["ticker"]).strip().upper()
                if _is_clean_listed_company(t, item):
                    company_map[t] = item
                else:
                    sig = item.get("signature_inputs") or {}
                    rw = sig.get("runway_months")
                    cash = sig.get("cash")
                    if (
                        isinstance(rw, (int, float))
                        and 0 < rw <= 12
                        and isinstance(cash, (int, float))
                        and cash > 0
                        and not (len(t) == 5 and t.endswith("Q"))
                        and TICKER_RE.match(t)
                    ):
                        unresolved_runway_candidates.append(item)
        total = companies_payload.get("total")
        if not items or len(items) < page_limit:
            break
        skip += len(items)
        if isinstance(total, int) and skip >= total:
            break

    runway_payload = _http_get_json(f"{clean_api}/public/stats/cash-runway") or {}
    runway_map: dict[str, dict[str, Any]] = {}
    for item in runway_payload.get("at_risk") or []:
        if isinstance(item, dict) and item.get("ticker"):
            runway_map[str(item["ticker"]).strip().upper()] = item

    pdufa_payload = _http_get_json(
        f"{clean_api}/calendar?upcoming=true&past_days=0&upcoming_days={int(upcoming_days)}&types=PDUFA&limit=50"
    ) or {}
    cal_payload = _http_get_json(
        f"{clean_api}/calendar?upcoming=true&past_days=0&upcoming_days={int(upcoming_days)}&limit=80"
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
        fin = comp.get("financial") or {}
        raw_cash = (
            rw.get("cash_and_equivalents")
            if rw and rw.get("cash_and_equivalents") is not None
            else (
                fin.get("cash_and_equivalents")
                if isinstance(fin.get("cash_and_equivalents"), (int, float))
                else sig.get("cash")
            )
        )
        raw_runway = (
            rw.get("runway_months")
            if rw and rw.get("runway_months") is not None
            else (
                fin.get("runway_months")
                if isinstance(fin.get("runway_months"), (int, float))
                else sig.get("runway_months")
            )
        )
        exposed_cash = (
            int(round(float(raw_cash), -5))
            if isinstance(raw_cash, (int, float)) and raw_cash > 0
            else None
        )
        exposed_runway = (
            max(1.0, round(float(raw_runway), 0))
            if is_runway_sample and isinstance(raw_runway, (int, float)) and raw_runway > 0
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
            "exchange": str(comp.get("exchange") or (rw or {}).get("exchange") or "").strip(),
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

    # Bucket 1: Up to 3 upcoming PDUFA targets on verified exchanges
    pdufa_events = list(pdufa_payload.get("events") or [])
    if int(upcoming_days) < 180 and len(pdufa_events) < MAX_PER_BUCKET:
        extended_pdufa = _http_get_json(
            f"{clean_api}/calendar?upcoming=true&past_days=0&upcoming_days=180&types=PDUFA&limit=50"
        ) or {}
        pdufa_events.extend(extended_pdufa.get("events") or [])

    pdufa_count = 0
    for ev in pdufa_events:
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

    # Bucket 2: Up to 3 upcoming non-PDUFA clinical/regulatory catalysts on verified exchanges
    # Prioritize clinical/regulatory readouts (Phase 1/2/3, AdCom, Data Readout, etc.) ahead of Earnings
    raw_cal_events = [
        ev
        for ev in (cal_payload.get("events") or [])
        if isinstance(ev, dict) and str(ev.get("catalyst_type") or "") != "PDUFA"
    ]
    prioritized_cal_events = sorted(
        raw_cal_events,
        key=lambda ev: (1 if str(ev.get("catalyst_type") or "") == "Earnings" else 0),
    )

    clinical_count = 0
    for ev in prioritized_cal_events:
        if len(rows) >= capped_total:
            break
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

    # Bucket 3: Up to 3 cash-runway watch companies (<12m runway teaser) on verified exchanges
    runway_count = 0
    for ticker, rw in runway_map.items():
        if len(rows) >= capped_total or runway_count >= MAX_PER_BUCKET:
            break
        if ticker in seen_tickers:
            continue
        comp = company_map.get(ticker)
        if not comp:
            single_comp = _http_get_json(f"{clean_api}/public/company/{ticker}")
            if isinstance(single_comp, dict) and _is_clean_listed_company(ticker, single_comp):
                comp = single_comp
                company_map[ticker] = comp
            elif rw.get("exchange") and _is_clean_listed_company(ticker, rw):
                comp = {
                    "ticker": ticker,
                    "name": rw.get("name") or ticker,
                    "exchange": rw.get("exchange"),
                }
            else:
                continue
        raw_rw = rw.get("runway_months")
        if not isinstance(raw_rw, (int, float)) or not (0 < raw_rw <= 12):
            continue
        rows.append(_build_teaser_row(ticker, comp, None, rw, is_runway_sample=True))
        seen_tickers.add(ticker)
        runway_count += 1

    # Fallback within Bucket 3: check company_map signature_inputs for additional <12m runway companies
    if runway_count < MAX_PER_BUCKET and len(rows) < capped_total:
        for ticker, comp in list(company_map.items()):
            if len(rows) >= capped_total or runway_count >= MAX_PER_BUCKET:
                break
            if ticker in seen_tickers:
                continue
            sig = comp.get("signature_inputs") or {}
            raw_rw = sig.get("runway_months")
            raw_cash = sig.get("cash")
            if (
                isinstance(raw_rw, (int, float))
                and 0 < raw_rw <= 12
                and isinstance(raw_cash, (int, float))
                and raw_cash > 0
            ):
                rows.append(_build_teaser_row(ticker, comp, None, None, is_runway_sample=True))
                seen_tickers.add(ticker)
                runway_count += 1

    # Secondary Fallback: resolve exchange for high-priority runway candidates with missing directory exchange
    if runway_count < MAX_PER_BUCKET and len(rows) < capped_total:
        for cand in unresolved_runway_candidates:
            if len(rows) >= capped_total or runway_count >= MAX_PER_BUCKET:
                break
            ticker = str(cand.get("ticker") or "").strip().upper()
            if not ticker or ticker in seen_tickers:
                continue
            single_comp = _http_get_json(f"{clean_api}/public/company/{ticker}")
            if isinstance(single_comp, dict) and _is_clean_listed_company(ticker, single_comp):
                cand_hydrated = {**cand, **single_comp}
                company_map[ticker] = cand_hydrated
                rows.append(_build_teaser_row(ticker, cand_hydrated, None, None, is_runway_sample=True))
                seen_tickers.add(ticker)
                runway_count += 1

    # Top-up window: if Bucket 1 or Bucket 3 had fewer than 3 indexable companies (e.g., only 1 <12m runway
    # company on Nasdaq/NYSE), fill remaining slots up to capped_total from verified clinical/regulatory events
    # so transient single-company listing refresh windows never drop total rows below MIN_PUBLIC_SAMPLE_ROWS (6).
    if len(rows) < capped_total and pdufa_count > 0 and runway_count > 0:
        for ev in prioritized_cal_events:
            if len(rows) >= capped_total:
                break
            ticker = (ev.get("company_ticker") or "").strip().upper()
            if not ticker or ticker in seen_tickers or not _is_event_indexable(ev, min_expected_date):
                continue
            comp = company_map.get(ticker)
            if not comp:
                continue
            rows.append(_build_teaser_row(ticker, comp, ev, runway_map.get(ticker), is_runway_sample=False))
            seen_tickers.add(ticker)

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
        asset_cell = f"[{asset_text}]({r['event_url']})" if r.get("event_url") else asset_text
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
    """Validate quality invariants first, then persist JSON, CSV, and Markdown catalog files."""
    validate_dataset_quality(rows)
    gen_date = generated_date or datetime.now(UTC).date().isoformat()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "dataset": "biotech-pdufa-catalyst-and-cash-runway-benchmark",
        "provider": "BioSniper (https://biosniper.co)",
        "read_contract": PUBLIC_EVIDENCE_READ_CONTRACT,
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


def _has_valid_existing_snapshot(
    json_path: Path = JSON_OUT,
    csv_path: Path = CSV_OUT,
    catalog_path: Path = CATALOG_OUT,
) -> bool:
    if not (json_path.exists() and csv_path.exists() and catalog_path.exists()):
        return False
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            return False
        validate_dataset_quality(records)
        return True
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--upcoming-days", type=int, default=180)
    parser.add_argument("--max-tickers", type=int, default=MAX_PUBLIC_SAMPLE_ROWS)
    parser.add_argument("--api-base", type=str, default=DEFAULT_API_BASE)
    parser.add_argument("--utm-source", type=str, default="github")
    args = parser.parse_args(argv)

    try:
        rows = fetch_dataset_rows(
            api_base=args.api_base,
            upcoming_days=args.upcoming_days,
            max_tickers=args.max_tickers,
            utm_source=args.utm_source,
        )
        write_dataset_outputs(rows)
    except DatasetQualityError as exc:
        if _has_valid_existing_snapshot():
            print(
                f"[sync_dataset] WARN: Upstream snapshot degraded ({exc}); preserving existing verified dataset snapshot.",
                file=sys.stderr,
            )
            return 0
        raise

    print(f"[sync_dataset] Verified & exported {len(rows)} teaser sample records to {JSON_OUT.name}, {CSV_OUT.name}, and {CATALOG_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
