"""Exception Manager for aging, escalation, and workflow management.

Handles exception lifecycle including assignment, escalation to management,
and addition to Valuation Committee agenda.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import structlog

from app.core.config import settings
from app.models.postgres import (
    CommitteeAgendaItem,
    VCException as ExceptionModel,
    ExceptionComment,
    Position,
)
from app.models.schemas import (
    ExceptionCommentCreate,
    ExceptionUpdate,
    ResolutionData,
)

log = structlog.get_logger()


class ExceptionManager:
    """Manage exception workflow, aging, and escalation."""

    def __init__(self, db: AsyncSession):
        self.db = db
        # Escalation rules (configurable via settings)
        self.escalation_rules = {
            "AMBER": {
                "days_to_manager": settings.escalation_amber_to_manager,
                "days_to_committee": None,  # Never escalate AMBER to committee
            },
            "RED": {
                "days_to_manager": settings.escalation_red_to_manager,
                "days_to_committee": settings.escalation_red_to_committee,
            },
        }

    async def get_exception(self, exception_id: int) -> ExceptionModel | None:
        """Get exception by ID with related data.

        Args:
            exception_id: The exception ID.

        Returns:
            Exception model with position and comments loaded.
        """
        stmt = (
            select(ExceptionModel)
            .options(
                selectinload(ExceptionModel.position),
                selectinload(ExceptionModel.comments),
            )
            .where(ExceptionModel.exception_id == exception_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_exceptions(
        self,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        asset_class: Optional[str] = None,
        assigned_to: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ExceptionModel]:
        """List exceptions with filtering options.

        Args:
            severity: Filter by AMBER/RED.
            status: Filter by OPEN/INVESTIGATING/RESOLVED/ESCALATED.
            asset_class: Filter by position asset class.
            assigned_to: Filter by assigned analyst.
            start_date: Filter by created_date >= start.
            end_date: Filter by created_date <= end.
            limit: Max results.
            offset: Pagination offset.

        Returns:
            List of exceptions matching filters.
        """
        stmt = (
            select(ExceptionModel)
            .options(selectinload(ExceptionModel.position))
            .join(Position)
        )

        filters = []
        if severity:
            filters.append(ExceptionModel.severity == severity)
        if status:
            filters.append(ExceptionModel.status == status)
        if asset_class:
            filters.append(Position.asset_class == asset_class)
        if assigned_to:
            filters.append(ExceptionModel.assigned_to == assigned_to)
        if start_date:
            filters.append(ExceptionModel.created_date >= start_date)
        if end_date:
            filters.append(ExceptionModel.created_date <= end_date)

        if filters:
            stmt = stmt.where(and_(*filters))

        stmt = (
            stmt.order_by(
                ExceptionModel.severity.desc(),  # RED before AMBER
                ExceptionModel.days_open.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_open_exceptions(self) -> list[ExceptionModel]:
        """Get all open/investigating exceptions for escalation check.

        Returns:
            List of non-resolved exceptions.
        """
        stmt = (
            select(ExceptionModel)
            .options(selectinload(ExceptionModel.position))
            .where(
                ExceptionModel.status.in_(["OPEN", "INVESTIGATING", "ESCALATED"])
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_exception(
        self, exception_id: int, data: ExceptionUpdate
    ) -> ExceptionModel | None:
        """Update exception fields.

        Args:
            exception_id: The exception to update.
            data: Fields to update.

        Returns:
            Updated exception or None if not found.
        """
        exc = await self.db.get(ExceptionModel, exception_id)
        if not exc:
            return None

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(exc, field, value)

        await self.db.commit()
        await self.db.refresh(exc)

        log.info("exception_updated", exception_id=exception_id, fields=data.model_dump(exclude_unset=True))
        return exc

    async def assign_exception(
        self, exception_id: int, assigned_to: str
    ) -> ExceptionModel | None:
        """Assign exception to a VC analyst.

        Args:
            exception_id: The exception to assign.
            assigned_to: Analyst name/ID.

        Returns:
            Updated exception or None if not found.
        """
        exc = await self.db.get(ExceptionModel, exception_id)
        if not exc:
            return None

        exc.assigned_to = assigned_to
        if exc.status == "OPEN":
            exc.status = "INVESTIGATING"

        await self.db.commit()
        await self.db.refresh(exc)

        log.info("exception_assigned", exception_id=exception_id, assigned_to=assigned_to)
        return exc

    async def add_comment(
        self, exception_id: int, data: ExceptionCommentCreate
    ) -> ExceptionComment:
        """Add a comment to an exception (dispute tracking).

        Args:
            exception_id: The exception to comment on.
            data: Comment data including user, text, and optional attachments.

        Returns:
            The created comment.
        """
        comment = ExceptionComment(
            exception_id=exception_id,
            user_name=data.user_name,
            comment_text=data.comment_text,
            attachments=data.attachments,
        )
        self.db.add(comment)
        await self.db.commit()
        await self.db.refresh(comment)

        log.info(
            "exception_comment_added",
            exception_id=exception_id,
            user=data.user_name,
        )
        return comment

    async def resolve_exception(
        self, exception_id: int, resolution: ResolutionData
    ) -> ExceptionModel | None:
        """Mark exception as resolved.

        Args:
            exception_id: The exception to resolve.
            resolution: Resolution notes and resolver info.

        Returns:
            Resolved exception or None if not found.
        """
        exc = await self.db.get(ExceptionModel, exception_id)
        if not exc:
            return None

        exc.status = "RESOLVED"
        exc.resolution_notes = resolution.resolution_notes
        exc.resolved_date = date.today()

        # Calculate final days_open
        exc.days_open = (date.today() - exc.created_date).days

        await self.db.commit()
        await self.db.refresh(exc)

        log.info(
            "exception_resolved",
            exception_id=exception_id,
            days_open=exc.days_open,
            resolved_by=resolution.resolved_by,
        )
        return exc

    async def update_days_open(self) -> int:
        """Daily job: Update days_open for all active exceptions.

        Returns:
            Number of exceptions updated.
        """
        exceptions = await self.get_open_exceptions()
        updated = 0

        for exc in exceptions:
            exc.days_open = (date.today() - exc.created_date).days
            updated += 1

        await self.db.commit()
        log.info("days_open_updated", count=updated)
        return updated

    async def check_escalations(self) -> dict:
        """Daily job: Check if exceptions need escalation.

        Returns:
            Summary of escalation actions taken.
        """
        open_exceptions = await self.get_open_exceptions()
        summary = {
            "checked": len(open_exceptions),
            "escalated_to_manager": 0,
            "escalated_to_committee": 0,
        }

        for exc in open_exceptions:
            days_open = (date.today() - exc.created_date).days
            severity = exc.severity
            current_level = exc.escalation_level
            rules = self.escalation_rules.get(severity, {})

            # Check if needs escalation to manager (level 2)
            if current_level == 1:
                days_to_manager = rules.get("days_to_manager")
                if days_to_manager and days_open >= days_to_manager:
                    await self._escalate_to_manager(exc)
                    summary["escalated_to_manager"] += 1

            # Check if needs escalation to committee (level 3)
            elif current_level == 2:
                days_to_committee = rules.get("days_to_committee")
                if days_to_committee and days_open >= days_to_committee:
                    await self._escalate_to_committee(exc)
                    summary["escalated_to_committee"] += 1

        await self.db.commit()
        log.info("escalation_check_complete", **summary)
        return summary

    async def _escalate_to_manager(self, exc: ExceptionModel) -> None:
        """Escalate exception to VC Manager.

        Args:
            exc: The exception to escalate.
        """
        exc.escalation_level = 2
        exc.status = "ESCALATED"

        # Add system comment
        comment = ExceptionComment(
            exception_id=exc.exception_id,
            user_name="SYSTEM",
            comment_text=f"Exception escalated to Manager after {exc.days_open} days open.",
            attachments=None,
        )
        self.db.add(comment)

        # In a real implementation, send email notification
        # self._send_email(
        #     to=settings.vc_manager_email,
        #     subject=f"Exception Escalation - Position {exc.position_id}",
        #     body=self._format_escalation_email(exc)
        # )

        log.warning(
            "exception_escalated_to_manager",
            exception_id=exc.exception_id,
            position_id=exc.position_id,
            days_open=exc.days_open,
        )

    async def _escalate_to_committee(self, exc: ExceptionModel) -> None:
        """Escalate exception to Valuation Committee.

        Args:
            exc: The exception to escalate.
        """
        exc.escalation_level = 3

        # Create committee agenda item
        meeting_date = self._get_next_committee_date()
        agenda_item = CommitteeAgendaItem(
            exception_id=exc.exception_id,
            position_id=exc.position_id,
            difference=exc.difference,
            status="PENDING_COMMITTEE",
            meeting_date=meeting_date,
        )
        self.db.add(agenda_item)

        # Add system comment
        comment = ExceptionComment(
            exception_id=exc.exception_id,
            user_name="SYSTEM",
            comment_text=f"Exception added to Valuation Committee agenda for {meeting_date}.",
            attachments=None,
        )
        self.db.add(comment)

        log.warning(
            "exception_escalated_to_committee",
            exception_id=exc.exception_id,
            position_id=exc.position_id,
            meeting_date=str(meeting_date),
        )

    def _get_next_committee_date(self) -> date:
        """Get next Valuation Committee meeting date (weekly Wednesday).

        Returns:
            The date of the next Wednesday.
        """
        today = date.today()
        days_ahead = 2 - today.weekday()  # Wednesday is weekday 2
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead)

    async def get_committee_agenda(
        self,
        meeting_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> list[CommitteeAgendaItem]:
        """Get Valuation Committee agenda items.

        Args:
            meeting_date: Filter by specific meeting date.
            status: Filter by status (PENDING_COMMITTEE, DISCUSSED, RESOLVED).

        Returns:
            List of agenda items.
        """
        stmt = select(CommitteeAgendaItem)

        filters = []
        if meeting_date:
            filters.append(CommitteeAgendaItem.meeting_date == meeting_date)
        if status:
            filters.append(CommitteeAgendaItem.status == status)

        if filters:
            stmt = stmt.where(and_(*filters))

        stmt = stmt.order_by(CommitteeAgendaItem.meeting_date.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_exception_statistics(self) -> dict:
        """Get detailed exception statistics for dashboard.

        Returns:
            Dictionary with various statistics.
        """
        # Total by status
        status_counts = await self.db.execute(
            select(
                ExceptionModel.status,
                func.count(ExceptionModel.exception_id).label("count"),
            ).group_by(ExceptionModel.status)
        )
        by_status = {row.status: row.count for row in status_counts.all()}

        # Total by severity (open only)
        severity_counts = await self.db.execute(
            select(
                ExceptionModel.severity,
                func.count(ExceptionModel.exception_id).label("count"),
            )
            .where(ExceptionModel.status.in_(["OPEN", "INVESTIGATING", "ESCALATED"]))
            .group_by(ExceptionModel.severity)
        )
        by_severity = {row.severity: row.count for row in severity_counts.all()}

        # Average resolution time
        avg_resolution = await self.db.execute(
            select(func.avg(ExceptionModel.days_open)).where(
                ExceptionModel.status == "RESOLVED"
            )
        )
        avg_days = avg_resolution.scalar() or 0

        # Exceptions by escalation level
        level_counts = await self.db.execute(
            select(
                ExceptionModel.escalation_level,
                func.count(ExceptionModel.exception_id).label("count"),
            )
            .where(ExceptionModel.status.in_(["OPEN", "INVESTIGATING", "ESCALATED"]))
            .group_by(ExceptionModel.escalation_level)
        )
        by_level = {f"level_{row.escalation_level}": row.count for row in level_counts.all()}

        # Exceptions created in last 7 days
        week_ago = date.today() - timedelta(days=7)
        recent_count = await self.db.execute(
            select(func.count(ExceptionModel.exception_id)).where(
                ExceptionModel.created_date >= week_ago
            )
        )
        recent = recent_count.scalar() or 0

        return {
            "by_status": by_status,
            "by_severity": by_severity,
            "by_escalation_level": by_level,
            "avg_days_to_resolve": round(float(avg_days), 1),
            "created_last_7_days": recent,
        }
