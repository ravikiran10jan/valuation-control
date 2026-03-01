"""Approval workflow service for mark adjustments."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.models.postgres import Dispute, DisputeApproval
from app.models.schemas import DisputeApprovalCreate, DisputeApprovalDecision
from app.services.email_integration import EmailIntegration

log = structlog.get_logger()


class ApprovalWorkflow:
    """Manages the approval lifecycle for mark adjustment requests."""

    def __init__(self) -> None:
        self._email = EmailIntegration()

    async def request_mark_adjustment(
        self,
        db: AsyncSession,
        dispute_id: int,
        data: DisputeApprovalCreate,
    ) -> DisputeApproval:
        dispute = await db.get(Dispute, dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")

        approval = DisputeApproval(
            dispute_id=dispute_id,
            requested_by=data.requested_by,
            old_mark=data.old_mark,
            new_mark=data.new_mark,
            justification=data.justification,
            status="PENDING",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        # Send notification to approvers
        dispute_dict = {
            "dispute_id": dispute.dispute_id,
            "position_id": dispute.position_id,
        }
        approval_dict = {
            "requested_by": data.requested_by,
            "old_mark": str(data.old_mark),
            "new_mark": str(data.new_mark),
            "justification": data.justification,
        }

        from app.core.config import settings

        await self._email.notify_approval_request(
            approval_dict, dispute_dict, settings.vc_manager_email
        )

        log.info(
            "mark_adjustment_requested",
            dispute_id=dispute_id,
            approval_id=approval.approval_id,
            requested_by=data.requested_by,
        )
        return approval

    async def decide_approval(
        self,
        db: AsyncSession,
        approval_id: int,
        data: DisputeApprovalDecision,
    ) -> DisputeApproval:
        approval = await db.get(DisputeApproval, approval_id)
        if approval is None:
            raise ValueError(f"Approval {approval_id} not found")

        if approval.status != "PENDING":
            raise ValueError(
                f"Approval {approval_id} already decided: {approval.status}"
            )

        approval.approved_by = data.approver
        approval.status = data.decision
        approval.approved_date = datetime.utcnow()

        if data.decision == "APPROVED":
            # Update the dispute final mark
            dispute = await db.get(Dispute, approval.dispute_id)
            if dispute:
                dispute.final_mark = approval.new_mark
                trail = list(dispute.audit_trail or [])
                trail.append({
                    "action": "MARK_ADJUSTED",
                    "actor": data.approver,
                    "detail": f"Mark adjusted from {approval.old_mark} to {approval.new_mark}",
                    "timestamp": datetime.utcnow().isoformat(),
                    "from_state": dispute.state,
                })
                dispute.audit_trail = trail

        await db.commit()
        await db.refresh(approval)

        log.info(
            "approval_decided",
            approval_id=approval_id,
            decision=data.decision,
            approver=data.approver,
        )
        return approval

    async def list_approvals(
        self,
        db: AsyncSession,
        dispute_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[DisputeApproval]:
        stmt = select(DisputeApproval)
        if dispute_id is not None:
            stmt = stmt.where(DisputeApproval.dispute_id == dispute_id)
        if status:
            stmt = stmt.where(DisputeApproval.status == status)
        stmt = stmt.order_by(DisputeApproval.requested_date.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_approval(
        self, db: AsyncSession, approval_id: int
    ) -> Optional[DisputeApproval]:
        return await db.get(DisputeApproval, approval_id)


async def add_message(
    db: AsyncSession,
    dispute_id: int,
    sender: str,
    sender_role: str,
    message_text: str,
    attachments: Optional[dict] = None,
    source: str = "platform",
):
    """Add a message to a dispute conversation thread."""
    from app.models.postgres import DisputeMessage

    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        raise ValueError(f"Dispute {dispute_id} not found")

    msg = DisputeMessage(
        dispute_id=dispute_id,
        sender=sender,
        sender_role=sender_role,
        message_text=message_text,
        attachments=attachments,
        source=source,
    )
    db.add(msg)

    trail = list(dispute.audit_trail or [])
    trail.append({
        "action": "MESSAGE_ADDED",
        "actor": sender,
        "detail": message_text[:200],
        "timestamp": datetime.utcnow().isoformat(),
        "from_state": dispute.state,
    })
    dispute.audit_trail = trail

    await db.commit()
    await db.refresh(msg)
    log.info("message_added", dispute_id=dispute_id, sender=sender)
    return msg


async def list_messages(
    db: AsyncSession, dispute_id: int
):
    """List all messages for a dispute ordered by timestamp."""
    from app.models.postgres import DisputeMessage

    result = await db.execute(
        select(DisputeMessage)
        .where(DisputeMessage.dispute_id == dispute_id)
        .order_by(DisputeMessage.timestamp.asc())
    )
    return list(result.scalars().all())
