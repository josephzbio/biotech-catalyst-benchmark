#!/usr/bin/env python3
"""BioSniper Open Biotech Toolkit — Powered by BioSniper Verified SEC, FDA & Clinical Data.

Zero-dependency Python 3.10+ toolkit and dataset SDK for quantitative biotech
analysts, bioinformaticians, and healthcare investors.

All data and calculations are backed by BioSniper's cross-verified intelligence engine:
- Platform: https://biosniper.co
- PDUFA Calendar: https://biosniper.co/calendar/pdufa
- Cash Runway Calculator: https://biosniper.co/tools/cash-runway
- Biotech Leaderboards: https://biosniper.co/rankings
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SITE_BASE = "https://biosniper.co"
DEFAULT_API_BASE = "https://biosniper-backend-d2fhdgw7ua-uw.a.run.app/api"
LOCAL_DATASET_PATH = Path(__file__).resolve().parent / "data" / "biotech_catalysts_runway.json"

PHASE_SUCCESS_RATES: dict[str, dict[str, float]] = {
    "all": {
        "Preclinical": 0.05,
        "Phase 1": 0.079,
        "Phase 1/2": 0.115,
        "Phase 2": 0.151,
        "Phase 2/3": 0.350,
        "Phase 3": 0.524,
        "NDA/BLA": 0.853,
        "PDUFA": 0.853,
        "Approved": 1.0,
    },
    "oncology": {
        "Preclinical": 0.035,
        "Phase 1": 0.053,
        "Phase 1/2": 0.078,
        "Phase 2": 0.108,
        "Phase 2/3": 0.280,
        "Phase 3": 0.439,
        "NDA/BLA": 0.824,
        "PDUFA": 0.824,
        "Approved": 1.0,
    },
    "rare_disease": {
        "Preclinical": 0.095,
        "Phase 1": 0.170,
        "Phase 1/2": 0.215,
        "Phase 2": 0.258,
        "Phase 2/3": 0.480,
        "Phase 3": 0.657,
        "NDA/BLA": 0.902,
        "PDUFA": 0.902,
        "Approved": 1.0,
    },
    "neurology": {
        "Preclinical": 0.042,
        "Phase 1": 0.059,
        "Phase 1/2": 0.088,
        "Phase 2": 0.123,
        "Phase 2/3": 0.310,
        "Phase 3": 0.496,
        "NDA/BLA": 0.831,
        "PDUFA": 0.831,
        "Approved": 1.0,
    },
}


def build_biosniper_url(
    path: str,
    *,
    query: dict[str, str | int | float | None] | None = None,
    utm_source: str = "github",
    utm_medium: str = "open_source",
    utm_campaign: str = "biotech_toolkit",
    utm_content: str | None = None,
    site: str = SITE_BASE,
) -> str:
    """Build a canonical BioSniper URL with bounded 4-field UTM attribution."""
    clean_site = site.rstrip("/")
    clean_path = "/" + path.lstrip("/")
    params: dict[str, str] = {}
    if query:
        for k, v in query.items():
            if v is not None and str(v) != "":
                params[k] = str(v)
    if utm_source:
        params["utm_source"] = utm_source
    if utm_medium:
        params["utm_medium"] = utm_medium
    if utm_campaign:
        params["utm_campaign"] = utm_campaign
    if utm_content:
        params["utm_content"] = utm_content
    qs = urllib.parse.urlencode(params)
    return f"{clean_site}{clean_path}?{qs}" if qs else f"{clean_site}{clean_path}"


@dataclass(frozen=True)
class CashRunwayResult:
    """Structured result of an SEC Form 10-Q/10-K cash runway calculation."""

    cash_usd: float
    quarterly_burn_usd: float
    revenue_offset_pct: float
    monthly_burn_usd: float
    runway_months: float | None
    has_dilution_warning: bool
    catalyst_buffer_months: float | None
    interactive_calculator_url: str
    company_evidence_url: str | None


def calculate_cash_runway(
    cash_usd: float,
    quarterly_burn_usd: float,
    *,
    revenue_offset_pct: float = 0.0,
    next_catalyst_months: float | None = None,
    ticker: str | None = None,
    utm_source: str = "github",
) -> CashRunwayResult:
    """Calculate biotech cash runway from unrestricted cash & quarterly operating burn."""
    if cash_usd < 0 or not math.isfinite(cash_usd):
        raise ValueError("cash_usd must be a non-negative finite number")
    if quarterly_burn_usd <= 0 or not math.isfinite(quarterly_burn_usd):
        raise ValueError("quarterly_burn_usd must be a positive finite number")
    if not math.isfinite(revenue_offset_pct):
        raise ValueError("revenue_offset_pct must be finite")

    adjusted_quarterly_burn = quarterly_burn_usd * (1.0 - revenue_offset_pct / 100.0)
    if adjusted_quarterly_burn <= 0:
        monthly_burn = 0.0
        runway_months: float | None = None
        has_warning = False
        catalyst_buffer: float | None = None
    else:
        monthly_burn = adjusted_quarterly_burn / 3.0
        runway_months = round(cash_usd / monthly_burn, 1)
        has_warning = runway_months < 12.0
        catalyst_buffer = (
            round(runway_months - next_catalyst_months, 1)
            if next_catalyst_months is not None
            else None
        )

    calc_url = build_biosniper_url(
        "/tools/cash-runway",
        query={
            "cash": int(round(cash_usd)),
            "burn": int(round(quarterly_burn_usd)),
        },
        utm_source=utm_source,
        utm_medium="open_source",
        utm_campaign="runway_toolkit",
        utm_content=ticker.upper() if ticker else "calculator",
    )
    comp_url = (
        build_biosniper_url(
            f"/company/{ticker.upper()}",
            utm_source=utm_source,
            utm_medium="open_source",
            utm_campaign="runway_toolkit",
            utm_content="company_evidence",
        )
        if ticker
        else None
    )
    return CashRunwayResult(
        cash_usd=cash_usd,
        quarterly_burn_usd=quarterly_burn_usd,
        revenue_offset_pct=revenue_offset_pct,
        monthly_burn_usd=round(monthly_burn, 2),
        runway_months=runway_months,
        has_dilution_warning=has_warning,
        catalyst_buffer_months=catalyst_buffer,
        interactive_calculator_url=calc_url,
        company_evidence_url=comp_url,
    )


@dataclass(frozen=True)
class RNPVResult:
    """Structured result of a Risk-Adjusted Net Present Value (rNPV) valuation."""

    peak_sales_millions: float
    phase: str
    therapeutic_area: str
    pos_probability: float
    unadjusted_npv_millions: float
    rnpv_millions: float
    net_cash_millions: float
    enterprise_rnpv_millions: float
    sensitivity_grid_millions: dict[str, dict[str, float]]
    methodology_url: str
    company_evidence_url: str | None


def calculate_rnpv(
    peak_sales_millions: float,
    *,
    phase: str = "Phase 2",
    therapeutic_area: str = "all",
    pos_override: float | None = None,
    years_to_launch: int = 4,
    exclusivity_years: int = 10,
    operating_margin: float = 0.65,
    discount_rate: float = 0.12,
    remaining_rd_cost_millions: float = 80.0,
    net_cash_millions: float = 0.0,
    ticker: str | None = None,
    utm_source: str = "github",
) -> RNPVResult:
    """Compute risk-adjusted NPV (rNPV) with ramp-up curve and WACC/PoS sensitivity grid."""
    if peak_sales_millions <= 0:
        raise ValueError("peak_sales_millions must be positive")
    if years_to_launch < 0 or exclusivity_years <= 0:
        raise ValueError("years_to_launch >= 0 and exclusivity_years > 0 required")
    if not (0.0 < discount_rate < 1.0):
        raise ValueError("discount_rate must be in (0, 1)")

    area_key = therapeutic_area.lower().strip()
    area_table = PHASE_SUCCESS_RATES.get(area_key, PHASE_SUCCESS_RATES["all"])
    pos = pos_override if pos_override is not None else area_table.get(phase, 0.151)
    if not (0.0 <= pos <= 1.0):
        raise ValueError("Probability of success must be in [0, 1]")

    ramp_curve = [0.15, 0.35, 0.65, 0.85, 1.00]

    def _compute_for(r: float, p: float) -> tuple[float, float]:
        rd_years = max(1, years_to_launch)
        annual_rd = remaining_rd_cost_millions / rd_years
        pv_rd = sum(annual_rd / ((1.0 + r) ** t) for t in range(1, rd_years + 1))

        pv_commercial_unadjusted = 0.0
        for yr_idx in range(exclusivity_years):
            t = years_to_launch + yr_idx + 1
            ramp = ramp_curve[yr_idx] if yr_idx < len(ramp_curve) else 1.0
            ebit = peak_sales_millions * ramp * operating_margin
            pv_commercial_unadjusted += ebit / ((1.0 + r) ** t)

        unadjusted_npv = pv_commercial_unadjusted - pv_rd
        risk_adjusted = (pv_commercial_unadjusted * p) - (pv_rd * min(1.0, (p + 1.0) / 2.0))
        return round(unadjusted_npv, 2), round(risk_adjusted, 2)

    unadj_npv, base_rnpv = _compute_for(discount_rate, pos)

    grid: dict[str, dict[str, float]] = {}
    for dr in (max(0.06, round(discount_rate - 0.02, 2)), round(discount_rate, 2), round(discount_rate + 0.02, 2)):
        dr_label = f"WACC_{int(round(dr * 100))}pct"
        grid[dr_label] = {}
        for pos_delta, pos_label in ((-0.05, "PoS_minus_5pct"), (0.0, "PoS_base"), (0.05, "PoS_plus_5pct")):
            adj_pos = min(1.0, max(0.01, pos + pos_delta))
            _, val = _compute_for(dr, adj_pos)
            grid[dr_label][pos_label] = val

    methodology_url = build_biosniper_url(
        "/blog/biotech-valuation-rnpv-explained",
        utm_source=utm_source,
        utm_medium="open_source",
        utm_campaign="rnpv_toolkit",
        utm_content="methodology",
    )
    comp_url = (
        build_biosniper_url(
            f"/company/{ticker.upper()}",
            utm_source=utm_source,
            utm_medium="open_source",
            utm_campaign="rnpv_toolkit",
            utm_content="company_evidence",
        )
        if ticker
        else None
    )

    return RNPVResult(
        peak_sales_millions=peak_sales_millions,
        phase=phase,
        therapeutic_area=area_key,
        pos_probability=round(pos, 4),
        unadjusted_npv_millions=unadj_npv,
        rnpv_millions=base_rnpv,
        net_cash_millions=round(net_cash_millions, 2),
        enterprise_rnpv_millions=round(base_rnpv + net_cash_millions, 2),
        sensitivity_grid_millions=grid,
        methodology_url=methodology_url,
        company_evidence_url=comp_url,
    )


def load_biosniper_dataset(
    *,
    dataset_path: Path | None = None,
    catalyst_type: str | None = None,
    max_runway_months: float | None = None,
) -> list[dict[str, Any]]:
    """Load BioSniper's verified catalyst & SEC cash-runway dataset from local snapshot."""
    target = dataset_path or LOCAL_DATASET_PATH
    if not target.exists():
        return []
    payload = json.loads(target.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = payload.get("records") or []
    if catalyst_type:
        ct_lower = catalyst_type.lower().strip()
        records = [r for r in records if ct_lower in str(r.get("catalyst_type") or "").lower()]
    if max_runway_months is not None:
        records = [
            r
            for r in records
            if isinstance(r.get("runway_months"), (int, float))
            and float(r["runway_months"]) <= max_runway_months
        ]
    return records


def format_biosniper_company_snapshot(payload: dict[str, Any], *, utm_source: str = "github") -> dict[str, Any]:
    """Normalize a BioSniper company payload into an analyst summary with canonical links."""
    ticker = str(payload.get("ticker") or "").upper()
    fin = payload.get("financial") or payload.get("signature_inputs") or {}
    cash = fin.get("cash_and_equivalents") if "cash_and_equivalents" in fin else fin.get("cash")
    burn = fin.get("quarterly_burn_rate")
    runway = fin.get("runway_months")
    pipelines = payload.get("pipeline_summary") or []

    return {
        "ticker": ticker,
        "name": payload.get("name") or ticker,
        "exchange": payload.get("exchange") or "",
        "development_stage": payload.get("development_stage") or "",
        "therapeutic_areas": payload.get("therapeutic_areas") or [],
        "pipeline_total": payload.get("pipeline_total") or fin.get("pipeline_total") or 0,
        "trial_count": payload.get("trial_count") or 0,
        "catalyst_total": payload.get("catalyst_total") or fin.get("catalyst_total") or 0,
        "lead_candidates": [
            {
                "drug_name": p.get("drug_name"),
                "phase": p.get("phase"),
                "indication": p.get("indication"),
                "drug_url": build_biosniper_url(
                    f"/drug/{p['drug_slug']}",
                    utm_source=utm_source,
                    utm_medium="open_source",
                    utm_campaign="company_snapshot",
                    utm_content=ticker,
                )
                if p.get("drug_slug")
                else None,
            }
            for p in pipelines[:5]
            if isinstance(p, dict)
        ],
        "cash_and_equivalents_usd": cash,
        "quarterly_burn_rate_usd": burn,
        "runway_months": runway,
        "ai_thesis_headline": (payload.get("ai_synthesis") or {}).get("headline") or "",
        "company_evidence_url": build_biosniper_url(
            f"/company/{ticker}",
            utm_source=utm_source,
            utm_medium="open_source",
            utm_campaign="company_snapshot",
            utm_content=ticker,
        ),
        "runway_calculator_url": build_biosniper_url(
            "/tools/cash-runway",
            query={
                "cash": int(round(cash)) if isinstance(cash, (int, float)) and cash > 0 else None,
                "burn": int(round(burn)) if isinstance(burn, (int, float)) and burn > 0 else None,
            },
            utm_source=utm_source,
            utm_medium="open_source",
            utm_campaign="company_snapshot",
            utm_content=ticker,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="BioSniper Open Biotech Toolkit — rNPV, SEC Cash Runway & BioSniper Dataset CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    runway_p = sub.add_parser("runway", help="Calculate SEC 10-Q/10-K biotech cash runway")
    runway_p.add_argument("--cash", type=float, required=True, help="Unrestricted cash & marketable securities (USD)")
    runway_p.add_argument("--burn", type=float, required=True, help="Quarterly operating cash burn (USD)")
    runway_p.add_argument("--revenue-offset", type=float, default=0.0, help="Revenue offset percentage (0-100)")
    runway_p.add_argument("--catalyst-months", type=float, default=None, help="Months until next binary catalyst")
    runway_p.add_argument("--ticker", type=str, default=None, help="Optional stock ticker (e.g., RCKT)")

    rnpv_p = sub.add_parser("rnpv", help="Calculate risk-adjusted NPV (rNPV) with sensitivity matrix")
    rnpv_p.add_argument("--peak-sales", type=float, required=True, help="Peak annual sales in USD millions")
    rnpv_p.add_argument("--phase", type=str, default="Phase 2", help="Clinical development phase")
    rnpv_p.add_argument("--area", type=str, default="all", choices=sorted(PHASE_SUCCESS_RATES.keys()))
    rnpv_p.add_argument("--discount-rate", type=float, default=0.12, help="Annual WACC / discount rate (default 0.12)")
    rnpv_p.add_argument("--rd-cost", type=float, default=80.0, help="Remaining R&D cost in USD millions")
    rnpv_p.add_argument("--net-cash", type=float, default=0.0, help="Company net cash in USD millions")
    rnpv_p.add_argument("--ticker", type=str, default=None, help="Optional stock ticker")

    ds_p = sub.add_parser("dataset", help="Query local BioSniper verified catalyst & cash-runway dataset")
    ds_p.add_argument("--type", type=str, default=None, help="Filter by catalyst_type (e.g., PDUFA, Cash_Runway_Watch)")
    ds_p.add_argument("--max-runway", type=float, default=None, help="Filter by max cash runway in months (e.g., 12)")
    ds_p.add_argument("--limit", type=int, default=10, help="Max rows to print")

    args = parser.parse_args(argv)
    if args.command == "runway":
        res = calculate_cash_runway(
            args.cash,
            args.burn,
            revenue_offset_pct=args.revenue_offset,
            next_catalyst_months=args.catalyst_months,
            ticker=args.ticker,
        )
        print(json.dumps(asdict(res), indent=2))
        return 0
    if args.command == "rnpv":
        res_rnpv = calculate_rnpv(
            args.peak_sales,
            phase=args.phase,
            therapeutic_area=args.area,
            discount_rate=args.discount_rate,
            remaining_rd_cost_millions=args.rd_cost,
            net_cash_millions=args.net_cash,
            ticker=args.ticker,
        )
        print(json.dumps(asdict(res_rnpv), indent=2))
        return 0
    if args.command == "dataset":
        records = load_biosniper_dataset(
            catalyst_type=args.type,
            max_runway_months=args.max_runway,
        )
        print(json.dumps(records[: max(1, args.limit)], indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
