"""Compliance gate for customer-facing outbound messages.

Meta's WhatsApp Business policy prohibits debt-collection activity, so overdue/collection reminders
are refused on every channel, always. Everything else needs: merchant approval, a recorded opt-in,
no later opt-out, and - for a real channel - OUTBOUND_POLICY_APPROVED plus an approved message type
plus configured channel credentials. The flag alone enables nothing.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Consent

ALLOWED_TYPES = {"invoice_share", "payment_request_share", "promise_confirmation"}
PROHIBITED_TYPES = {"overdue_reminder", "collection_followup", "debt_collection"}


def current_consent(db: Session, merchant_id: str, customer_id: str, channel: str) -> str | None:
    row = db.scalar(select(Consent).where(Consent.merchant_id == merchant_id, Consent.customer_id == customer_id,
                                          Consent.channel == channel)
                    .order_by(Consent.recorded_at.desc(), Consent.id.desc()))
    return row.status if row else None


def check_outbound(db: Session, settings: Settings, merchant_id: str, customer_id: str, channel: str,
                   message_type: str) -> tuple[bool, str]:
    """Returns (allowed, reason)."""
    if message_type in PROHIBITED_TYPES:
        return False, "Overdue/collection reminders are prohibited by WhatsApp Business policy and are never sent."
    if message_type not in ALLOWED_TYPES:
        return False, f"Message type {message_type!r} is not a permitted transactional type."
    consent = current_consent(db, merchant_id, customer_id, channel)
    if consent == "opt_out":
        return False, "Customer has opted out of this channel."
    if consent != "opt_in":
        return False, "No recorded opt-in for this customer on this channel."
    if channel == "demo_inbox":
        return True, "Simulated delivery to the demo inbox only; nothing leaves this system."
    if channel == "whatsapp":
        if not settings.outbound_policy_approved:
            return False, "OUTBOUND_POLICY_APPROVED is not set; real customer messaging is disabled."
        if message_type not in settings.approved_message_types:
            return False, f"Message type {message_type!r} is not in OUTBOUND_APPROVED_MESSAGE_TYPES."
        if not settings.whatsapp_access_token:
            return False, "WhatsApp channel credentials are not configured."
        return False, ("All policy gates pass, but live WhatsApp sending is intentionally not implemented in this "
                       "MVP. Share the content manually or use the demo inbox.")
    return False, f"Channel {channel!r} does not support outbound messages."
