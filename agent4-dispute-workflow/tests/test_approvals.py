"""Tests for approval workflow and message thread services."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.schemas import (
    DisputeApprovalCreate,
    DisputeApprovalDecision,
    DisputeCreate,
)
from app.services.approvals import ApprovalWorkflow, add_message, list_messages
from app.services.disputes import create_dispute, transition_state


@pytest.mark.asyncio
class TestMessages:
    async def test_add_and_list_messages(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        dispute = await create_dispute(db, data)

        msg = await add_message(
            db,
            dispute.dispute_id,
            sender="vc_analyst@bank.com",
            sender_role="VC",
            message_text="Attaching updated MC model output",
        )
        assert msg.message_id is not None
        assert msg.sender_role == "VC"

        msgs = await list_messages(db, dispute.dispute_id)
        assert len(msgs) >= 1

    async def test_add_message_nonexistent_dispute(self, db):
        with pytest.raises(ValueError, match="not found"):
            await add_message(db, 999999, "a@b.com", "VC", "test")

    async def test_message_updates_audit_trail(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        dispute = await create_dispute(db, data)

        await add_message(
            db,
            dispute.dispute_id,
            sender="vc_analyst@bank.com",
            sender_role="VC",
            message_text="Adding evidence",
        )

        from app.services.disputes import get_dispute

        updated = await get_dispute(db, dispute.dispute_id)
        assert len(updated.audit_trail) == 2  # CREATED + MESSAGE_ADDED


@pytest.mark.asyncio
class TestApprovalWorkflow:
    async def _create_dispute_for_approval(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        dispute = await create_dispute(db, data)
        return dispute

    async def test_request_mark_adjustment(self, db, sample_dispute_data):
        dispute = await self._create_dispute_for_approval(db, sample_dispute_data)
        workflow = ApprovalWorkflow()

        approval = await workflow.request_mark_adjustment(
            db,
            dispute.dispute_id,
            DisputeApprovalCreate(
                requested_by="fx_trader@bank.com",
                old_mark=Decimal("425000.00"),
                new_mark=Decimal("380000.00"),
                justification="Adjusted after vol surface recalibration",
            ),
        )
        assert approval.approval_id is not None
        assert approval.status == "PENDING"
        assert approval.new_mark == Decimal("380000.00")

    async def test_approve_adjustment(self, db, sample_dispute_data):
        dispute = await self._create_dispute_for_approval(db, sample_dispute_data)
        workflow = ApprovalWorkflow()

        approval = await workflow.request_mark_adjustment(
            db,
            dispute.dispute_id,
            DisputeApprovalCreate(
                requested_by="fx_trader@bank.com",
                old_mark=Decimal("425000.00"),
                new_mark=Decimal("380000.00"),
                justification="Vol surface recalibration",
            ),
        )

        decided = await workflow.decide_approval(
            db,
            approval.approval_id,
            DisputeApprovalDecision(
                approver="vc.manager@bank.com", decision="APPROVED"
            ),
        )
        assert decided.status == "APPROVED"
        assert decided.approved_by == "vc.manager@bank.com"
        assert decided.approved_date is not None

    async def test_reject_adjustment(self, db, sample_dispute_data):
        dispute = await self._create_dispute_for_approval(db, sample_dispute_data)
        workflow = ApprovalWorkflow()

        approval = await workflow.request_mark_adjustment(
            db,
            dispute.dispute_id,
            DisputeApprovalCreate(
                requested_by="fx_trader@bank.com",
                old_mark=Decimal("425000.00"),
                new_mark=Decimal("380000.00"),
                justification="Vol surface recalibration",
            ),
        )

        decided = await workflow.decide_approval(
            db,
            approval.approval_id,
            DisputeApprovalDecision(
                approver="vc.manager@bank.com", decision="REJECTED"
            ),
        )
        assert decided.status == "REJECTED"

    async def test_double_decide_raises(self, db, sample_dispute_data):
        dispute = await self._create_dispute_for_approval(db, sample_dispute_data)
        workflow = ApprovalWorkflow()

        approval = await workflow.request_mark_adjustment(
            db,
            dispute.dispute_id,
            DisputeApprovalCreate(
                requested_by="fx_trader@bank.com",
                old_mark=Decimal("425000.00"),
                new_mark=Decimal("380000.00"),
                justification="Vol surface recalibration",
            ),
        )

        await workflow.decide_approval(
            db,
            approval.approval_id,
            DisputeApprovalDecision(
                approver="vc.manager@bank.com", decision="APPROVED"
            ),
        )

        with pytest.raises(ValueError, match="already decided"):
            await workflow.decide_approval(
                db,
                approval.approval_id,
                DisputeApprovalDecision(
                    approver="other.manager@bank.com", decision="REJECTED"
                ),
            )

    async def test_list_approvals(self, db, sample_dispute_data):
        dispute = await self._create_dispute_for_approval(db, sample_dispute_data)
        workflow = ApprovalWorkflow()

        await workflow.request_mark_adjustment(
            db,
            dispute.dispute_id,
            DisputeApprovalCreate(
                requested_by="fx_trader@bank.com",
                old_mark=Decimal("425000.00"),
                new_mark=Decimal("380000.00"),
                justification="Vol surface recalibration",
            ),
        )

        approvals = await workflow.list_approvals(db, dispute_id=dispute.dispute_id)
        assert len(approvals) == 1

    async def test_nonexistent_dispute_raises(self, db):
        workflow = ApprovalWorkflow()
        with pytest.raises(ValueError, match="not found"):
            await workflow.request_mark_adjustment(
                db,
                999999,
                DisputeApprovalCreate(
                    requested_by="a@b.com",
                    old_mark=Decimal("100"),
                    new_mark=Decimal("90"),
                    justification="test",
                ),
            )
