"""Tests for the dispute workflow service — state machine, CRUD, audit trail."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.schemas import (
    DeskResponse,
    DisputeCreate,
    DisputeResolve,
    DisputeUpdate,
)
from app.services.disputes import (
    RESOLVED_STATES,
    TRANSITIONS,
    _is_valid_transition,
    create_dispute,
    desk_respond,
    get_dispute,
    get_dispute_detail,
    get_dispute_summary,
    list_disputes,
    resolve_dispute,
    transition_state,
    update_dispute,
)


# ── State machine unit tests ─────────────────────────────────────
class TestStateMachine:
    def test_valid_transitions_from_initiated(self):
        assert _is_valid_transition("INITIATED", "DESK_REVIEWING")
        assert _is_valid_transition("INITIATED", "ESCALATED")

    def test_invalid_transitions_from_initiated(self):
        assert not _is_valid_transition("INITIATED", "RESOLVED_VC_WIN")
        assert not _is_valid_transition("INITIATED", "NEGOTIATING")

    def test_resolved_states_are_terminal(self):
        for state in RESOLVED_STATES:
            assert TRANSITIONS[state] == set()
            assert not _is_valid_transition(state, "INITIATED")

    def test_escalated_can_resolve(self):
        assert _is_valid_transition("ESCALATED", "RESOLVED_VC_WIN")
        assert _is_valid_transition("ESCALATED", "RESOLVED_DESK_WIN")
        assert _is_valid_transition("ESCALATED", "RESOLVED_COMPROMISE")

    def test_vc_reviewing_transitions(self):
        assert _is_valid_transition("VC_REVIEWING", "NEGOTIATING")
        assert _is_valid_transition("VC_REVIEWING", "RESOLVED_VC_WIN")
        assert _is_valid_transition("VC_REVIEWING", "ESCALATED")


# ── CRUD tests (async, with in-memory DB) ─────────────────────────
@pytest.mark.asyncio
class TestDisputeCRUD:
    async def test_create_dispute(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        dispute = await create_dispute(db, data)

        assert dispute.dispute_id is not None
        assert dispute.state == "INITIATED"
        assert dispute.exception_id == 1
        assert dispute.vc_analyst == "vc_analyst@bank.com"
        assert dispute.difference == Decimal("119000.00")
        assert dispute.audit_trail is not None
        assert len(dispute.audit_trail) == 1
        assert dispute.audit_trail[0]["action"] == "CREATED"

    async def test_get_dispute(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        created = await create_dispute(db, data)
        fetched = await get_dispute(db, created.dispute_id)

        assert fetched is not None
        assert fetched.dispute_id == created.dispute_id

    async def test_get_nonexistent_dispute(self, db):
        result = await get_dispute(db, 999999)
        assert result is None

    async def test_list_disputes_no_filter(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        await create_dispute(db, data)
        disputes = await list_disputes(db)
        assert len(disputes) >= 1

    async def test_list_disputes_filter_by_state(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        await create_dispute(db, data)
        disputes = await list_disputes(db, state="INITIATED")
        assert all(d.state == "INITIATED" for d in disputes)

    async def test_update_dispute(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        dispute = await create_dispute(db, data)
        updated = await update_dispute(
            db, dispute.dispute_id, DisputeUpdate(desk_position="Counter-argument")
        )
        assert updated.desk_position == "Counter-argument"

    async def test_dispute_summary(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        await create_dispute(db, data)
        summary = await get_dispute_summary(db)
        assert summary["total_disputes"] >= 1
        assert summary["initiated"] >= 1


# ── Workflow transition tests ─────────────────────────────────────
@pytest.mark.asyncio
class TestDisputeWorkflow:
    async def test_transition_to_desk_reviewing(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        dispute = await create_dispute(db, data)

        dispute = await transition_state(
            db, dispute.dispute_id, "DESK_REVIEWING", "vc_analyst@bank.com"
        )
        assert dispute.state == "DESK_REVIEWING"
        assert len(dispute.audit_trail) == 2

    async def test_invalid_transition_raises(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        dispute = await create_dispute(db, data)

        with pytest.raises(ValueError, match="Invalid transition"):
            await transition_state(
                db, dispute.dispute_id, "RESOLVED_VC_WIN", "vc_analyst@bank.com"
            )

    async def test_nonexistent_dispute_raises(self, db):
        with pytest.raises(ValueError, match="not found"):
            await transition_state(db, 999999, "DESK_REVIEWING", "vc@bank.com")

    async def test_desk_respond(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        dispute = await create_dispute(db, data)
        dispute = await transition_state(
            db, dispute.dispute_id, "DESK_REVIEWING", "vc_analyst@bank.com"
        )

        response = DeskResponse(
            desk_position="Our mark reflects client-specific vol surface",
            desk_trader="fx_trader@bank.com",
            proposed_mark=Decimal("380000.00"),
        )
        dispute = await desk_respond(db, dispute.dispute_id, response)

        assert dispute.state == "DESK_RESPONDED"
        assert dispute.desk_position is not None
        assert "vol surface" in dispute.desk_position

    async def test_desk_respond_wrong_state_raises(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        dispute = await create_dispute(db, data)

        with pytest.raises(ValueError, match="DESK_REVIEWING"):
            await desk_respond(
                db,
                dispute.dispute_id,
                DeskResponse(
                    desk_position="test",
                    desk_trader="trader@bank.com",
                ),
            )

    async def test_full_workflow_to_resolution(self, db, sample_dispute_data):
        """End-to-end: INITIATED -> DESK_REVIEWING -> DESK_RESPONDED
        -> VC_REVIEWING -> RESOLVED_COMPROMISE"""
        data = DisputeCreate(**sample_dispute_data)
        dispute = await create_dispute(db, data)

        # VC sends to desk
        dispute = await transition_state(
            db, dispute.dispute_id, "DESK_REVIEWING", "vc_analyst@bank.com"
        )

        # Desk responds
        dispute = await desk_respond(
            db,
            dispute.dispute_id,
            DeskResponse(
                desk_position="We use different vol surface",
                desk_trader="fx_trader@bank.com",
            ),
        )

        # VC reviews
        dispute = await transition_state(
            db, dispute.dispute_id, "VC_REVIEWING", "vc_analyst@bank.com"
        )

        # Resolve as compromise
        dispute = await resolve_dispute(
            db,
            dispute.dispute_id,
            DisputeResolve(
                resolution_type="COMPROMISE",
                final_mark=Decimal("365000.00"),
                actor="vc_analyst@bank.com",
                notes="Met in the middle after vol surface review",
            ),
        )

        assert dispute.state == "RESOLVED_COMPROMISE"
        assert dispute.final_mark == Decimal("365000.00")
        assert dispute.resolution_type == "COMPROMISE"
        assert dispute.resolved_date is not None

    async def test_escalation_workflow(self, db, sample_dispute_data):
        data = DisputeCreate(**sample_dispute_data)
        dispute = await create_dispute(db, data)

        dispute = await transition_state(
            db, dispute.dispute_id, "ESCALATED", "vc_analyst@bank.com", "No agreement"
        )
        assert dispute.state == "ESCALATED"

        dispute = await resolve_dispute(
            db,
            dispute.dispute_id,
            DisputeResolve(
                resolution_type="VC_WIN",
                final_mark=Decimal("306000.00"),
                actor="committee@bank.com",
                notes="Committee agreed with VC model",
            ),
        )
        assert dispute.state == "RESOLVED_VC_WIN"
