"""Deterministic webhook reconciliation (no AI). Implements docs/ARCHITECTURE.md "Reconciliation
algorithm, mandatory":

1. verify raw-body HMAC  2. persist envelope under unique(provider, event_id); replays are no-ops
3. validate account, correlation, currency, amount  4-5. upsert payment + allocate under row locks,
never beyond verified funds or invoice due  6. audit  7. reversals are compensating entries.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import clock
from app.config import Settings
from app.models import Invoice, MerchantProviderAccount, Payment, PaymentRequest, WebhookEvent
from adapters.payments import get_provider

from . import ledger
from .money import format_inr

ACTOR = "reconciliation_service"
# A payment only ever moves up this ladder, so late or re-ordered events cannot regress it.
_RANK = {"pending": 0, "failed": 1, "authorised": 2, "provider_verified": 3, "disputed": 4, "reversed": 5}


@dataclass
class IngestResult:
    http_status: int
    status: str  # processed | duplicate | ignored | rejected
    detail: str
    webhook_event_id: str | None = None


def ingest_webhook(db: Session, settings: Settings, provider_name: str, raw_body: bytes,
                   signature: str | None, event_id: str | None) -> IngestResult:
    provider = get_provider(provider_name, settings)

    # 1. Signature over the exact bytes received, constant-time compare.
    if not provider.verify_signature(raw_body, signature):
        ev = WebhookEvent(provider=provider_name, event_id=None, signature_valid=False, status="rejected",
                          detail="invalid signature", raw_body=raw_body[:2000].decode("utf-8", "replace"))
        db.add(ev)
        db.flush()
        return IngestResult(401, "rejected", "invalid signature", ev.id)
    if not event_id:
        return IngestResult(400, "rejected", "missing provider event id")

    # 2. Idempotency envelope.
    ev = WebhookEvent(provider=provider_name, event_id=event_id, signature_valid=True, status="received",
                      raw_body=raw_body.decode("utf-8", "replace"))
    try:
        with db.begin_nested():
            db.add(ev)
            db.flush()
    except IntegrityError:
        prior = db.scalar(select(WebhookEvent).where(WebhookEvent.provider == provider_name,
                                                     WebhookEvent.event_id == event_id))
        prior.duplicate_deliveries += 1
        return IngestResult(200, "duplicate", "event already recorded; not re-applied", prior.id)

    try:
        with db.begin_nested():
            status, detail = _apply(db, provider, ev, json.loads(raw_body))
    except (ValueError, KeyError, TypeError, ledger.LedgerError) as exc:
        status, detail = "rejected", f"could not apply event: {exc}"
    ev.status, ev.detail = status, detail
    db.flush()
    # Provider gets 2xx for anything authentic so it stops retrying; the outcome is in the envelope.
    return IngestResult(200, status, detail, ev.id)


def _apply(db: Session, provider, ev: WebhookEvent, body: dict) -> tuple[str, str]:
    event_type = body.get("event") or ""
    ev.event_type = event_type
    payload = body.get("payload") or {}

    # 3a. Which tenant does this provider account belong to?
    account = db.scalar(select(MerchantProviderAccount).where(
        MerchantProviderAccount.provider == provider.name,
        MerchantProviderAccount.account_id == str(body.get("account_id"))))
    if account is None:
        return "rejected", "provider account is not linked to any merchant"
    merchant_id = ev.merchant_id = account.merchant_id

    if event_type.startswith("refund.") or event_type.startswith("payment.dispute."):
        return _apply_adjustment(db, provider, ev, merchant_id, event_type, payload)
    if event_type not in ("payment.authorized", "payment.captured", "payment.failed"):
        return "ignored", f"unhandled event type {event_type!r}"

    entity = payload["payment"]["entity"]
    provider_payment_id = str(entity["id"])
    amount, currency = entity["amount"], entity.get("currency")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise ValueError("amount must be a positive integer of paise")
    # 3b. Currency.
    if currency != "INR":
        ledger.open_mismatch(db, merchant_id, "currency_mismatch",
                             f"Provider payment {provider_payment_id} is in {currency!r}; only INR is posted.",
                             webhook_event_id=ev.id)
        return "rejected", f"unsupported currency {currency!r}"

    # 3c. Correlation to one of this merchant's payment requests.
    request_id = (entity.get("notes") or {}).get("payment_request_id")
    request = db.get(PaymentRequest, request_id) if isinstance(request_id, str) else None
    if request is not None and (request.merchant_id != merchant_id or request.provider != provider.name):
        ledger.open_mismatch(db, merchant_id, "reference_not_owned",
                             f"Provider payment {provider_payment_id} references a payment request that does not "
                             "belong to this account. Nothing was posted.", webhook_event_id=ev.id)
        return "rejected", "payment request does not belong to this provider account"

    # 4. Upsert by (provider, provider_payment_id).
    payment = db.scalar(select(Payment).where(Payment.provider == provider.name,
                                              Payment.provider_payment_id == provider_payment_id).with_for_update())
    target = {"payment.authorized": "authorised", "payment.captured": "provider_verified",
              "payment.failed": "failed"}[event_type]
    if payment is None:
        created = entity.get("created_at")
        payment = Payment(
            merchant_id=merchant_id, provider=provider.name, provider_payment_id=provider_payment_id,
            payment_request_id=request.id if request else None,
            intended_invoice_id=request.invoice_id if request else None,
            customer_id=request.customer_id if request else None,
            amount_paise=amount, currency="INR", state="pending", mode=provider.mode, method=entity.get("method"),
            received_at=(datetime.fromtimestamp(created, timezone.utc).replace(tzinfo=None)
                         if isinstance(created, int) else clock.now()))
        db.add(payment)
        db.flush()
        ledger.audit(db, merchant_id, ACTOR, "payment.recorded", "payment", payment.id,
                     provider=provider.name, provider_payment_id=provider_payment_id, amount_paise=amount,
                     mode=provider.mode, webhook_event_id=ev.id)
    elif payment.merchant_id != merchant_id:
        return "rejected", "payment belongs to a different merchant"
    elif payment.amount_paise != amount:
        ledger.open_mismatch(db, merchant_id, "amount_changed",
                             f"Event {ev.event_id} reports a different amount for {provider_payment_id} than first "
                             "recorded. The original amount stands.", payment.id, ev.id)
        return "rejected", "amount differs from the recorded payment"

    if _RANK[target] <= _RANK.get(payment.state, 0):
        return "ignored", f"payment already {payment.state}; {event_type} did not change it"

    previous, payment.state = payment.state, target
    ledger.audit(db, merchant_id, ACTOR, "payment.state_changed", "payment", payment.id,
                 from_state=previous, to_state=target, webhook_event_id=ev.id)
    if target != "provider_verified":
        return "processed", f"payment {target}; no funds posted"

    # 5. Post verified funds exactly once (this branch is only reachable on the transition into verified).
    if request is None:
        ledger.open_mismatch(db, merchant_id, "unknown_reference",
                             f"Verified payment {provider_payment_id} has no matching payment request. It is "
                             "recorded but not applied to any invoice.", payment.id, ev.id)
        return "processed", "verified payment recorded; unallocated (no matching payment request)"

    invoice = db.get(Invoice, request.invoice_id)
    applied = ledger.allocate_available(db, payment, invoice, ACTOR, f"provider event {ev.event_id}")
    if request.status == "approved":
        request.status = "paid"
    if amount != request.amount_paise:
        ledger.open_mismatch(db, merchant_id, "amount_mismatch",
                             f"Requested {format_inr(request.amount_paise)} but the provider verified {format_inr(amount)}.",
                             payment.id, ev.id)
    if applied < amount:
        ledger.open_mismatch(db, merchant_id, "unallocated_funds",
                             f"{format_inr(amount - applied)} of verified payment {provider_payment_id} exceeds the invoice "
                             "balance and is held unallocated. Allocate it to another invoice or refund it.",
                             payment.id, ev.id)
    return "processed", f"verified; {format_inr(applied)} applied to invoice {invoice.number}"


def _apply_adjustment(db: Session, provider, ev: WebhookEvent, merchant_id: str, event_type: str,
                      payload: dict) -> tuple[str, str]:
    kind = "refund" if event_type.startswith("refund.") else "dispute"
    entity = payload[kind]["entity"]
    payment = db.scalar(select(Payment).where(Payment.provider == provider.name, Payment.merchant_id == merchant_id,
                                              Payment.provider_payment_id == str(entity["payment_id"])).with_for_update())
    if payment is None:
        ledger.open_mismatch(db, merchant_id, "adjustment_for_unknown_payment",
                             f"{event_type} refers to provider payment {entity.get('payment_id')}, which has not "
                             "been recorded. Check with the provider.", webhook_event_id=ev.id)
        return "ignored", "adjustment refers to an unknown payment"

    if event_type == "refund.processed":
        if entity.get("amount") != payment.amount_paise:
            ledger.open_mismatch(db, merchant_id, "partial_refund",
                                 f"Partial refund of {entity.get('amount')} paise on a {format_inr(payment.amount_paise)} payment needs manual review.", payment.id, ev.id)
            return "processed", "partial refund flagged for manual review"
        ledger.mark_reversed(db, payment, ACTOR, f"provider refund {entity.get('id')}")
        return "processed", "payment reversed with compensating entries"
    if event_type == "payment.dispute.created":
        ledger.mark_disputed(db, payment, ACTOR, f"provider dispute {entity.get('id')}")
        return "processed", "payment disputed; allocations reversed pending outcome"
    if event_type in ("payment.dispute.won", "payment.dispute.lost") and payment.state == "disputed":
        ledger.resolve_dispute(db, payment, "upheld" if event_type.endswith("won") else "rejected", ACTOR,
                               f"provider event {ev.event_id}")
        return "processed", f"dispute resolved ({event_type.rsplit('.', 1)[-1]})"
    return "ignored", f"{event_type} did not change the payment"
