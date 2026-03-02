"""Disputes routes — proxy to Agent 4 (Dispute Workflow).

Provides full dispute management workflow including creation, state transitions,
messages, approvals, and document handling.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from app.services.upstream import agent4_get, agent4_post, get_client
from app.core.config import settings

router = APIRouter(prefix="/api/disputes", tags=["Disputes"])


# ── List & Summary ──────────────────────────────────────────────


@router.get("/")
async def list_disputes(
    state: Optional[str] = None,
    exception_id: Optional[int] = None,
    vc_analyst: Optional[str] = None,
    desk_trader: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List disputes with optional filters.

    Proxies to Agent 4 GET /disputes/.
    """
    params = {}
    if state:
        params["state"] = state
    if exception_id:
        params["exception_id"] = exception_id
    if vc_analyst:
        params["vc_analyst"] = vc_analyst
    if desk_trader:
        params["desk_trader"] = desk_trader
    params["skip"] = skip
    params["limit"] = limit

    try:
        return await agent4_get("/disputes/", params=params)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Dispute service unavailable: {exc}")


@router.get("/summary")
async def get_dispute_summary() -> dict[str, Any]:
    """Get aggregate dispute statistics.

    Proxies to Agent 4 GET /disputes/summary.
    """
    try:
        return await agent4_get("/disputes/summary")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch summary: {exc}")


# ── Single Dispute ──────────────────────────────────────────────


@router.get("/{dispute_id}")
async def get_dispute(dispute_id: int) -> dict[str, Any]:
    """Get full dispute detail including messages, approvals, attachments.

    Proxies to Agent 4 GET /disputes/{dispute_id}.
    """
    try:
        return await agent4_get(f"/disputes/{dispute_id}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch dispute {dispute_id}: {exc}")


# ── Create Dispute ──────────────────────────────────────────────


class DisputeCreate(BaseModel):
    exception_id: int
    position_id: int
    vc_analyst: str
    desk_trader: str
    vc_fair_value: float
    desk_mark: float
    difference_pct: float
    reason: Optional[str] = None


@router.post("/")
async def create_dispute(data: DisputeCreate) -> dict[str, Any]:
    """Create a new dispute.

    Proxies to Agent 4 POST /disputes/.
    """
    try:
        return await agent4_post("/disputes/", json=data.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to create dispute: {exc}")


# ── State Transitions ───────────────────────────────────────────


class TransitionRequest(BaseModel):
    new_state: str
    actor: str
    reason: Optional[str] = None


@router.post("/{dispute_id}/transition")
async def transition_dispute(dispute_id: int, data: TransitionRequest) -> dict[str, Any]:
    """Manually transition dispute to a new state.

    Proxies to Agent 4 POST /disputes/{dispute_id}/transition.
    """
    try:
        return await agent4_post(f"/disputes/{dispute_id}/transition", json=data.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to transition dispute: {exc}")


class DeskResponse(BaseModel):
    desk_trader: str
    response_text: str
    proposed_mark: Optional[float] = None
    supporting_evidence: Optional[str] = None


@router.post("/{dispute_id}/desk-respond")
async def desk_respond(dispute_id: int, data: DeskResponse) -> dict[str, Any]:
    """Desk trader responds to dispute.

    Proxies to Agent 4 POST /disputes/{dispute_id}/desk-respond.
    """
    try:
        return await agent4_post(f"/disputes/{dispute_id}/desk-respond", json=data.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to submit desk response: {exc}")


class DisputeResolve(BaseModel):
    resolved_by: str
    resolution_type: str  # VC_WIN, DESK_WIN, COMPROMISE
    final_mark: float
    resolution_notes: Optional[str] = None


@router.post("/{dispute_id}/resolve")
async def resolve_dispute(dispute_id: int, data: DisputeResolve) -> dict[str, Any]:
    """Resolve dispute with final mark.

    Proxies to Agent 4 POST /disputes/{dispute_id}/resolve.
    """
    try:
        return await agent4_post(f"/disputes/{dispute_id}/resolve", json=data.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to resolve dispute: {exc}")


# ── Messages ────────────────────────────────────────────────────


@router.get("/{dispute_id}/messages/")
async def list_messages(dispute_id: int) -> list[dict[str, Any]]:
    """List all messages in dispute thread.

    Proxies to Agent 4 GET /disputes/{dispute_id}/messages/.
    """
    try:
        return await agent4_get(f"/disputes/{dispute_id}/messages/")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch messages: {exc}")


class MessageCreate(BaseModel):
    sender: str
    role: str  # VC_ANALYST, DESK_TRADER, MANAGER, SYSTEM
    message_text: str
    source: str = "platform"  # platform, email
    attachments: Optional[list[str]] = None


@router.post("/{dispute_id}/messages/")
async def add_message(dispute_id: int, data: MessageCreate) -> dict[str, Any]:
    """Add message to dispute thread.

    Proxies to Agent 4 POST /disputes/{dispute_id}/messages/.
    """
    try:
        return await agent4_post(f"/disputes/{dispute_id}/messages/", json=data.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to add message: {exc}")


# ── Approvals ───────────────────────────────────────────────────


@router.get("/{dispute_id}/approvals/")
async def list_approvals(
    dispute_id: int,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List approval requests for a dispute.

    Proxies to Agent 4 GET /disputes/{dispute_id}/approvals/.
    """
    params = {}
    if status:
        params["status"] = status
    try:
        return await agent4_get(f"/disputes/{dispute_id}/approvals/", params=params)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch approvals: {exc}")


class ApprovalCreate(BaseModel):
    requested_by: str
    approver: str
    adjustment_amount: float
    justification: str


@router.post("/{dispute_id}/approvals/")
async def request_approval(dispute_id: int, data: ApprovalCreate) -> dict[str, Any]:
    """Request mark adjustment approval.

    Proxies to Agent 4 POST /disputes/{dispute_id}/approvals/.
    """
    try:
        return await agent4_post(f"/disputes/{dispute_id}/approvals/", json=data.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to request approval: {exc}")


class ApprovalDecision(BaseModel):
    decision: str  # APPROVED, REJECTED
    comments: Optional[str] = None


@router.post("/{dispute_id}/approvals/{approval_id}/decide")
async def decide_approval(
    dispute_id: int,
    approval_id: int,
    data: ApprovalDecision,
) -> dict[str, Any]:
    """Approve or reject a mark adjustment request.

    Proxies to Agent 4 POST /disputes/{dispute_id}/approvals/{approval_id}/decide.
    """
    try:
        return await agent4_post(
            f"/disputes/{dispute_id}/approvals/{approval_id}/decide",
            json=data.model_dump(),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to process approval decision: {exc}")


# ── Documents ───────────────────────────────────────────────────


@router.get("/{dispute_id}/documents/")
async def list_documents(dispute_id: int) -> list[dict[str, Any]]:
    """List all documents attached to dispute.

    Proxies to Agent 4 GET /disputes/{dispute_id}/documents/.
    """
    try:
        return await agent4_get(f"/disputes/{dispute_id}/documents/")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch documents: {exc}")


@router.post("/{dispute_id}/documents/")
async def upload_document(
    dispute_id: int,
    file: UploadFile = File(...),
    document_type: str = Query(...),
    uploaded_by: str = Query(...),
) -> dict[str, Any]:
    """Upload document to dispute.

    Proxies file upload to Agent 4 POST /disputes/{dispute_id}/documents/.
    """
    client = await get_client()
    url = f"{settings.agent4_url}/disputes/{dispute_id}/documents/"
    params = {"document_type": document_type, "uploaded_by": uploaded_by}

    try:
        files = {"file": (file.filename, await file.read(), file.content_type)}
        resp = await client.post(url, files=files, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to upload document: {exc}")


@router.delete("/{dispute_id}/documents/{attachment_id}")
async def delete_document(dispute_id: int, attachment_id: int) -> dict[str, Any]:
    """Delete document from dispute.

    Proxies to Agent 4 DELETE /disputes/{dispute_id}/documents/{attachment_id}.
    """
    client = await get_client()
    url = f"{settings.agent4_url}/disputes/{dispute_id}/documents/{attachment_id}"

    try:
        resp = await client.delete(url)
        resp.raise_for_status()
        return {"status": "deleted", "attachment_id": attachment_id}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to delete document: {exc}")
