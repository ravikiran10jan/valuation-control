"""Seed script: Populates the database with FX positions from IPV_FX_Model.

Clears all existing data and inserts 7 FX positions with associated
market data, dealer quotes, exceptions, comparisons, and barrier details
exactly matching the IPV_FX_Model Excel workbook.

Usage:
    python -m app.seed_fx_data
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, engine, Base
from app.models.postgres import (
    Position,
    FXBarrierDetail,
    MarketDataSnapshot,
    DealerQuote,
    VCException,
    ExceptionComment,
    ValuationComparison,
    CommitteeAgendaItem,
)

VALUATION_DATE = date(2025, 2, 14)


async def clear_all_tables(db: AsyncSession) -> None:
    """Delete all rows from every table (respecting FK order)."""
    await db.execute(text("DELETE FROM committee_agenda_items"))
    await db.execute(text("DELETE FROM exception_comments"))
    await db.execute(text("DELETE FROM exceptions"))
    await db.execute(text("DELETE FROM valuation_comparisons"))
    await db.execute(text("DELETE FROM dealer_quotes"))
    await db.execute(text("DELETE FROM market_data_snapshots"))
    await db.execute(text("DELETE FROM fx_barrier_details"))
    await db.execute(text("DELETE FROM rates_swap_details"))
    await db.execute(text("DELETE FROM credit_details"))
    await db.execute(text("DELETE FROM equity_details"))
    await db.execute(text("DELETE FROM positions"))
    await db.commit()
    print("Cleared all tables.")


async def create_tables() -> None:
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created / verified.")


async def seed_positions(db: AsyncSession) -> list[Position]:
    """Insert the 7 FX positions from IPV_FX_Model."""

    positions_data = [
        # 1. EUR/USD Spot — G10, L1, GREEN
        {
            "trade_id": "FX-SPOT-001",
            "product_type": "Spot",
            "asset_class": "FX",
            "currency_pair": "EUR/USD",
            "notional": Decimal("150000000"),
            "notional_usd": Decimal("150000000"),
            "currency": "EUR",
            "trade_date": date(2025, 2, 14),
            "maturity_date": date(2025, 2, 18),
            "settlement_date": date(2025, 2, 18),
            "counterparty": "Institutional Client A",
            "desk_mark": Decimal("1.082500"),
            "vc_fair_value": Decimal("1.082300"),
            "book_value_usd": Decimal("162375000"),
            "difference": Decimal("0.000200"),
            "difference_pct": Decimal("0.0185"),
            "exception_status": "GREEN",
            "fair_value_level": "L1",
            "pricing_source": "WM/Reuters WMCO",
            "fva_usd": Decimal("-300"),
            "valuation_date": VALUATION_DATE,
        },
        # 2. GBP/USD Spot — G10, L1, GREEN
        {
            "trade_id": "FX-SPOT-002",
            "product_type": "Spot",
            "asset_class": "FX",
            "currency_pair": "GBP/USD",
            "notional": Decimal("85000000"),
            "notional_usd": Decimal("85000000"),
            "currency": "GBP",
            "trade_date": date(2025, 2, 13),
            "maturity_date": date(2025, 2, 18),
            "settlement_date": date(2025, 2, 18),
            "counterparty": "Hedge Fund B",
            "desk_mark": Decimal("1.264800"),
            "vc_fair_value": Decimal("1.264500"),
            "book_value_usd": Decimal("107508000"),
            "difference": Decimal("0.000300"),
            "difference_pct": Decimal("0.0237"),
            "exception_status": "GREEN",
            "fair_value_level": "L1",
            "pricing_source": "WM/Reuters WMCO",
            "fva_usd": Decimal("-255"),
            "valuation_date": VALUATION_DATE,
        },
        # 3. USD/JPY Spot — G10, L1, GREEN
        {
            "trade_id": "FX-SPOT-003",
            "product_type": "Spot",
            "asset_class": "FX",
            "currency_pair": "USD/JPY",
            "notional": Decimal("50000000"),
            "notional_usd": Decimal("50000000"),
            "currency": "USD",
            "trade_date": date(2025, 2, 12),
            "maturity_date": date(2025, 2, 18),
            "settlement_date": date(2025, 2, 18),
            "counterparty": "Corporate Treasury C",
            "desk_mark": Decimal("149.850000"),
            "vc_fair_value": Decimal("149.880000"),
            "book_value_usd": Decimal("50000000"),
            "difference": Decimal("-0.030000"),
            "difference_pct": Decimal("-0.0200"),
            "exception_status": "GREEN",
            "fair_value_level": "L1",
            "pricing_source": "WM/Reuters WMCO",
            "fva_usd": Decimal("100"),
            "valuation_date": VALUATION_DATE,
        },
        # 4. USD/TRY Spot — EM, L2, RED (8.22% breach)
        {
            "trade_id": "FX-SPOT-004",
            "product_type": "Spot (EM)",
            "asset_class": "FX",
            "currency_pair": "USD/TRY",
            "notional": Decimal("25000000"),
            "notional_usd": Decimal("25000000"),
            "currency": "USD",
            "trade_date": date(2025, 2, 10),
            "maturity_date": date(2025, 2, 18),
            "settlement_date": date(2025, 2, 18),
            "counterparty": "EM Trading Desk Internal",
            "desk_mark": Decimal("32.450000"),
            "vc_fair_value": Decimal("35.120000"),
            "book_value_usd": Decimal("25000000"),
            "difference": Decimal("-2.670000"),
            "difference_pct": Decimal("-8.2200"),
            "exception_status": "RED",
            "fair_value_level": "L2",
            "pricing_source": "WM/Reuters WMCO",
            "fva_usd": Decimal("-18500"),
            "valuation_date": VALUATION_DATE,
        },
        # 5. USD/BRL Spot — EM, L2, AMBER (1.17%)
        {
            "trade_id": "FX-SPOT-005",
            "product_type": "Spot (EM)",
            "asset_class": "FX",
            "currency_pair": "USD/BRL",
            "notional": Decimal("10000000"),
            "notional_usd": Decimal("10000000"),
            "currency": "USD",
            "trade_date": date(2025, 2, 11),
            "maturity_date": date(2025, 2, 18),
            "settlement_date": date(2025, 2, 18),
            "counterparty": "EM Macro Fund D",
            "desk_mark": Decimal("5.120000"),
            "vc_fair_value": Decimal("5.180000"),
            "book_value_usd": Decimal("10000000"),
            "difference": Decimal("-0.060000"),
            "difference_pct": Decimal("-1.1700"),
            "exception_status": "AMBER",
            "fair_value_level": "L2",
            "pricing_source": "WM/Reuters WMCO",
            "fva_usd": Decimal("-1160"),
            "valuation_date": VALUATION_DATE,
        },
        # 6. EUR/USD 1Y Forward — L2, GREEN
        {
            "trade_id": "FX-FWD-001",
            "product_type": "Forward",
            "asset_class": "FX",
            "currency_pair": "EUR/USD",
            "notional": Decimal("120000000"),
            "notional_usd": Decimal("120000000"),
            "currency": "EUR",
            "trade_date": date(2025, 1, 20),
            "maturity_date": date(2026, 2, 15),
            "settlement_date": date(2026, 2, 17),
            "counterparty": "Pension Fund E",
            "desk_mark": Decimal("1.095000"),
            "vc_fair_value": Decimal("1.094800"),
            "book_value_usd": Decimal("131400000"),
            "difference": Decimal("0.000200"),
            "difference_pct": Decimal("0.0183"),
            "exception_status": "GREEN",
            "fair_value_level": "L2",
            "pricing_source": "Bloomberg FXFA",
            "fva_usd": Decimal("-240"),
            "valuation_date": VALUATION_DATE,
        },
        # 7. EUR/USD Barrier Option (Double-No-Touch) — L3, RED
        {
            "trade_id": "FX-OPT-001",
            "product_type": "Barrier (DNT)",
            "asset_class": "FX",
            "currency_pair": "EUR/USD",
            "notional": Decimal("50000000"),
            "notional_usd": Decimal("50000000"),
            "currency": "EUR",
            "trade_date": date(2025, 1, 5),
            "maturity_date": date(2025, 12, 31),
            "settlement_date": date(2026, 1, 2),
            "counterparty": "Structured Products Client F",
            "desk_mark": Decimal("425000"),
            "vc_fair_value": Decimal("306000"),
            "book_value_usd": Decimal("850000"),
            "difference": Decimal("119000"),
            "difference_pct": Decimal("-28.0000"),
            "exception_status": "RED",
            "fair_value_level": "L3",
            "pricing_source": "Internal BS Model",
            "fva_usd": Decimal("-119000"),
            "valuation_date": VALUATION_DATE,
        },
    ]

    created = []
    for data in positions_data:
        pos = Position(**data)
        db.add(pos)
        await db.flush()
        created.append(pos)
        print(f"  Position: {pos.trade_id} ({pos.currency_pair} {pos.product_type}) -> id={pos.position_id}")

    await db.commit()
    for pos in created:
        await db.refresh(pos)
    print(f"Seeded {len(created)} FX positions.")
    return created


async def seed_barrier_detail(db: AsyncSession, barrier_pos: Position) -> None:
    """Insert FX barrier option details from Level3_Barrier_Model sheet."""
    detail = FXBarrierDetail(
        position_id=barrier_pos.position_id,
        currency_pair="EUR/USD",
        spot_ref=Decimal("1.08230"),
        lower_barrier=Decimal("1.05000"),
        upper_barrier=Decimal("1.12000"),
        barrier_type="DNT",
        volatility=Decimal("0.0680"),
        time_to_expiry=Decimal("0.8767"),  # 320/365 days
        domestic_rate=Decimal("0.0525"),   # USD Fed rate
        foreign_rate=Decimal("0.0425"),    # EUR ECB rate
        survival_probability=Decimal("0.7200"),
        premium_market=Decimal("425000"),
        premium_model=Decimal("306000"),
    )
    db.add(detail)
    await db.commit()
    print("Seeded FX barrier detail.")


async def seed_market_data(db: AsyncSession) -> None:
    """Insert market data snapshots matching IPV_Price_Sources sheet."""
    snapshots = [
        # Spot rates (WM/Reuters 4pm Fix)
        ("WM/Reuters", "EUR/USD_Spot", Decimal("1.08230000")),
        ("WM/Reuters", "EUR/USD_Bid", Decimal("1.08220000")),
        ("WM/Reuters", "EUR/USD_Ask", Decimal("1.08240000")),
        ("WM/Reuters", "GBP/USD_Spot", Decimal("1.26450000")),
        ("WM/Reuters", "GBP/USD_Bid", Decimal("1.26430000")),
        ("WM/Reuters", "GBP/USD_Ask", Decimal("1.26470000")),
        ("WM/Reuters", "USD/JPY_Spot", Decimal("149.88000000")),
        ("WM/Reuters", "USD/JPY_Bid", Decimal("149.86000000")),
        ("WM/Reuters", "USD/JPY_Ask", Decimal("149.90000000")),
        ("WM/Reuters", "USD/TRY_Spot", Decimal("35.12000000")),
        ("WM/Reuters", "USD/TRY_Bid", Decimal("35.08000000")),
        ("WM/Reuters", "USD/TRY_Ask", Decimal("35.16000000")),
        ("WM/Reuters", "USD/BRL_Spot", Decimal("5.18000000")),
        ("WM/Reuters", "USD/BRL_Bid", Decimal("5.17000000")),
        ("WM/Reuters", "USD/BRL_Ask", Decimal("5.19000000")),

        # Forward points (Bloomberg FXFA)
        ("Bloomberg_FXFA", "EUR/USD_1M_FWD", Decimal("9.00000000")),
        ("Bloomberg_FXFA", "EUR/USD_3M_FWD", Decimal("27.00000000")),
        ("Bloomberg_FXFA", "EUR/USD_6M_FWD", Decimal("54.00000000")),
        ("Bloomberg_FXFA", "EUR/USD_1Y_FWD", Decimal("108.00000000")),

        # Interest rates
        ("ECB", "EUR_Rate_1Y", Decimal("4.25000000")),
        ("Fed", "USD_Rate_1Y", Decimal("5.25000000")),

        # Vol surface (Bloomberg OVML) — EUR/USD 1Y
        ("Bloomberg_OVML", "EUR/USD_1Y_ATM_Vol", Decimal("6.80000000")),
        ("Bloomberg_OVML", "EUR/USD_1Y_25D_RR", Decimal("0.80000000")),
        ("Bloomberg_OVML", "EUR/USD_1Y_25D_BF", Decimal("0.30000000")),
    ]

    for source, field, value in snapshots:
        snap = MarketDataSnapshot(
            valuation_date=VALUATION_DATE,
            data_source=source,
            field_name=field,
            field_value=value,
        )
        db.add(snap)

    await db.commit()
    print(f"Seeded {len(snapshots)} market data snapshots.")


async def seed_dealer_quotes(db: AsyncSession, positions: list[Position]) -> None:
    """Insert dealer quotes for EM and barrier positions."""
    pos_by_trade = {p.trade_id: p for p in positions}

    quotes_data = [
        # USD/TRY dealer quotes — EM requires multiple dealer validation
        (pos_by_trade["FX-SPOT-004"].position_id, "Deutsche Bank", Decimal("35.10"), "Mid"),
        (pos_by_trade["FX-SPOT-004"].position_id, "JP Morgan", Decimal("35.14"), "Mid"),
        (pos_by_trade["FX-SPOT-004"].position_id, "Goldman Sachs", Decimal("35.08"), "Mid"),
        (pos_by_trade["FX-SPOT-004"].position_id, "Citibank", Decimal("35.16"), "Mid"),

        # USD/BRL dealer quotes
        (pos_by_trade["FX-SPOT-005"].position_id, "Itau BBA", Decimal("5.17"), "Mid"),
        (pos_by_trade["FX-SPOT-005"].position_id, "Bradesco", Decimal("5.19"), "Mid"),
        (pos_by_trade["FX-SPOT-005"].position_id, "BTG Pactual", Decimal("5.18"), "Mid"),

        # Barrier option — broker quotes for model validation
        (pos_by_trade["FX-OPT-001"].position_id, "Goldman Sachs", Decimal("420000"), "Mid"),
        (pos_by_trade["FX-OPT-001"].position_id, "JP Morgan", Decimal("415000"), "Mid"),
        (pos_by_trade["FX-OPT-001"].position_id, "Barclays", Decimal("410000"), "Mid"),
    ]

    for pid, dealer, value, qtype in quotes_data:
        q = DealerQuote(
            position_id=pid,
            dealer_name=dealer,
            quote_value=value,
            quote_date=VALUATION_DATE,
            quote_type=qtype,
        )
        db.add(q)

    await db.commit()
    print(f"Seeded {len(quotes_data)} dealer quotes.")


async def seed_exceptions(db: AsyncSession, positions: list[Position]) -> list[VCException]:
    """Insert exceptions for RED and AMBER breaches."""
    pos_by_trade = {p.trade_id: p for p in positions}
    exceptions_data = []

    # Exception 1: USD/TRY RED breach — stale desk mark
    exc1 = VCException(
        position_id=pos_by_trade["FX-SPOT-004"].position_id,
        difference=Decimal("-2.67"),
        difference_pct=Decimal("-8.22"),
        status="OPEN",
        severity="RED",
        created_date=VALUATION_DATE,
        assigned_to="Sarah Chen",
        days_open=0,
        escalation_level=1,
    )
    db.add(exc1)
    await db.flush()
    exceptions_data.append(exc1)

    # Exception 2: USD/BRL AMBER breach — moderate EM vol
    exc2 = VCException(
        position_id=pos_by_trade["FX-SPOT-005"].position_id,
        difference=Decimal("-0.06"),
        difference_pct=Decimal("-1.17"),
        status="OPEN",
        severity="AMBER",
        created_date=VALUATION_DATE,
        assigned_to="Michael Park",
        days_open=0,
        escalation_level=1,
    )
    db.add(exc2)
    await db.flush()
    exceptions_data.append(exc2)

    # Exception 3: Barrier Option RED — model uncertainty
    exc3 = VCException(
        position_id=pos_by_trade["FX-OPT-001"].position_id,
        difference=Decimal("119000"),
        difference_pct=Decimal("-28.00"),
        status="INVESTIGATING",
        severity="RED",
        created_date=date(2025, 2, 10),
        assigned_to="David Liu",
        days_open=4,
        escalation_level=2,
    )
    db.add(exc3)
    await db.flush()
    exceptions_data.append(exc3)

    await db.commit()
    for exc in exceptions_data:
        await db.refresh(exc)
    print(f"Seeded {len(exceptions_data)} exceptions.")
    return exceptions_data


async def seed_exception_comments(db: AsyncSession, exceptions: list[VCException]) -> None:
    """Insert dispute/discussion comments on exceptions."""
    comments = [
        # USD/TRY exception comments
        ExceptionComment(
            exception_id=exceptions[0].exception_id,
            user_name="SYSTEM",
            comment_text="IPV breach detected: Desk mark 32.45 vs IPV 35.12 (-8.22%). "
                         "Exceeds EM Spot threshold of 5%. Lira depreciation event on 14-Feb.",
        ),
        ExceptionComment(
            exception_id=exceptions[0].exception_id,
            user_name="Sarah Chen",
            comment_text="Desk trader confirmed mark is from 10-Feb close. "
                         "Lira moved significantly since. Requesting desk to update mark to current WM/Reuters fix.",
        ),

        # USD/BRL exception comments
        ExceptionComment(
            exception_id=exceptions[1].exception_id,
            user_name="SYSTEM",
            comment_text="IPV breach detected: Desk mark 5.12 vs IPV 5.18 (-1.17%). "
                         "Within EM Spot threshold but flagged AMBER for monitoring. Real weakness vs USD.",
        ),

        # Barrier option exception comments
        ExceptionComment(
            exception_id=exceptions[2].exception_id,
            user_name="SYSTEM",
            comment_text="IPV breach detected: Desk premium $425k vs VC model $306k (-28%). "
                         "Level 3 position. Vol surface calibration uncertainty +/-5%.",
        ),
        ExceptionComment(
            exception_id=exceptions[2].exception_id,
            user_name="Desk Trader",
            comment_text="Using weekly observation for barrier monitoring. Client quote of $420k "
                         "supports desk mark. Vol surface from OVML is stale.",
        ),
        ExceptionComment(
            exception_id=exceptions[2].exception_id,
            user_name="David Liu",
            comment_text="VC response: Term sheet specifies daily observation, not weekly. "
                         "VC model uses daily obs which gives lower survival probability (72%). "
                         "Breach stands. Escalating to Valuation Committee.",
        ),
        ExceptionComment(
            exception_id=exceptions[2].exception_id,
            user_name="SYSTEM",
            comment_text="Exception escalated to Manager after 4 days open.",
        ),
    ]

    for c in comments:
        db.add(c)
    await db.commit()
    print(f"Seeded {len(comments)} exception comments.")


async def seed_comparisons(db: AsyncSession, positions: list[Position]) -> None:
    """Insert valuation comparison history records."""
    for pos in positions:
        if pos.desk_mark is not None and pos.vc_fair_value is not None:
            comp = ValuationComparison(
                position_id=pos.position_id,
                desk_mark=pos.desk_mark,
                vc_fair_value=pos.vc_fair_value,
                difference=pos.difference,
                difference_pct=pos.difference_pct,
                status=pos.exception_status or "GREEN",
                comparison_date=VALUATION_DATE,
            )
            db.add(comp)

    await db.commit()
    print(f"Seeded {len(positions)} valuation comparisons.")


async def seed_committee_agenda(db: AsyncSession, exceptions: list[VCException]) -> None:
    """Create committee agenda item for the barrier option exception."""
    barrier_exc = exceptions[2]  # Barrier option RED exception

    agenda = CommitteeAgendaItem(
        exception_id=barrier_exc.exception_id,
        position_id=barrier_exc.position_id,
        difference=barrier_exc.difference,
        status="PENDING_COMMITTEE",
        meeting_date=date(2025, 2, 19),  # Next Wednesday after 14-Feb
    )
    db.add(agenda)
    await db.commit()
    print("Seeded committee agenda item for barrier option.")


async def main() -> None:
    print("=" * 60)
    print("FX IPV MODEL — SEED DATA")
    print("Valuation Date: 14-Feb-2025")
    print("=" * 60)

    await create_tables()

    async with async_session_factory() as db:
        await clear_all_tables(db)

        positions = await seed_positions(db)
        barrier_pos = [p for p in positions if p.trade_id == "FX-OPT-001"][0]
        await seed_barrier_detail(db, barrier_pos)
        await seed_market_data(db)
        await seed_dealer_quotes(db, positions)
        exceptions = await seed_exceptions(db, positions)
        await seed_exception_comments(db, exceptions)
        await seed_comparisons(db, positions)
        await seed_committee_agenda(db, exceptions)

    print("=" * 60)
    print("Seed complete. 7 FX positions loaded from IPV_FX_Model.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
