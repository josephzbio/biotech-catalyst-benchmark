#!/usr/bin/env python3
"""Unit tests for BioSniper Open Biotech Toolkit & Dataset Exporter."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from biosniper_toolkit import (
    build_biosniper_url,
    calculate_cash_runway,
    calculate_rnpv,
    format_biosniper_company_snapshot,
    load_biosniper_dataset,
)
from generate_citations_pack import build_citations_pack_markdown
from generate_digest import build_digest_markdown
from publish_to_huggingface import UPLOAD_FILES, resolve_hf_token
from sync_dataset import (
    CSV_COLUMNS,
    MAX_PUBLIC_SAMPLE_ROWS,
    DatasetQualityError,
    _parse_retry_after,
    fetch_dataset_rows,
    render_catalog_markdown,
    validate_dataset_quality,
)

ALLOWED_UTM_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_content"}


class TestBioSniperToolkit(unittest.TestCase):
    def test_build_biosniper_url_uses_only_bounded_utm_keys(self) -> None:
        url = build_biosniper_url(
            "/tools/cash-runway",
            query={"cash": 185000000, "burn": 24000000},
            utm_source="github",
            utm_medium="open_source",
            utm_campaign="runway_toolkit",
            utm_content="RCKT",
        )
        parsed = urlsplit(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "biosniper.co")
        self.assertEqual(parsed.path, "/tools/cash-runway")
        qs = parse_qs(parsed.query)
        utm_keys = {k for k in qs if k.startswith("utm_")}
        self.assertTrue(utm_keys.issubset(ALLOWED_UTM_KEYS))
        self.assertEqual(qs["cash"], ["185000000"])
        self.assertEqual(qs["burn"], ["24000000"])

    def test_calculate_cash_runway_matches_10q_formula(self) -> None:
        res = calculate_cash_runway(
            cash_usd=180_000_000,
            quarterly_burn_usd=30_000_000,
            next_catalyst_months=9.0,
            ticker="RCKT",
        )
        self.assertEqual(res.monthly_burn_usd, 10_000_000.0)
        self.assertEqual(res.runway_months, 18.0)
        self.assertEqual(res.catalyst_buffer_months, 9.0)
        self.assertFalse(res.has_dilution_warning)
        self.assertIn("cash=180000000", res.interactive_calculator_url)
        self.assertIn("burn=30000000", res.interactive_calculator_url)
        self.assertIn("/company/RCKT", res.company_evidence_url or "")

    def test_calculate_cash_runway_flags_sub_12m_warning(self) -> None:
        res = calculate_cash_runway(cash_usd=20_000_000, quarterly_burn_usd=9_000_000)
        self.assertEqual(res.runway_months, 6.7)
        self.assertTrue(res.has_dilution_warning)

    def test_calculate_rnpv_returns_sensitivity_grid(self) -> None:
        res = calculate_rnpv(
            peak_sales_millions=1000.0,
            phase="Phase 3",
            therapeutic_area="rare_disease",
            discount_rate=0.12,
            remaining_rd_cost_millions=50.0,
            net_cash_millions=100.0,
            ticker="BMRN",
        )
        self.assertAlmostEqual(res.pos_probability, 0.657, places=3)
        self.assertGreater(res.unadjusted_npv_millions, res.rnpv_millions)
        self.assertAlmostEqual(
            res.enterprise_rnpv_millions,
            round(res.rnpv_millions + 100.0, 2),
            places=2,
        )
        self.assertEqual(len(res.sensitivity_grid_millions), 3)
        self.assertIn("WACC_12pct", res.sensitivity_grid_millions)
        self.assertIn("/company/BMRN", res.company_evidence_url or "")

    def test_load_biosniper_dataset_filters_by_type_and_runway(self) -> None:
        sample = {
            "records": [
                {"ticker": "BTAI", "catalyst_type": "PDUFA", "runway_months": None},
                {"ticker": "QURE", "catalyst_type": "Cash_Runway_Watch", "runway_months": 11.0},
                {"ticker": "CYDY", "catalyst_type": "Cash_Runway_Watch", "runway_months": 6.4},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "dataset.json"
            p.write_text(json.dumps(sample), encoding="utf-8")
            pdufa = load_biosniper_dataset(dataset_path=p, catalyst_type="PDUFA")
            self.assertEqual([r["ticker"] for r in pdufa], ["BTAI"])
            sub10 = load_biosniper_dataset(dataset_path=p, max_runway_months=10.0)
            self.assertEqual([r["ticker"] for r in sub10], ["CYDY"])

    def test_format_biosniper_company_snapshot_builds_canonical_links(self) -> None:
        raw = {
            "ticker": "RCKT",
            "name": "Rocket Pharmaceuticals, Inc.",
            "exchange": "Nasdaq",
            "development_stage": "Phase 3",
            "therapeutic_areas": ["Rare Disease"],
            "pipeline_total": 6,
            "trial_count": 14,
            "catalyst_total": 2,
            "pipeline_summary": [
                {"drug_name": "Kresladi", "drug_slug": "kresladi", "phase": "BLA", "indication": "LAD-I"}
            ],
            "financial": {"cash_and_equivalents": 185_000_000, "quarterly_burn_rate": 24_000_000, "runway_months": 23.1},
            "ai_synthesis": {"headline": "Gene therapy pipeline with near-term FDA review."},
        }
        snap = format_biosniper_company_snapshot(raw)
        self.assertEqual(snap["ticker"], "RCKT")
        self.assertIn("/company/RCKT", snap["company_evidence_url"])
        self.assertIn("/drug/kresladi", snap["lead_candidates"][0]["drug_url"])
        self.assertIn("cash=185000000", snap["runway_calculator_url"])

    def test_render_catalog_markdown_includes_entity_and_tool_links(self) -> None:
        rows = [
            {
                "ticker": "RCKT",
                "company_name": "Rocket Pharmaceuticals, Inc.",
                "exchange": "NASDAQ",
                "event_id": 101,
                "catalyst_type": "PDUFA",
                "expected_date": "2026-11-20",
                "date_kind": "exact",
                "drug_name": "Kresladi",
                "indication": "Severe Leukocyte Adhesion Deficiency-I",
                "event_title": "PDUFA Target Action Date",
                "cash_and_equivalents_usd": 185_000_000,
                "quarterly_burn_rate_usd": 24_000_000,
                "runway_months": 23.1,
                "pipeline_total": 6,
                "catalyst_total": 2,
                "company_url": "https://biosniper.co/company/RCKT?utm_source=github",
                "event_url": "https://biosniper.co/calendar/event/101?utm_source=github",
                "runway_calculator_url": "https://biosniper.co/tools/cash-runway?cash=185000000&burn=24000000&utm_source=github",
            }
        ]
        md = render_catalog_markdown(rows, "2026-10-31")
        self.assertIn("[**RCKT**](https://biosniper.co/company/RCKT?utm_source=github)", md)
        self.assertIn("[Kresladi](https://biosniper.co/calendar/event/101?utm_source=github)", md)
        self.assertIn("[Runway Sim](https://biosniper.co/tools/cash-runway?cash=185000000&burn=24000000&utm_source=github)", md)

    def test_build_digest_markdown_renders_pdufa_and_runway_sections(self) -> None:
        rows = [
            {
                "ticker": "BTAI",
                "company_name": "BioXcel Therapeutics, Inc.",
                "event_id": 971191,
                "catalyst_type": "PDUFA",
                "expected_date": "2026-11-14",
                "indication": "Oncology",
                "cash_and_equivalents_usd": 12_841_000,
                "total_debt_usd": 107_152_000,
            },
            {
                "ticker": "CYDY",
                "company_name": "CytoDyn Inc.",
                "catalyst_type": "CASH_RUNWAY_WATCH",
                "expected_date": "2026-08-31",
                "cash_and_equivalents_usd": 4_120_000,
                "total_debt_usd": 49_470_000,
                "runway_months": 6.4,
            },
        ]
        md = build_digest_markdown(rows, generated_date="2026-11-01")
        self.assertIn("https://biosniper.co/feed.xml", md)
        self.assertIn("https://biosniper.co/atom.xml", md)
        self.assertIn("https://biosniper.co/company/BTAI", md)
        self.assertIn("https://biosniper.co/calendar/event/971191", md)
        self.assertIn("utm_source=github", md)
        self.assertNotIn("substack", md)
        self.assertIn("**~6 mos (<12m Watch)**", md)

    def test_public_dataset_enforces_teaser_cap_and_redacts_deep_balance_sheet_fields(self) -> None:
        self.assertEqual(MAX_PUBLIC_SAMPLE_ROWS, 9)
        for sensitive_col in (
            "total_debt_usd",
            "net_income_usd",
            "quarterly_burn_rate_usd",
            "financial_period_end",
            "catalyst_total",
        ):
            self.assertNotIn(sensitive_col, CSV_COLUMNS)

    def test_build_citations_pack_markdown_outputs_wiki_ref_and_methodology(self) -> None:
        rows = [
            {
                "ticker": "BTAI",
                "company_name": "BioXcel Therapeutics, Inc.",
                "event_id": 971191,
                "catalyst_type": "PDUFA",
                "expected_date": "2026-11-14",
            }
        ]
        md = build_citations_pack_markdown(rows, generated_date="2026-11-01")
        self.assertIn("{{cite web |title=BioXcel Therapeutics, Inc. (BTAI)", md)
        self.assertIn("https://biosniper.co/calendar/event/971191", md)
        self.assertIn("https://biosniper.co/tools/cash-runway", md)

    def test_publish_to_huggingface_resolves_explicit_token_and_files_exist(self) -> None:
        self.assertEqual(resolve_hf_token("  hf_test_123  "), "hf_test_123")
        kit_dir = Path(__file__).resolve().parent
        for rel in UPLOAD_FILES:
            self.assertTrue((kit_dir / rel).exists(), f"Missing {rel}")

    def test_validate_dataset_quality_rejects_otc_q_unknown_or_empty_buckets(self) -> None:
        def _row(ticker: str, ctype: str, rw: float | None = None) -> dict[str, object]:
            return {
                "ticker": ticker,
                "company_name": f"{ticker} Bio Inc.",
                "exchange": "Nasdaq",
                "catalyst_type": ctype,
                "event_title": "FDA PDUFA Review Target",
                "cash_and_equivalents_usd": 50_000_000,
                "runway_months": rw,
                "runway_band": "Verify Live SEC Runway & Burn on BioSniper",
                "company_url": f"https://biosniper.co/company/{ticker}",
                "runway_calculator_url": "https://biosniper.co/tools/cash-runway?cash=50000000",
            }

        valid_rows = [
            _row("DYN", "PDUFA"),
            _row("PRAX", "PDUFA"),
            _row("KRYS", "Earnings"),
            _row("AXSM", "Earnings"),
            _row("QURE", "CASH_RUNWAY_WATCH", 11.0),
            _row("CYDY", "CASH_RUNWAY_WATCH", 6.0),
        ]
        validate_dataset_quality(valid_rows)

        # Reject 5-letter OTC -Q bankruptcy ticker
        bad_otc = [dict(r) for r in valid_rows]
        bad_otc[4]["ticker"] = "SGMOQ"
        with self.assertRaises(DatasetQualityError):
            validate_dataset_quality(bad_otc)

        # Reject leaked UNKNOWN placeholder
        bad_unknown = [dict(r) for r in valid_rows]
        bad_unknown[0]["event_title"] = "PDUFA: Drug identity UNKNOWN"
        with self.assertRaises(DatasetQualityError):
            validate_dataset_quality(bad_unknown)

    def test_fetch_dataset_rows_prioritizes_clinical_and_tops_up_when_runway_bucket_sparse(self) -> None:
        from unittest.mock import patch

        self.assertEqual(_parse_retry_after("5", 1), 5.0)
        self.assertEqual(_parse_retry_after("99", 1), 6.0)
        self.assertEqual(_parse_retry_after(None, 2), 4.0)

        companies = {
            "items": [
                {"ticker": t, "name": f"{t} Therapeutics", "exchange": "Nasdaq", "signature_inputs": {"cash": 90_000_000}}
                for t in ("DYN", "PRAX", "MRNA", "ELAN", "VRTX", "BMRN", "ALNY", "IONS", "QURE")
            ]
        }
        runway = {
            "at_risk": [
                {"ticker": "SGMOQ", "name": "Sangamo", "cash_and_equivalents": 4_000_000, "runway_months": 4.3},
                {"ticker": "QURE", "name": "uniQure", "cash_and_equivalents": 55_000_000, "runway_months": 11.0},
            ]
        }
        pdufa = {
            "events": [
                {"id": 1, "company_ticker": "DYN", "catalyst_type": "PDUFA", "expected_date": "2027-01-21", "title": "PDUFA Review", "indexability": {"is_indexable": True}},
                {"id": 2, "company_ticker": "PRAX", "catalyst_type": "PDUFA", "expected_date": "2027-01-29", "title": "PDUFA Action", "indexability": {"is_indexable": True}},
            ]
        }
        cal = {
            "events": [
                {"id": 3, "company_ticker": "MRNA", "catalyst_type": "Earnings", "expected_date": "2026-11-10", "title": "Q3 2026 Earnings", "indexability": {"is_indexable": True}},
                {"id": 4, "company_ticker": "ELAN", "catalyst_type": "Earnings", "expected_date": "2026-11-11", "title": "Q3 2026 Earnings", "indexability": {"is_indexable": True}},
                {"id": 5, "company_ticker": "VRTX", "catalyst_type": "Phase 3", "expected_date": "2026-12-01", "title": "Phase 3 Readout", "indexability": {"is_indexable": True}},
                {"id": 6, "company_ticker": "BMRN", "catalyst_type": "Phase 2", "expected_date": "2026-12-10", "title": "Phase 2 Readout", "indexability": {"is_indexable": True}},
                {"id": 7, "company_ticker": "ALNY", "catalyst_type": "Data Readout", "expected_date": "2026-12-15", "title": "Topline Data", "indexability": {"is_indexable": True}},
                {"id": 8, "company_ticker": "IONS", "catalyst_type": "Phase 3", "expected_date": "2026-12-20", "title": "Pivotal Readout", "indexability": {"is_indexable": True}},
            ]
        }

        def fake_get(url: str, **_kwargs: object) -> dict[str, object]:
            if "/public/companies" in url:
                return companies
            if "/public/stats/cash-runway" in url:
                return runway
            if "types=PDUFA" in url:
                return pdufa
            return cal

        with patch("sync_dataset._http_get_json", side_effect=fake_get):
            rows = fetch_dataset_rows(upcoming_days=90, max_tickers=9)
        validate_dataset_quality(rows)
        self.assertGreaterEqual(len(rows), 7)
        tickers = [r["ticker"] for r in rows]
        self.assertIn("VRTX", tickers[:5])
        self.assertIn("BMRN", tickers[:5])
        self.assertIn("ALNY", tickers[:5])
        self.assertIn("QURE", tickers)


if __name__ == "__main__":
    unittest.main()
