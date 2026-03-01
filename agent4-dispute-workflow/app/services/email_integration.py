"""Email integration service for dispute notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog

from app.core.config import settings

log = structlog.get_logger()


class EmailIntegration:
    """Handles outbound email notifications and inbound email sync for disputes."""

    def __init__(self) -> None:
        self._provider = settings.email_provider
        self._base_url = settings.vc_platform_base_url

    # ── Templates ─────────────────────────────────────────────────
    def _render_dispute_initiated(self, dispute: dict) -> tuple[str, str]:
        subject = f"[DISPUTE-{dispute['dispute_id']}] Valuation Exception Requires Response"
        body = f"""
VALUATION DISPUTE -- ACTION REQUIRED

Position: {dispute.get('position_id', 'N/A')}
VC Fair Value: {dispute.get('vc_fair_value', 'N/A')}
Desk Mark: {dispute.get('desk_mark', 'N/A')}
Difference: {dispute.get('difference', 'N/A')} ({dispute.get('difference_pct', 'N/A')}%)

VC POSITION:
{dispute.get('vc_position', '')}

Please review and respond within {settings.desk_response_deadline_days} business days.
Access dispute portal: {self._base_url}/disputes/{dispute['dispute_id']}
"""
        return subject, body

    def _render_desk_responded(self, dispute: dict) -> tuple[str, str]:
        subject = f"[DISPUTE-{dispute['dispute_id']}] Desk Has Responded"
        body = f"""
DESK RESPONSE RECEIVED

Dispute #{dispute['dispute_id']} - Position {dispute.get('position_id', 'N/A')}

DESK POSITION:
{dispute.get('desk_position', 'No response text')}

Please review the desk response and take action.
Access dispute portal: {self._base_url}/disputes/{dispute['dispute_id']}
"""
        return subject, body

    def _render_escalation(self, dispute: dict) -> tuple[str, str]:
        subject = f"[DISPUTE-{dispute['dispute_id']}] ESCALATED - Requires Committee Review"
        body = f"""
DISPUTE ESCALATED TO COMMITTEE

Dispute #{dispute['dispute_id']} - Position {dispute.get('position_id', 'N/A')}
VC Fair Value: {dispute.get('vc_fair_value', 'N/A')}
Desk Mark: {dispute.get('desk_mark', 'N/A')}
Difference: {dispute.get('difference', 'N/A')} ({dispute.get('difference_pct', 'N/A')}%)

This dispute has been escalated and requires committee review.
Access dispute portal: {self._base_url}/disputes/{dispute['dispute_id']}
"""
        return subject, body

    def _render_resolved(self, dispute: dict) -> tuple[str, str]:
        subject = f"[DISPUTE-{dispute['dispute_id']}] Resolved - {dispute.get('resolution_type', 'N/A')}"
        body = f"""
DISPUTE RESOLVED

Dispute #{dispute['dispute_id']} - Position {dispute.get('position_id', 'N/A')}
Resolution: {dispute.get('resolution_type', 'N/A')}
Final Mark: {dispute.get('final_mark', 'N/A')}

Access dispute portal: {self._base_url}/disputes/{dispute['dispute_id']}
"""
        return subject, body

    def _render_approval_request(self, approval: dict, dispute: dict) -> tuple[str, str]:
        subject = f"[DISPUTE-{dispute['dispute_id']}] Mark Adjustment Approval Required"
        body = f"""
MARK ADJUSTMENT APPROVAL REQUIRED

Dispute #{dispute['dispute_id']} - Position {dispute.get('position_id', 'N/A')}

Requested by: {approval.get('requested_by', 'N/A')}
Current Mark: {approval.get('old_mark', 'N/A')}
Proposed Mark: {approval.get('new_mark', 'N/A')}

Justification:
{approval.get('justification', '')}

Access dispute portal: {self._base_url}/disputes/{dispute['dispute_id']}
"""
        return subject, body

    # ── Sending ───────────────────────────────────────────────────
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[list[str]] = None,
    ) -> bool:
        """Send an email using the configured provider.

        In production this would integrate with Microsoft Graph API or SMTP.
        Currently logs the email for development purposes.
        """
        log.info(
            "email_sent",
            to=to,
            cc=cc,
            subject=subject,
            provider=self._provider,
        )
        # Production implementation would go here:
        # if self._provider == "outlook":
        #     return await self._send_via_graph(to, subject, body, cc)
        # else:
        #     return await self._send_via_smtp(to, subject, body, cc)
        return True

    # ── Notification dispatch ─────────────────────────────────────
    async def notify_dispute_initiated(
        self, dispute: dict, desk_email: str
    ) -> bool:
        subject, body = self._render_dispute_initiated(dispute)
        return await self.send_email(to=desk_email, subject=subject, body=body)

    async def notify_desk_responded(
        self, dispute: dict, vc_email: str
    ) -> bool:
        subject, body = self._render_desk_responded(dispute)
        return await self.send_email(to=vc_email, subject=subject, body=body)

    async def notify_escalation(self, dispute: dict) -> bool:
        subject, body = self._render_escalation(dispute)
        return await self.send_email(
            to=settings.vc_committee_email,
            subject=subject,
            body=body,
            cc=[settings.vc_manager_email],
        )

    async def notify_resolved(
        self, dispute: dict, recipients: list[str]
    ) -> bool:
        subject, body = self._render_resolved(dispute)
        for recipient in recipients:
            await self.send_email(to=recipient, subject=subject, body=body)
        return True

    async def notify_approval_request(
        self, approval: dict, dispute: dict, approver_email: str
    ) -> bool:
        subject, body = self._render_approval_request(approval, dispute)
        return await self.send_email(to=approver_email, subject=subject, body=body)

    # ── Email sync (inbound) ──────────────────────────────────────
    async def sync_dispute_emails(self, dispute_id: int) -> list[dict]:
        """Search for emails tagged with [DISPUTE-{id}] and sync to messages table.

        In production this would use Microsoft Graph API to search mailbox.
        Returns list of synced email metadata.
        """
        log.info("email_sync_requested", dispute_id=dispute_id)
        # Production: search Graph API for subject containing [DISPUTE-{dispute_id}]
        # Parse bodies, download attachments, store in dispute_messages
        return []
