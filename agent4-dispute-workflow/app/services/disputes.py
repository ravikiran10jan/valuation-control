"""Dispute workflow service with state machine, CRUD, and audit trail."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import structlog

from app.models.postgres import Dispute, DisputeMessage
from app.models.schemas import (
    DeskResponse,
    DisputeCreate,
    DisputeResolve,
    DisputeUpdate,
)

log = structlog.get_logger()

# ── Valid state transitions ───────────────────────────────────────
TRANSITIONS = {
    "INITIATED":          {"DESK_REVIEWING", "ESCALATED"},
    "DESK_REVIEWING":     {"DESK_RESPONDED", "ESCALATED"},
    "DESK_RESPONDED":     {"VC_REVIEWING", "ESCALATED"},
    "VC_REVIEWING":       {"NEGOTIATING", "RESOLVED_VC_WIN", "RESOLVED_DESK_WIN", "RESOLVED_COMPROMISE", "ESCALATED"},
    "NEGOTIATING":        {"RESOLVED_VC_WIN", "RESOLVED_DESK_WIN", "RESOLVED_COMPROMISE", "ESCALATED"},
    "ESCALATED":          {"RESOLVED_VC_WIN", "RESOLVED_DESK_WIN", "RESOLVED_COMPROMISE"},
    "RESOLVED_VC_WIN":    set(),
    "RESOLVED_DESK_WIN":  set(),
    "RESOLVED_COMPROMISE": set(),
}

RESOLVED_STATES = {"RESOLVED_VC_WIN", "RESOLVED_DESK_WIN", "RESOLVED_COMPROMISE"}


def _is_valid_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def _append_audit(dispute: Dispute, action: str, actor: str, detail: str = "") -> None:
    trail = list(dispute.audit_trail or [])
    trail.append({
        "action": action,
        "actor": actor,
        "detail": detail,
        "timestamp": datetime.utcnow().isoformat(),
        "from_state": dispute.state,
    })
    dispute.audit_trail = trail


# ── CRUD ──────────────────────────────────────────────────────────
async def create_dispute(db: AsyncSession, data: DisputeCreate) -> Dispute:
    difference = None
    difference_pct = None
    if data.desk_mark is not None and data.vc_fair_value is not None:
        difference = data.desk_mark - data.vc_fair_value
        if data.vc_fair_value != 0:
            difference_pct = (difference / abs(data.vc_fair_value)) * 100

    dispute = Dispute(
        exception_id=data.exception_id,
        position_id=data.position_id,
        state="INITIATED",
        vc_position=data.vc_position,
        vc_analyst=data.vc_analyst,
        desk_trader=data.desk_trader,
        desk_mark=data.desk_mark,
        vc_fair_value=data.vc_fair_value,
        difference=difference,
        difference_pct=difference_pct,
        audit_trail=[{
            "action": "CREATED",
            "actor": data.vc_analyst,
            "detail": "Dispute initiated by VC analyst",
            "timestamp": datetime.utcnow().isoformat(),
            "from_state": None,
        }],
    )

    db.add(dispute)
    await db.commit()
    await db.refresh(dispute)
    log.info(
        "dispute_created",
        dispute_id=dispute.dispute_id,
        exception_id=data.exception_id,
    )
    return dispute


async def get_dispute(db: AsyncSession, dispute_id: int) -> Optional[Dispute]:
    return await db.get(Dispute, dispute_id)


async def get_dispute_detail(db: AsyncSession, dispute_id: int) -> Optional[Dispute]:
    result = await db.execute(
        select(Dispute)
        .options(
            selectinload(Dispute.messages),
            selectinload(Dispute.approvals),
            selectinload(Dispute.attachments),
        )
        .where(Dispute.dispute_id == dispute_id)
    )
    return result.scalar_one_or_none()


async def list_disputes(
    db: AsyncSession,
    state: Optional[str] = None,
    exception_id: Optional[int] = None,
    vc_analyst: Optional[str] = None,
    desk_trader: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Dispute]:
    stmt = select(Dispute)
    if state:
        stmt = stmt.where(Dispute.state == state)
    if exception_id:
        stmt = stmt.where(Dispute.exception_id == exception_id)
    if vc_analyst:
        stmt = stmt.where(Dispute.vc_analyst == vc_analyst)
    if desk_trader:
        stmt = stmt.where(Dispute.desk_trader == desk_trader)
    stmt = stmt.order_by(Dispute.created_date.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_dispute(
    db: AsyncSession, dispute_id: int, data: DisputeUpdate
) -> Optional[Dispute]:
    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(dispute, field, value)
    await db.commit()
    await db.refresh(dispute)
    log.info("dispute_updated", dispute_id=dispute_id)
    return dispute


async def get_dispute_summary(db: AsyncSession) -> dict:
    total = await db.scalar(select(func.count(Dispute.dispute_id)))
    initiated = await db.scalar(
        select(func.count(Dispute.dispute_id)).where(Dispute.state == "INITIATED")
    )
    in_progress_states = {
        "DESK_REVIEWING", "DESK_RESPONDED", "VC_REVIEWING", "NEGOTIATING",
    }
    in_progress = await db.scalar(
        select(func.count(Dispute.dispute_id)).where(Dispute.state.in_(in_progress_states))
    )
    escalated = await db.scalar(
        select(func.count(Dispute.dispute_id)).where(Dispute.state == "ESCALATED")
    )
    resolved = await db.scalar(
        select(func.count(Dispute.dispute_id)).where(Dispute.state.in_(RESOLVED_STATES))
    )

    # Use julianday for SQLite compat, extract(epoch ...) for PostgreSQL.
    # At runtime we detect the dialect; for tests (SQLite) we use julianday.
    try:
        avg_days_q = await db.execute(
            select(
                func.avg(
                    func.julianday(Dispute.resolved_date) - func.julianday(Dispute.created_date)
                )
            ).where(Dispute.resolved_date.isnot(None))
        )
        avg_days = avg_days_q.scalar() or 0.0
    except Exception:
        avg_days = 0.0

    return {
        "total_disputes": total or 0,
        "initiated": initiated or 0,
        "in_progress": (in_progress or 0),
        "escalated": escalated or 0,
        "resolved": resolved or 0,
        "avg_days_to_resolve": round(float(avg_days), 1),
    }


# ── State transitions ────────────────────────────────────────────
async def transition_state(
    db: AsyncSession,
    dispute_id: int,
    new_state: str,
    actor: str,
    reason: str = "",
) -> Dispute:
    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        raise ValueError(f"Dispute {dispute_id} not found")

    if not _is_valid_transition(dispute.state, new_state):
        raise ValueError(
            f"Invalid transition from {dispute.state} to {new_state}"
        )

    old_state = dispute.state
    _append_audit(dispute, f"STATE_CHANGE:{old_state}->{new_state}", actor, reason)
    dispute.state = new_state

    if new_state in RESOLVED_STATES:
        dispute.resolved_date = datetime.utcnow()
        dispute.resolution_type = new_state.replace("RESOLVED_", "")

    await db.commit()
    await db.refresh(dispute)
    log.info(
        "dispute_state_changed",
        dispute_id=dispute_id,
        from_state=old_state,
        to_state=new_state,
        actor=actor,
    )
    return dispute


async def desk_respond(
    db: AsyncSession, dispute_id: int, data: DeskResponse
) -> Dispute:
    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        raise ValueError(f"Dispute {dispute_id} not found")

    if dispute.state not in ("DESK_REVIEWING",):
        raise ValueError(
            f"Desk can only respond when state is DESK_REVIEWING, "
            f"current state is {dispute.state}"
        )

    dispute.desk_position = data.desk_position
    dispute.desk_trader = data.desk_trader
    _append_audit(dispute, "DESK_RESPONDED", data.desk_trader, data.desk_position[:200])
    dispute.state = "DESK_RESPONDED"

    # Add the response as a message
    msg = DisputeMessage(
        dispute_id=dispute_id,
        sender=data.desk_trader,
        sender_role="DESK",
        message_text=data.desk_position,
        source="platform",
    )
    db.add(msg)

    await db.commit()
    await db.refresh(dispute)
    log.info("desk_responded", dispute_id=dispute_id, trader=data.desk_trader)
    return dispute


async def resolve_dispute(
    db: AsyncSession, dispute_id: int, data: DisputeResolve
) -> Dispute:
    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        raise ValueError(f"Dispute {dispute_id} not found")

    target_state = f"RESOLVED_{data.resolution_type}"
    if not _is_valid_transition(dispute.state, target_state):
        raise ValueError(
            f"Cannot resolve from state {dispute.state}"
        )

    old_state = dispute.state
    _append_audit(
        dispute,
        f"RESOLVED:{data.resolution_type}",
        data.actor,
        data.notes or f"Final mark: {data.final_mark}",
    )

    dispute.state = target_state
    dispute.resolution_type = data.resolution_type
    dispute.final_mark = data.final_mark
    dispute.resolved_date = datetime.utcnow()

    await db.commit()
    await db.refresh(dispute)
    log.info(
        "dispute_resolved",
        dispute_id=dispute_id,
        resolution=data.resolution_type,
        final_mark=str(data.final_mark),
        from_state=old_state,
    )
    return dispute
