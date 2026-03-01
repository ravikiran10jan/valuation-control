"""Tests for the FastAPI dispute endpoints."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import Base, get_db
from app.main import app

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


SAMPLE_DISPUTE = {
    "exception_id": 1,
    "position_id": 100,
    "vc_position": "VC model shows fair value of 306,000",
    "vc_analyst": "vc_analyst@bank.com",
    "desk_trader": "fx_trader@bank.com",
    "desk_mark": "425000.00",
    "vc_fair_value": "306000.00",
}


@pytest.mark.asyncio
class TestDisputeAPI:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "agent4-dispute-workflow"

    async def test_create_dispute(self, client):
        resp = await client.post("/disputes/", json=SAMPLE_DISPUTE)
        assert resp.status_code == 201
        data = resp.json()
        assert data["state"] == "DESK_REVIEWING"  # auto-transition since desk_trader given
        assert data["vc_analyst"] == "vc_analyst@bank.com"

    async def test_list_disputes(self, client):
        await client.post("/disputes/", json=SAMPLE_DISPUTE)
        resp = await client.get("/disputes/")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_get_dispute_detail(self, client):
        create_resp = await client.post("/disputes/", json=SAMPLE_DISPUTE)
        dispute_id = create_resp.json()["dispute_id"]

        resp = await client.get(f"/disputes/{dispute_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert "approvals" in data
        assert "attachments" in data

    async def test_get_nonexistent_dispute(self, client):
        resp = await client.get("/disputes/999999")
        assert resp.status_code == 404

    async def test_desk_respond(self, client):
        create_resp = await client.post("/disputes/", json=SAMPLE_DISPUTE)
        dispute_id = create_resp.json()["dispute_id"]

        resp = await client.post(
            f"/disputes/{dispute_id}/desk-respond",
            json={
                "desk_position": "Our mark reflects client-specific vol",
                "desk_trader": "fx_trader@bank.com",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "DESK_RESPONDED"

    async def test_resolve_dispute(self, client):
        create_resp = await client.post("/disputes/", json=SAMPLE_DISPUTE)
        dispute_id = create_resp.json()["dispute_id"]

        # desk respond
        await client.post(
            f"/disputes/{dispute_id}/desk-respond",
            json={
                "desk_position": "Counter-argument",
                "desk_trader": "fx_trader@bank.com",
            },
        )

        # transition to VC reviewing
        await client.post(
            f"/disputes/{dispute_id}/transition",
            json={
                "new_state": "VC_REVIEWING",
                "actor": "vc_analyst@bank.com",
            },
        )

        # resolve
        resp = await client.post(
            f"/disputes/{dispute_id}/resolve",
            json={
                "resolution_type": "COMPROMISE",
                "final_mark": "365000.00",
                "actor": "vc_analyst@bank.com",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "RESOLVED_COMPROMISE"

    async def test_dispute_summary(self, client):
        await client.post("/disputes/", json=SAMPLE_DISPUTE)
        resp = await client.get("/disputes/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_disputes" in data

    async def test_post_message(self, client):
        create_resp = await client.post("/disputes/", json=SAMPLE_DISPUTE)
        dispute_id = create_resp.json()["dispute_id"]

        resp = await client.post(
            f"/disputes/{dispute_id}/messages/",
            json={
                "sender": "vc_analyst@bank.com",
                "sender_role": "VC",
                "message_text": "Attaching updated MC model output",
            },
        )
        assert resp.status_code == 201

    async def test_list_messages(self, client):
        create_resp = await client.post("/disputes/", json=SAMPLE_DISPUTE)
        dispute_id = create_resp.json()["dispute_id"]

        await client.post(
            f"/disputes/{dispute_id}/messages/",
            json={
                "sender": "vc_analyst@bank.com",
                "sender_role": "VC",
                "message_text": "First message",
            },
        )
        resp = await client.get(f"/disputes/{dispute_id}/messages/")
        assert resp.status_code == 200

    async def test_request_approval(self, client):
        create_resp = await client.post("/disputes/", json=SAMPLE_DISPUTE)
        dispute_id = create_resp.json()["dispute_id"]

        resp = await client.post(
            f"/disputes/{dispute_id}/approvals/",
            json={
                "requested_by": "fx_trader@bank.com",
                "old_mark": "425000.00",
                "new_mark": "380000.00",
                "justification": "Vol surface recalibration",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "PENDING"

    async def test_decide_approval(self, client):
        create_resp = await client.post("/disputes/", json=SAMPLE_DISPUTE)
        dispute_id = create_resp.json()["dispute_id"]

        approval_resp = await client.post(
            f"/disputes/{dispute_id}/approvals/",
            json={
                "requested_by": "fx_trader@bank.com",
                "old_mark": "425000.00",
                "new_mark": "380000.00",
                "justification": "Vol surface recalibration",
            },
        )
        approval_id = approval_resp.json()["approval_id"]

        resp = await client.post(
            f"/disputes/{dispute_id}/approvals/{approval_id}/decide",
            json={
                "approver": "vc.manager@bank.com",
                "decision": "APPROVED",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "APPROVED"
