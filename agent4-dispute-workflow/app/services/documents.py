"""Document management service for dispute attachments (S3-backed)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.core.config import settings
from app.models.postgres import DisputeAttachment

log = structlog.get_logger()


class DocumentManager:
    """Handles file uploads, S3 storage, pre-signed URLs, and version tracking."""

    def __init__(self) -> None:
        self._bucket = settings.s3_bucket
        self._region = settings.s3_region
        self._presigned_expiry = settings.s3_presigned_url_expiry_seconds

    def _get_s3_client(self):
        """Lazily create S3 client.

        In production this would use boto3.client('s3').
        Kept as a method so tests can mock it.
        """
        try:
            import boto3

            return boto3.client(
                "s3",
                region_name=self._region,
                aws_access_key_id=settings.aws_access_key_id or None,
                aws_secret_access_key=settings.aws_secret_access_key or None,
            )
        except ImportError:
            log.warning("boto3_not_installed", msg="S3 operations will be no-ops")
            return None

    def _generate_s3_key(self, dispute_id: int, filename: str) -> str:
        return f"disputes/{dispute_id}/{uuid.uuid4()}_{filename}"

    async def upload_attachment(
        self,
        db: AsyncSession,
        dispute_id: int,
        filename: str,
        file_data: bytes,
        content_type: str,
        document_type: str,
        uploaded_by: str,
    ) -> DisputeAttachment:
        s3_key = self._generate_s3_key(dispute_id, filename)

        # Upload to S3
        s3 = self._get_s3_client()
        if s3:
            s3.put_object(
                Bucket=self._bucket,
                Key=s3_key,
                Body=file_data,
                ContentType=content_type,
            )

        # Determine version
        version = await self._next_version(db, dispute_id, document_type)

        attachment = DisputeAttachment(
            dispute_id=dispute_id,
            filename=filename,
            s3_key=s3_key,
            content_type=content_type,
            file_size_bytes=len(file_data),
            document_type=document_type,
            version=version,
            uploaded_by=uploaded_by,
        )
        db.add(attachment)
        await db.commit()
        await db.refresh(attachment)

        log.info(
            "attachment_uploaded",
            dispute_id=dispute_id,
            filename=filename,
            s3_key=s3_key,
            version=version,
        )
        return attachment

    async def get_presigned_url(self, s3_key: str) -> Optional[str]:
        s3 = self._get_s3_client()
        if not s3:
            return None
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": s3_key},
            ExpiresIn=self._presigned_expiry,
        )

    async def list_attachments(
        self, db: AsyncSession, dispute_id: int
    ) -> List[DisputeAttachment]:
        result = await db.execute(
            select(DisputeAttachment)
            .where(DisputeAttachment.dispute_id == dispute_id)
            .order_by(DisputeAttachment.uploaded_at.desc())
        )
        return list(result.scalars().all())

    async def get_document_versions(
        self, db: AsyncSession, dispute_id: int, document_type: str
    ) -> List[DisputeAttachment]:
        result = await db.execute(
            select(DisputeAttachment)
            .where(
                DisputeAttachment.dispute_id == dispute_id,
                DisputeAttachment.document_type == document_type,
            )
            .order_by(DisputeAttachment.version.asc())
        )
        return list(result.scalars().all())

    async def delete_attachment(
        self, db: AsyncSession, attachment_id: int
    ) -> bool:
        attachment = await db.get(DisputeAttachment, attachment_id)
        if attachment is None:
            return False

        # Delete from S3
        s3 = self._get_s3_client()
        if s3:
            s3.delete_object(Bucket=self._bucket, Key=attachment.s3_key)

        await db.delete(attachment)
        await db.commit()
        log.info("attachment_deleted", attachment_id=attachment_id)
        return True

    async def _next_version(
        self, db: AsyncSession, dispute_id: int, document_type: str
    ) -> int:
        result = await db.scalar(
            select(func.max(DisputeAttachment.version)).where(
                DisputeAttachment.dispute_id == dispute_id,
                DisputeAttachment.document_type == document_type,
            )
        )
        return (result or 0) + 1
