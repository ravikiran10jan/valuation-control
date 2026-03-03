"""Day 1 P&L Reserve — classification, multi-method amortization, accounting & expiry release.

Classification:
  - SUSPICIOUS: |Day1 P&L| / FV > 20%, or SEVERE red flag, or Level3 with |P&L| > 10% FV
  - NORMAL:     |Day1 P&L| / FV between 2% and 20%
  - IDEAL:      |Day1 P&L| / FV < 2%

Amortization methods:
  - STRAIGHT_LINE:       equal monthly amounts over instrument life
  - FV_CONVERGENCE:      front-weighted schedule proportional to expected FV convergence
  - ACCELERATED_RELEASE: declining-balance (50% of remaining each period)

Accounting:
  Reserve creation:   Dr Trading Revenue / Cr Day 1 P&L Reserve
  Monthly amortize:   Dr Day 1 P&L Reserve / Cr Trading Revenue
  Expiry release:     Dr Day 1 P&L Reserve / Cr Trading Revenue  (release remaining)
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from dateutil.relativedelta import relativedelta
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postgres import (
    AmortizationSchedule,
    Day1PnL as Day1PnLRow,
    Day1PnLJournal,
    Reserve,
)
from app.models.schemas import (
    AccountingEntry,
    AmortizationEntry,
    AmortizationMethod,
    Day1PnLClassification,
    Day1PnLReserve,
    Day1PnLPortfolioSummary,
    PositionInput,
    RedFlagReport,
)
from app.services.red_flag_detector import detect_red_flags

log = structlog.get_logger()

# ── Thresholds ──────────────────────────────────────────────────
_SUSPICIOUS_PCT = Decimal("0.20")   # >20% of FV
_NORMAL_UPPER   = Decimal("0.20")   # <=20%
_NORMAL_LOWER   = Decimal("0.02")   # >2%
_LEVEL3_SUSPICIOUS_PCT = Decimal("0.10")  # Level3 with >10% triggers suspicious


def _classify(
    day1_pnl: Decimal,
    fair_value: Decimal,
    classification: str,
    red_flag_report: RedFlagReport | None,
) -> tuple[Day1PnLClassification, str]:
    """Return (classification, reason)."""
    if fair_value == 0:
        return Day1PnLClassification.SUSPICIOUS, "Fair value is zero — cannot validate"

    pct = abs(day1_pnl) / abs(fair_value)

    # Check for SEVERE red flags
    if red_flag_report and red_flag_report.requires_escalation:
        return (
            Day1PnLClassification.SUSPICIOUS,
            f"SEVERE red flag: {red_flag_report.escalation_reason}",
        )

    # Level 3 with material P&L
    if classification == "Level3" and pct > _LEVEL3_SUSPICIOUS_PCT:
        return (
            Day1PnLClassification.SUSPICIOUS,
            f"Level 3 position with Day 1 P&L at {float(pct)*100:.1f}% of FV",
        )

    # Percentage thresholds
    if pct > _SUSPICIOUS_PCT:
        return (
            Day1PnLClassification.SUSPICIOUS,
            f"Day 1 P&L is {float(pct)*100:.1f}% of FV — exceeds 20% threshold",
        )
    if pct > _NORMAL_LOWER:
        return (
            Day1PnLClassification.NORMAL,
            f"Day 1 P&L is {float(pct)*100:.1f}% of FV — within normal range",
        )
    return (
        Day1PnLClassification.IDEAL,
        f"Day 1 P&L is {float(pct)*100:.1f}% of FV — minimal difference",
    )


def _build_amortization(
    deferred: Decimal,
    trade_date: date | None,
    maturity_date: date | None,
    method: AmortizationMethod,
) -> list[AmortizationEntry]:
    """Build an amortization schedule using the chosen method."""
    start = trade_date or date.today()
    end = maturity_date or start + relativedelta(years=1)
    if end <= start or deferred == 0:
        return []

    periods: list[date] = []
    current = start + relativedelta(months=1)
    while current <= end:
        periods.append(current)
        current += relativedelta(months=1)
    if not periods:
        periods = [end]

    n = len(periods)
    entries: list[AmortizationEntry] = []
    cumulative = Decimal(0)

    if method == AmortizationMethod.STRAIGHT_LINE:
        monthly = (deferred / Decimal(n)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for i, pd in enumerate(periods):
            amt = deferred - cumulative if i == n - 1 else monthly  # ensure sum == deferred
            cumulative += amt
            entries.append(AmortizationEntry(
                period_date=pd,
                amortization_amount=amt,
                cumulative_recognized=cumulative,
                remaining_deferred=deferred - cumulative,
            ))

    elif method == AmortizationMethod.FV_CONVERGENCE:
        # Front-weighted: weights decrease linearly  (n, n-1, ... , 1)
        total_weight = Decimal(n * (n + 1) // 2)
        for i, pd in enumerate(periods):
            weight = Decimal(n - i)
            amt = (deferred * weight / total_weight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if i == n - 1:
                amt = deferred - cumulative
            cumulative += amt
            entries.append(AmortizationEntry(
                period_date=pd,
                amortization_amount=amt,
                cumulative_recognized=cumulative,
                remaining_deferred=deferred - cumulative,
            ))

    elif method == AmortizationMethod.ACCELERATED_RELEASE:
        # Declining balance — release 50% of remaining each period
        remaining = deferred
        for i, pd in enumerate(periods):
            if i == n - 1:
                amt = remaining  # release all remaining at last period
            else:
                amt = (remaining * Decimal("0.50")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            remaining -= amt
            cumulative += amt
            entries.append(AmortizationEntry(
                period_date=pd,
                amortization_amount=amt,
                cumulative_recognized=cumulative,
                remaining_deferred=remaining,
            ))

    return entries


def _build_accounting_entries(
    position_id: int,
    deferred: Decimal,
    trade_date: date | None,
    schedule: list[AmortizationEntry],
    is_expired: bool,
    reserve_balance: Decimal,
) -> list[AccountingEntry]:
    """Generate double-entry accounting journal entries."""
    entries: list[AccountingEntry] = []
    td = trade_date or date.today()

    if deferred != 0:
        # 1. Reserve creation
        entries.append(AccountingEntry(
            entry_id=str(uuid4())[:8],
            entry_date=td,
            description=f"Day 1 P&L reserve creation — position #{position_id}",
            debit_account="Trading Revenue",
            credit_account="Day 1 P&L Reserve",
            amount=abs(deferred),
            position_id=position_id,
            entry_type="RESERVE_CREATION",
        ))

        # 2. Monthly amortization entries
        for entry in schedule:
            entries.append(AccountingEntry(
                entry_id=str(uuid4())[:8],
                entry_date=entry.period_date,
                description=f"Day 1 P&L amortization — position #{position_id}",
                debit_account="Day 1 P&L Reserve",
                credit_account="Trading Revenue",
                amount=abs(entry.amortization_amount),
                position_id=position_id,
                entry_type="AMORTIZATION",
            ))

    # 3. Expiry release
    if is_expired and reserve_balance > 0:
        entries.append(AccountingEntry(
            entry_id=str(uuid4())[:8],
            entry_date=date.today(),
            description=f"Day 1 P&L reserve released on expiry — position #{position_id}",
            debit_account="Day 1 P&L Reserve",
            credit_account="Trading Revenue",
            amount=abs(reserve_balance),
            position_id=position_id,
            entry_type="EXPIRY_RELEASE",
        ))

    return entries


async def calculate_day1_pnl_reserve(
    db: AsyncSession,
    position: PositionInput,
    amortization_method: AmortizationMethod = AmortizationMethod.STRAIGHT_LINE,
    recent_trade_count: int | None = None,
    average_trade_count: int | None = None,
    remark_count: int | None = None,
    remark_period_days: int = 30,
) -> Day1PnLReserve:
    """Full Day 1 P&L reserve calculation with classification, amortization & accounting."""
    txn = position.transaction_price or Decimal(0)
    fv = position.vc_fair_value or Decimal(0)
    day1_pnl = txn - fv
    day1_pnl_pct = (abs(day1_pnl) / abs(fv) * 100) if fv != 0 else Decimal(0)

    # Red flag analysis
    red_flag_report = detect_red_flags(
        position=position,
        transaction_price=txn,
        fair_value=fv,
        recent_trade_count=recent_trade_count,
        average_trade_count=average_trade_count,
        remark_count=remark_count,
        remark_period_days=remark_period_days,
    )

    # Classification
    classification, reason = _classify(day1_pnl, fv, position.classification, red_flag_report)

    # Recognition
    if position.classification == "Level3" or classification == Day1PnLClassification.SUSPICIOUS:
        recognition_status = "DEFERRED"
        recognized = Decimal(0)
        deferred = day1_pnl
    else:
        recognition_status = "RECOGNIZED"
        recognized = day1_pnl
        deferred = Decimal(0)

    # Expiry check
    is_expired = False
    if position.maturity_date and position.maturity_date <= date.today():
        is_expired = True

    # Amortization
    schedule: list[AmortizationEntry] = []
    if recognition_status == "DEFERRED" and deferred != 0:
        schedule = _build_amortization(deferred, position.trade_date, position.maturity_date, amortization_method)

    # Current reserve balance (initially = deferred, reduced by amortization to-date)
    amortized_to_date = Decimal(0)
    today = date.today()
    for entry in schedule:
        if entry.period_date <= today:
            amortized_to_date += entry.amortization_amount
    reserve_balance = abs(deferred) - abs(amortized_to_date)
    if is_expired:
        reserve_balance = Decimal(0)

    # Accounting
    accounting = _build_accounting_entries(
        position.position_id, deferred, position.trade_date, schedule, is_expired, reserve_balance,
    )

    # Persist
    pnl_row = Day1PnLRow(
        position_id=position.position_id,
        transaction_price=txn,
        fair_value=fv,
        day1_pnl=day1_pnl,
        recognition_status=recognition_status,
        recognized_amount=recognized,
        deferred_amount=deferred,
        trade_date=position.trade_date,
    )
    db.add(pnl_row)

    reserve = Reserve(
        position_id=position.position_id,
        reserve_type="Day1_PnL",
        amount=abs(deferred),
        calculation_date=date.today(),
        rationale=(
            f"Day1 P&L ${float(day1_pnl):,.0f} — {classification.value} ({reason}); "
            f"Method: {amortization_method.value}"
        ),
        components={
            "classification": classification.value,
            "classification_reason": reason,
            "amortization_method": amortization_method.value,
            "red_flags_triggered": red_flag_report.total_flags_triggered,
            "is_expired": is_expired,
        },
    )
    db.add(reserve)

    # Persist amortization schedule
    for entry in schedule:
        row = AmortizationSchedule(
            position_id=position.position_id,
            period_date=entry.period_date,
            amortization_amount=entry.amortization_amount,
            cumulative_recognized=entry.cumulative_recognized,
            remaining_deferred=entry.remaining_deferred,
        )
        db.add(row)

    # Persist journal entries
    for je in accounting:
        j_row = Day1PnLJournal(
            position_id=je.position_id,
            entry_date=je.entry_date,
            description=je.description,
            debit_account=je.debit_account,
            credit_account=je.credit_account,
            amount=je.amount,
            entry_type=je.entry_type,
        )
        db.add(j_row)

    await db.flush()

    log.info(
        "day1_pnl_reserve_calculated",
        position_id=position.position_id,
        classification=classification.value,
        day1_pnl=float(day1_pnl),
        method=amortization_method.value,
        is_expired=is_expired,
    )

    return Day1PnLReserve(
        position_id=position.position_id,
        trade_id=position.trade_id,
        transaction_price=txn,
        fair_value=fv,
        day1_pnl=day1_pnl,
        day1_pnl_pct=day1_pnl_pct,
        classification=classification,
        classification_reason=reason,
        recognition_status=recognition_status,
        recognized_amount=recognized,
        deferred_amount=deferred,
        reserve_balance=reserve_balance,
        trade_date=position.trade_date,
        maturity_date=position.maturity_date,
        amortization_method=amortization_method,
        amortization_schedule=schedule,
        accounting_entries=accounting,
        red_flag_report=red_flag_report,
        is_expired=is_expired,
        released_on_expiry=is_expired and deferred != 0,
    )


async def calculate_portfolio_day1_pnl(
    db: AsyncSession,
    positions: list[PositionInput],
    amortization_method: AmortizationMethod = AmortizationMethod.STRAIGHT_LINE,
) -> Day1PnLPortfolioSummary:
    """Calculate Day 1 P&L reserves for a portfolio of positions."""
    results: list[Day1PnLReserve] = []
    all_entries: list[AccountingEntry] = []

    for pos in positions:
        result = await calculate_day1_pnl_reserve(db, pos, amortization_method)
        results.append(result)
        all_entries.extend(result.accounting_entries)

    await db.flush()

    return Day1PnLPortfolioSummary(
        total_positions=len(results),
        total_day1_pnl=sum(r.day1_pnl for r in results),
        total_deferred=sum(r.deferred_amount for r in results),
        total_recognized=sum(r.recognized_amount for r in results),
        total_reserve_balance=sum(r.reserve_balance for r in results),
        suspicious_count=sum(1 for r in results if r.classification == Day1PnLClassification.SUSPICIOUS),
        normal_count=sum(1 for r in results if r.classification == Day1PnLClassification.NORMAL),
        ideal_count=sum(1 for r in results if r.classification == Day1PnLClassification.IDEAL),
        positions=results,
        accounting_entries=all_entries,
    )
