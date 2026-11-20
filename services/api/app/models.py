"""Authoritative schema. All money is integer INR paise; every business row is tenant-scoped."""
import threading
import time
import uuid
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from . import clock
from .db import Base


_id_lock = threading.Lock()
_last_ns = 0


def new_id(prefix: str) -> str:
    """Time-sortable ID, strictly increasing within a process, so (created_at, id) is insertion order
    even when several rows share a timestamp."""
    global _last_ns
    with _id_lock:
        _last_ns = max(time.time_ns(), _last_ns + 1)
        ns = _last_ns
    return f"{prefix}_{ns:016x}{uuid.uuid4().hex[:6]}"


def _pk(prefix: str):
    return mapped_column(String(40), primary_key=True, default=lambda: new_id(prefix))


def _merchant():
    return mapped_column(String(40), ForeignKey("merchants.id"), index=True)


def _created():
    return mapped_column(DateTime, default=clock.now)


class Merchant(Base):
    __tablename__ = "merchants"
    id: Mapped[str] = _pk("mer")
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Kolkata")
    next_invoice_seq: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = _created()


class MerchantProviderAccount(Base):
    """Maps a provider account (payment account, WhatsApp phone-number ID) to its tenant."""
    __tablename__ = "merchant_provider_accounts"
    __table_args__ = (UniqueConstraint("provider", "account_id"),)
    id: Mapped[str] = _pk("mpa")
    merchant_id: Mapped[str] = _merchant()
    provider: Mapped[str] = mapped_column(String(30))
    account_id: Mapped[str] = mapped_column(String(100))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = _pk("usr")
    merchant_id: Mapped[str] = _merchant()
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner | staff | viewer


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = _pk("cus")
    merchant_id: Mapped[str] = _merchant()
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(30))
    # Explicitly stated by the customer and editable; never inferred.
    preferred_method: Mapped[str | None] = mapped_column(String(20))
    preference_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class Consent(Base):
    """Append-only consent evidence; the latest row per (customer, channel) is the current state."""
    __tablename__ = "consents"
    id: Mapped[str] = _pk("con")
    merchant_id: Mapped[str] = _merchant()
    customer_id: Mapped[str] = mapped_column(String(40), ForeignKey("customers.id"), index=True)
    channel: Mapped[str] = mapped_column(String(30))  # demo_inbox | whatsapp | voice_call
    status: Mapped[str] = mapped_column(String(20))  # opt_in | opt_out
    evidence: Mapped[str] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(40))
    recorded_at: Mapped[datetime] = _created()


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[str] = _pk("upl")
    merchant_id: Mapped[str] = _merchant()
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(30), default="web")  # web | whatsapp_demo | whatsapp
    external_media_id: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = _created()


class InvoiceDraft(Base):
    __tablename__ = "invoice_drafts"
    id: Mapped[str] = _pk("drf")
    merchant_id: Mapped[str] = _merchant()
    upload_id: Mapped[str] = mapped_column(String(40), ForeignKey("uploads.id"))
    status: Mapped[str] = mapped_column(String(30), default="needs_review")  # needs_review | approved | rejected
    extraction_source: Mapped[str] = mapped_column(String(30))  # simulated | gemini | manual
    extraction_error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    customer_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("customers.id"))
    invoice_id: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=clock.now, onupdate=clock.now)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("merchant_id", "number"),)
    id: Mapped[str] = _pk("inv")
    merchant_id: Mapped[str] = _merchant()
    customer_id: Mapped[str] = mapped_column(String(40), ForeignKey("customers.id"), index=True)
    number: Mapped[str] = mapped_column(String(40))
    invoice_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    subtotal_paise: Mapped[int] = mapped_column(BigInteger)
    tax_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    draft_id: Mapped[str | None] = mapped_column(String(40))
    approved_by: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = _created()
    # No stored balance: due is always derived from payment_allocations.


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[str] = _pk("lin")
    merchant_id: Mapped[str] = _merchant()
    invoice_id: Mapped[str] = mapped_column(String(40), ForeignKey("invoices.id"), index=True)
    position: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[str] = mapped_column(String(30))  # decimal string
    unit_price_paise: Mapped[int] = mapped_column(BigInteger)
    line_total_paise: Mapped[int] = mapped_column(BigInteger)


class PaymentRequest(Base):
    __tablename__ = "payment_requests"
    id: Mapped[str] = _pk("prq")
    merchant_id: Mapped[str] = _merchant()
    invoice_id: Mapped[str] = mapped_column(String(40), ForeignKey("invoices.id"), index=True)
    customer_id: Mapped[str] = mapped_column(String(40), ForeignKey("customers.id"))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | approved | paid | cancelled
    provider: Mapped[str | None] = mapped_column(String(30))
    mode: Mapped[str | None] = mapped_column(String(20))  # simulated | test | live
    provider_ref: Mapped[str | None] = mapped_column(String(100), index=True)
    link_url: Mapped[str | None] = mapped_column(String(500))
    proposed_by: Mapped[str] = mapped_column(String(40))
    approved_by: Mapped[str | None] = mapped_column(String(40))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = _created()


class WebhookEvent(Base):
    """Raw ingestion envelope. unique(provider, event_id) is the idempotency key."""
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id"),)
    id: Mapped[str] = _pk("whe")
    merchant_id: Mapped[str | None] = mapped_column(String(40), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    event_id: Mapped[str | None] = mapped_column(String(200))
    event_type: Mapped[str | None] = mapped_column(String(80))
    signature_valid: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(30))  # received | processed | ignored | rejected
    detail: Mapped[str | None] = mapped_column(Text)
    raw_body: Mapped[str] = mapped_column(Text)
    duplicate_deliveries: Mapped[int] = mapped_column(BigInteger, default=0)
    received_at: Mapped[datetime] = _created()


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("provider", "provider_payment_id"),)
    id: Mapped[str] = _pk("pay")
    merchant_id: Mapped[str] = _merchant()
    customer_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("customers.id"), index=True)
    provider: Mapped[str] = mapped_column(String(30))  # demo | razorpay | manual
    provider_payment_id: Mapped[str] = mapped_column(String(100))
    payment_request_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("payment_requests.id"))
    intended_invoice_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("invoices.id"))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    # pending | authorised | failed | provider_verified | manual_unverified | merchant_confirmed | disputed | reversed
    state: Mapped[str] = mapped_column(String(30))
    state_before_dispute: Mapped[str | None] = mapped_column(String(30))
    mode: Mapped[str] = mapped_column(String(20))  # simulated | test | live | manual
    method: Mapped[str | None] = mapped_column(String(30))
    evidence_type: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=clock.now)
    created_at: Mapped[datetime] = _created()


class PaymentAllocation(Base):
    """Immutable ledger entry. Positive = allocation, negative = compensating reversal."""
    __tablename__ = "payment_allocations"
    id: Mapped[str] = _pk("alc")
    merchant_id: Mapped[str] = _merchant()
    payment_id: Mapped[str] = mapped_column(String(40), ForeignKey("payments.id"), index=True)
    invoice_id: Mapped[str] = mapped_column(String(40), ForeignKey("invoices.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(20))  # allocation | reversal
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = _created()


class Mismatch(Base):
    __tablename__ = "mismatches"
    id: Mapped[str] = _pk("mis")
    merchant_id: Mapped[str] = _merchant()
    kind: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text)
    payment_id: Mapped[str | None] = mapped_column(String(40))
    webhook_event_id: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | resolved
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = _created()


class Promise(Base):
    """A customer-stated intention to pay. Never a receipt; never changes a balance."""
    __tablename__ = "promises"
    id: Mapped[str] = _pk("prm")
    merchant_id: Mapped[str] = _merchant()
    customer_id: Mapped[str] = mapped_column(String(40), ForeignKey("customers.id"), index=True)
    invoice_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("invoices.id"))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    promised_date: Mapped[date] = mapped_column(Date, index=True)
    method: Mapped[str] = mapped_column(String(20))  # cash | upi | other
    pickup_window: Mapped[str | None] = mapped_column(String(100))  # customer-confirmed cash pickup availability
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | kept | broken | cancelled
    evidence_source: Mapped[str] = mapped_column(String(40))  # demo_inbox | whatsapp | in_person | phone_call | demo_seed
    evidence_text: Mapped[str] = mapped_column(Text)
    source_message_id: Mapped[str | None] = mapped_column(String(40))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_by: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=clock.now, onupdate=clock.now)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_customer", "merchant_id", "customer_id"),)
    id: Mapped[str] = _pk("msg")
    merchant_id: Mapped[str] = _merchant()
    customer_id: Mapped[str] = mapped_column(String(40), ForeignKey("customers.id"))
    direction: Mapped[str] = mapped_column(String(10))  # inbound | outbound
    channel: Mapped[str] = mapped_column(String(30))  # demo_inbox | whatsapp
    message_type: Mapped[str] = mapped_column(String(40), default="text")
    body: Mapped[str] = mapped_column(Text)
    # received | draft | sent_simulated | blocked
    status: Mapped[str] = mapped_column(String(20))
    block_reason: Mapped[str | None] = mapped_column(Text)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = _created()


class ContactEvent(Base):
    __tablename__ = "contact_events"
    id: Mapped[str] = _pk("cev")
    merchant_id: Mapped[str] = _merchant()
    customer_id: Mapped[str] = mapped_column(String(40), ForeignKey("customers.id"))
    kind: Mapped[str] = mapped_column(String(20))  # contacted | replied
    channel: Mapped[str] = mapped_column(String(30))
    message_id: Mapped[str | None] = mapped_column(String(40))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=clock.now, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_entity", "merchant_id", "entity_type", "entity_id"),)
    id: Mapped[str] = _pk("aud")
    merchant_id: Mapped[str | None] = mapped_column(String(40), index=True)
    actor: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = _created()


def _immutable(mapper, connection, target):
    raise RuntimeError(f"{type(target).__name__} rows are immutable; write a compensating entry instead")


for _model in (AuditEvent, PaymentAllocation):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)
