"""Synthetic report data generators for standalone operation.

When Agent 6 (Regulatory Reporting) is unavailable, these generators
produce realistic data matching the expected API response schemas.
"""

from __future__ import annotations

import csv
import io
import random
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional

_report_id_counter = 1000


def _next_report_id() -> int:
    global _report_id_counter
    _report_id_counter += 1
    return _report_id_counter


# ═══════════════════════════════════════════════════════════════
# Pillar 3 (Basel III)
# ═══════════════════════════════════════════════════════════════


def generate_pillar3(reporting_date: str) -> dict[str, Any]:
    """Generate a synthetic Pillar 3 report with Table 3.2 AVA breakdown."""
    breakdown = {
        "Market Price Uncertainty": 1_245_320,
        "Close-Out Costs": 387_150,
        "Model Risk": 892_400,
        "Unearned Credit Spreads": 156_780,
        "Investment & Funding": 234_560,
        "Concentrated Positions": 178_930,
        "Future Admin Costs": 98_450,
    }
    total_ava = sum(breakdown.values())
    cet1 = 70_465_575
    ava_pct = total_ava / cet1 * 100

    return {
        "report_id": _next_report_id(),
        "reporting_date": reporting_date,
        "status": "DRAFT",
        "tables": {
            "3.2": {
                "total_ava": f"€{total_ava:,.0f}",
                "breakdown": breakdown,
                "as_pct_of_cet1": f"{ava_pct:.2f}%",
            }
        },
        "generated_at": datetime.utcnow().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# IFRS 13 Fair Value Hierarchy
# ═══════════════════════════════════════════════════════════════


def generate_ifrs13(reporting_date: str) -> dict[str, Any]:
    """Generate a synthetic IFRS 13 fair value hierarchy report."""
    l1_fv = 285_400_000
    l2_fv = 148_250_000
    l3_fv = 52_100_000
    total_fv = l1_fv + l2_fv + l3_fv

    fair_value_hierarchy = [
        {
            "level": "Level 1",
            "count": 22,
            "total_fair_value": l1_fv,
            "percentage_of_total": round(l1_fv / total_fv * 100, 1),
        },
        {
            "level": "Level 2",
            "count": 18,
            "total_fair_value": l2_fv,
            "percentage_of_total": round(l2_fv / total_fv * 100, 1),
        },
        {
            "level": "Level 3",
            "count": 8,
            "total_fair_value": l3_fv,
            "percentage_of_total": round(l3_fv / total_fv * 100, 1),
        },
    ]

    closing = 52_100_000
    level3_reconciliation = {
        "opening_balance": 48_750_000,
        "purchases": 5_200_000,
        "issuances": 0,
        "transfers_in": 1_800_000,
        "transfers_out": -2_350_000,
        "settlements": -1_500_000,
        "pnl": 200_000,
        "oci": 0,
        "closing_balance": closing,
        "check_passed": True,
    }

    valuation_techniques = [
        {
            "product_type": "FX Spot",
            "technique": "Market Approach — Quoted Prices",
            "inputs": ["Spot rate", "Bid-ask spread"],
            "observable_inputs": True,
        },
        {
            "product_type": "FX Forward",
            "technique": "Income Approach — Discounted Cash Flow",
            "inputs": ["Spot rate", "Forward points", "Discount rate"],
            "observable_inputs": True,
        },
        {
            "product_type": "FX Option (Vanilla)",
            "technique": "Black-Scholes-Merton",
            "inputs": ["Spot rate", "Implied volatility", "Risk-free rate", "Strike"],
            "observable_inputs": True,
        },
        {
            "product_type": "FX Option (Barrier)",
            "technique": "Heston Stochastic Volatility",
            "inputs": [
                "Spot rate",
                "Vol-of-vol",
                "Mean reversion speed",
                "Correlation",
                "Long-run variance",
            ],
            "observable_inputs": False,
        },
        {
            "product_type": "Interest Rate Swap",
            "technique": "Income Approach — Discounted Cash Flow",
            "inputs": ["Yield curve", "Swap spread", "Credit spread"],
            "observable_inputs": True,
        },
    ]

    return {
        "report_id": _next_report_id(),
        "reporting_date": reporting_date,
        "status": "DRAFT",
        "fair_value_hierarchy": fair_value_hierarchy,
        "level3_reconciliation": level3_reconciliation,
        "valuation_techniques": valuation_techniques,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# PRA110 (UK Regulatory Return)
# ═══════════════════════════════════════════════════════════════


def generate_pra110(reporting_date: str) -> dict[str, Any]:
    """Generate a synthetic PRA110 Section D report with XML."""
    section_d = {
        "d010_mpu": 1_245_320,
        "d020_close_out": 387_150,
        "d030_model_risk": 892_400,
        "d040_credit_spreads": 156_780,
        "d050_funding": 234_560,
        "d060_concentration": 178_930,
        "d070_admin": 98_450,
        "d080_total_ava": 3_193_590,
    }

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<PRA110Return>
  <Header>
    <FirmReference>FCA-123456</FirmReference>
    <ReportingDate>{reporting_date}</ReportingDate>
    <ReportingPeriod>Q4 2025</ReportingPeriod>
  </Header>
  <SectionD>
    <D010_MPU>{section_d['d010_mpu']}</D010_MPU>
    <D020_CloseOut>{section_d['d020_close_out']}</D020_CloseOut>
    <D030_ModelRisk>{section_d['d030_model_risk']}</D030_ModelRisk>
    <D040_CreditSpreads>{section_d['d040_credit_spreads']}</D040_CreditSpreads>
    <D050_Funding>{section_d['d050_funding']}</D050_Funding>
    <D060_Concentration>{section_d['d060_concentration']}</D060_Concentration>
    <D070_Admin>{section_d['d070_admin']}</D070_Admin>
    <D080_TotalAVA>{section_d['d080_total_ava']}</D080_TotalAVA>
  </SectionD>
</PRA110Return>"""

    return {
        "report_id": _next_report_id(),
        "reporting_date": reporting_date,
        "firm_reference": "FCA-123456",
        "status": "DRAFT",
        "section_d": section_d,
        "xml_content": xml_content,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# FR Y-14Q (US Federal Reserve)
# ═══════════════════════════════════════════════════════════════


def generate_fry14q(reporting_date: str) -> dict[str, Any]:
    """Generate a synthetic FR Y-14Q Schedule H.1 report with CSV."""
    l1_fv = 285_400_000
    l2_fv = 148_250_000
    l3_fv = 52_100_000
    total_fv = l1_fv + l2_fv + l3_fv

    schedule_h1 = {
        "fair_value_hierarchy": [
            {
                "level": "Level 1",
                "count": 22,
                "total_fair_value": l1_fv,
                "percentage_of_total": round(l1_fv / total_fv * 100, 1),
            },
            {
                "level": "Level 2",
                "count": 18,
                "total_fair_value": l2_fv,
                "percentage_of_total": round(l2_fv / total_fv * 100, 1),
            },
            {
                "level": "Level 3",
                "count": 8,
                "total_fair_value": l3_fv,
                "percentage_of_total": round(l3_fv / total_fv * 100, 1),
            },
        ],
        "prudent_valuation": {
            "market_price_uncertainty": 1_245_320,
            "close_out_costs": 387_150,
            "model_risk": 892_400,
            "unearned_credit_spreads": 156_780,
            "investment_funding": 234_560,
            "concentrated_positions": 178_930,
            "future_admin_costs": 98_450,
            "total": 3_193_590,
        },
        "var_metrics": {
            "var_1day_99": 2_450_000,
            "var_10day_99": 7_748_000,
            "stressed_var": 12_350_000,
        },
    }

    # Build CSV content
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Schedule H.1 — Trading Risk", "", ""])
    writer.writerow(["Reporting Date", reporting_date, ""])
    writer.writerow(["Firm Reference", "RSSD-9999", ""])
    writer.writerow([])
    writer.writerow(["Fair Value Hierarchy", "Count", "Total Fair Value", "% of Total"])
    for level in schedule_h1["fair_value_hierarchy"]:
        writer.writerow([
            level["level"],
            level["count"],
            level["total_fair_value"],
            f"{level['percentage_of_total']}%",
        ])
    writer.writerow([])
    writer.writerow(["Prudent Valuation Adjustments", "Amount (USD)"])
    pv = schedule_h1["prudent_valuation"]
    writer.writerow(["Market Price Uncertainty", pv["market_price_uncertainty"]])
    writer.writerow(["Close-Out Costs", pv["close_out_costs"]])
    writer.writerow(["Model Risk", pv["model_risk"]])
    writer.writerow(["Unearned Credit Spreads", pv["unearned_credit_spreads"]])
    writer.writerow(["Investment & Funding", pv["investment_funding"]])
    writer.writerow(["Concentrated Positions", pv["concentrated_positions"]])
    writer.writerow(["Future Admin Costs", pv["future_admin_costs"]])
    writer.writerow(["Total AVA", pv["total"]])
    writer.writerow([])
    writer.writerow(["VaR Metrics", "Amount (USD)"])
    var_m = schedule_h1["var_metrics"]
    writer.writerow(["1-Day 99% VaR", var_m["var_1day_99"]])
    writer.writerow(["10-Day 99% VaR", var_m["var_10day_99"]])
    writer.writerow(["Stressed VaR", var_m["stressed_var"]])

    csv_content = buf.getvalue()

    return {
        "report_id": _next_report_id(),
        "reporting_date": reporting_date,
        "firm_reference": "RSSD-9999",
        "status": "DRAFT",
        "schedule_h1": schedule_h1,
        "csv_content": csv_content,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# Audit Trail
# ═══════════════════════════════════════════════════════════════

_EVENT_TYPES = [
    "VALUATION_RUN",
    "MARK_ADJUSTMENT",
    "EXCEPTION_CREATED",
    "EXCEPTION_RESOLVED",
    "REPORT_GENERATED",
    "REPORT_SUBMITTED",
    "AVA_CALCULATED",
    "LEVEL_TRANSFER",
]

_USERS = [
    "j.chen",
    "s.patel",
    "m.garcia",
    "a.mueller",
    "r.johnson",
    "system",
]

_IPS = [
    "10.0.1.42",
    "10.0.1.55",
    "10.0.2.12",
    "10.0.2.78",
    "10.0.3.33",
    None,
]


def _make_audit_event(ts: datetime) -> dict[str, Any]:
    """Create a single realistic audit event."""
    event_type = random.choice(_EVENT_TYPES)
    user = random.choice(_USERS)
    ip = random.choice(_IPS)

    details: dict[str, Any] = {}
    if event_type == "VALUATION_RUN":
        details = {
            "run_id": f"IPV-{random.randint(100, 999)}",
            "positions_processed": random.randint(30, 48),
            "status": "COMPLETED",
        }
    elif event_type == "MARK_ADJUSTMENT":
        details = {
            "position_id": random.randint(1, 48),
            "old_mark": round(random.uniform(0.8, 1.5), 4),
            "new_mark": round(random.uniform(0.8, 1.5), 4),
            "reason": random.choice(["Stale price update", "Market data correction", "Model recalibration"]),
        }
    elif event_type == "EXCEPTION_CREATED":
        details = {
            "exception_id": random.randint(100, 500),
            "position_id": random.randint(1, 48),
            "severity": random.choice(["RED", "AMBER"]),
            "difference_pct": round(random.uniform(1.5, 15.0), 2),
        }
    elif event_type == "EXCEPTION_RESOLVED":
        details = {
            "exception_id": random.randint(100, 500),
            "resolution": random.choice(["Mark adjusted", "Data corrected", "Model updated", "Within tolerance"]),
        }
    elif event_type == "REPORT_GENERATED":
        details = {
            "report_type": random.choice(["PILLAR3", "IFRS13", "PRA110", "FRY14Q"]),
            "report_id": random.randint(1000, 9999),
            "reporting_date": (ts - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d"),
        }
    elif event_type == "REPORT_SUBMITTED":
        details = {
            "report_type": random.choice(["PILLAR3", "PRA110", "FRY14Q"]),
            "report_id": random.randint(1000, 9999),
            "regulator": random.choice(["ECB", "PRA", "FED"]),
            "confirmation_id": f"REG-{uuid.uuid4().hex[:8].upper()}",
        }
    elif event_type == "AVA_CALCULATED":
        details = {
            "position_id": random.randint(1, 48),
            "total_ava": round(random.uniform(5000, 500000), 2),
            "components": 7,
        }
    elif event_type == "LEVEL_TRANSFER":
        levels = ["Level 1", "Level 2", "Level 3"]
        from_level = random.choice(levels)
        to_level = random.choice([l for l in levels if l != from_level])
        details = {
            "position_id": random.randint(1, 48),
            "from_level": from_level,
            "to_level": to_level,
            "reason": random.choice([
                "Reduced market liquidity",
                "New observable inputs available",
                "Model change",
                "Quarterly reclassification",
            ]),
        }

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "user": user,
        "timestamp": ts.isoformat(),
        "details": details,
        "ip_address": ip,
    }


def generate_audit_trail(
    start_date: str,
    end_date: str,
    event_type: Optional[str] = None,
    user: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Generate synthetic audit trail events for a date range."""
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    if end < start:
        return []

    # Seed based on date range for consistency
    random.seed(hash((start_date, end_date)) % 2**32)

    # Generate ~5 events per day
    days = (end - start).days + 1
    total_events = min(days * 5, 500)

    events = []
    for _ in range(total_events):
        ts = start + timedelta(
            days=random.randint(0, max(0, days - 1)),
            hours=random.randint(7, 18),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59),
        )
        events.append(_make_audit_event(ts))

    # Sort by timestamp descending
    events.sort(key=lambda e: e["timestamp"], reverse=True)

    # Apply filters
    if event_type:
        events = [e for e in events if e["event_type"] == event_type]
    if user:
        events = [e for e in events if e["user"] == user]

    # Reset random seed
    random.seed()

    return events[offset : offset + limit]


def generate_audit_event(event_id: str) -> dict[str, Any]:
    """Generate a single synthetic audit event."""
    random.seed(hash(event_id) % 2**32)
    ts = datetime.utcnow() - timedelta(days=random.randint(0, 30))
    event = _make_audit_event(ts)
    event["event_id"] = event_id
    random.seed()
    return event


def generate_audit_report(start_date: str, end_date: str) -> dict[str, Any]:
    """Generate a synthetic audit report summary."""
    events = generate_audit_trail(start_date, end_date, limit=10000)

    events_by_type: dict[str, int] = {}
    users: set[str] = set()
    for e in events:
        et = e["event_type"]
        events_by_type[et] = events_by_type.get(et, 0) + 1
        users.add(e["user"])

    return {
        "period_start": start_date,
        "period_end": end_date,
        "total_events": len(events),
        "events_by_type": events_by_type,
        "users": sorted(users),
        "events": events[:100],  # Cap at 100 for the response
    }


def generate_audit_statistics(start_date: str, end_date: str) -> dict[str, Any]:
    """Generate synthetic audit statistics."""
    events = generate_audit_trail(start_date, end_date, limit=10000)

    by_type: dict[str, int] = {}
    by_user: dict[str, int] = {}
    for e in events:
        et = e["event_type"]
        by_type[et] = by_type.get(et, 0) + 1
        u = e["user"]
        by_user[u] = by_user.get(u, 0) + 1

    return {
        "period_start": start_date,
        "period_end": end_date,
        "total_events": len(events),
        "by_event_type": by_type,
        "by_user": by_user,
    }


def generate_audit_excel(start_date: str, end_date: str) -> bytes:
    """Generate a synthetic audit Excel report as bytes."""
    report = generate_audit_report(start_date, end_date)

    # Build CSV as fallback (no openpyxl dependency needed)
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Summary
    writer.writerow(["Audit Report"])
    writer.writerow([])
    writer.writerow(["Period:", f"{start_date} to {end_date}"])
    writer.writerow(["Total Events:", report["total_events"]])
    writer.writerow(["Unique Users:", len(report["users"])])
    writer.writerow([])
    writer.writerow(["Events by Type"])
    for etype, count in report["events_by_type"].items():
        writer.writerow([etype, count])
    writer.writerow([])

    # Events detail
    writer.writerow(["Event ID", "Type", "User", "Timestamp", "IP Address", "Details"])
    for event in report["events"]:
        writer.writerow([
            event["event_id"],
            event["event_type"],
            event["user"],
            event["timestamp"],
            event.get("ip_address", ""),
            str(event.get("details", {})),
        ])

    return buf.getvalue().encode("utf-8")
