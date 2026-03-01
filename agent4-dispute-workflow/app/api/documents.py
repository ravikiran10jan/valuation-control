"""Dispute document upload and management API endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import DisputeAttachmentOut, DisputeAttachmentUploadOut
from app.services.documents import DocumentManager

router = APIRouter(
    prefix="/disputes/{dispute_id}/documents", tags=["Dispute Documents"]
)
_doc_mgr = DocumentManager()


@router.get("/", response_model=list[DisputeAttachmentOut])
async def list_documents(
    dispute_id: int, db: AsyncSession = Depends(get_db)
):
    """List all documents attached to a dispute."""
    return await _doc_mgr.list_attachments(db, dispute_id)


@router.get("/versions", response_model=list[DisputeAttachmentOut])
async def list_document_versions(
    dispute_id: int,
    document_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """List all versions of a specific document type."""
    return await _doc_mgr.get_document_versions(db, dispute_id, document_type)


@router.post("/", response_model=DisputeAttachmentUploadOut, status_code=201)
async def upload_document(
    dispute_id: int,
    file: UploadFile = File(...),
    document_type: str = Query(default="other"),
    uploaded_by: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document (model output, term sheet, etc.) to a dispute."""
    file_data = await file.read()
    attachment = await _doc_mgr.upload_attachment(
        db,
        dispute_id=dispute_id,
        filename=file.filename or "unnamed",
        file_data=file_data,
        content_type=file.content_type or "application/octet-stream",
        document_type=document_type,
        uploaded_by=uploaded_by,
    )

    url = await _doc_mgr.get_presigned_url(attachment.s3_key)

    return DisputeAttachmentUploadOut(
        attachment_id=attachment.attachment_id,
        dispute_id=attachment.dispute_id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        file_size_bytes=attachment.file_size_bytes,
        document_type=attachment.document_type,
        version=attachment.version,
        uploaded_by=attachment.uploaded_by,
        uploaded_at=attachment.uploaded_at,
        presigned_url=url or "",
    )


@router.delete("/{attachment_id}", status_code=204)
async def delete_document(
    dispute_id: int,
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete an attachment from a dispute."""
    deleted = await _doc_mgr.delete_attachment(db, attachment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Attachment not found")
