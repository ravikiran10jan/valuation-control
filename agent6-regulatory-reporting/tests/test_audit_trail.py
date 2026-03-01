"""Tests for audit trail service."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from app.models.schemas import (
    AuditEventOut,
    AuditEventType,
    AuditTrailQuery,
)


class TestAuditTrail:
    """Tests for AuditTrail service."""

    @pytest.mark.asyncio
    async def test_log_audit_event(self):
        """Test logging an audit event."""
        from app.services.audit_trail import AuditTrail

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        audit_trail = AuditTrail(mock_db)

        # Mock the event creation
        event = await audit_trail.log_audit_event(
            event_type=AuditEventType.VALUATION_RUN,
            user="test_user",
            details={"position_count": 100, "run_id": "abc123"},
            ip_address="192.168.1.1",
        )

        # Verify add was called
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_audit_events(self):
        """Test querying audit events."""
        from app.services.audit_trail import AuditTrail
        from app.models.postgres import AuditEvent

        # Create mock events
        mock_event = MagicMock()
        mock_event.event_id = uuid.uuid4()
        mock_event.event_type = "VALUATION_RUN"
        mock_event.user = "test_user"
        mock_event.timestamp = datetime.utcnow()
        mock_event.details = {"test": "data"}
        mock_event.ip_address = "192.168.1.1"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_event]
        mock_db.execute.return_value = mock_result

        audit_trail = AuditTrail(mock_db)

        query = AuditTrailQuery(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        events = await audit_trail.query_audit_events(query)

        assert len(events) == 1
        assert events[0].user == "test_user"

    @pytest.mark.asyncio
    async def test_generate_audit_report(self):
        """Test audit report generation."""
        from app.services.audit_trail import AuditTrail

        mock_db = AsyncMock()
        audit_trail = AuditTrail(mock_db)

        # Mock query_audit_events
        mock_events = [
            AuditEventOut(
                event_id=str(uuid.uuid4()),
                event_type=AuditEventType.VALUATION_RUN,
                user="user1",
                timestamp=datetime.utcnow(),
                details={},
            ),
            AuditEventOut(
                event_id=str(uuid.uuid4()),
                event_type=AuditEventType.REPORT_GENERATED,
                user="user2",
                timestamp=datetime.utcnow(),
                details={},
            ),
            AuditEventOut(
                event_id=str(uuid.uuid4()),
                event_type=AuditEventType.VALUATION_RUN,
                user="user1",
                timestamp=datetime.utcnow(),
                details={},
            ),
        ]

        audit_trail.query_audit_events = AsyncMock(return_value=mock_events)

        report = await audit_trail.generate_audit_report(
            date(2024, 1, 1), date(2024, 12, 31)
        )

        assert report.total_events == 3
        assert "VALUATION_RUN" in report.events_by_type
        assert report.events_by_type["VALUATION_RUN"] == 2
        assert "user1" in report.users
        assert "user2" in report.users


class TestAuditEventTypes:
    """Tests for audit event type handling."""

    def test_all_event_types_defined(self):
        """Test all required event types are defined."""
        required_types = [
            "VALUATION_RUN",
            "MARK_ADJUSTMENT",
            "EXCEPTION_CREATED",
            "EXCEPTION_RESOLVED",
            "REPORT_GENERATED",
            "REPORT_SUBMITTED",
            "AVA_CALCULATED",
            "LEVEL_TRANSFER",
        ]

        for event_type in required_types:
            assert hasattr(AuditEventType, event_type)
            assert AuditEventType[event_type].value == event_type
