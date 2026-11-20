"""Payments, payment requests, provider webhooks, the demo provider simulator and verification views."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.payments import DemoPaymentProvider, get_provider
from domain import ledger, reconciliation
from domain.money import format_inr

from .. import clock
from ..auth import Principal, can_write, current_principal, owned, owner_only
from ..config import get_settings
from ..db import get_db
from ..models import (Customer, Invoice, MerchantProviderAccount, Mismatch, Payment, PaymentRequest, WebhookEvent)
from ..seed import reset
from .core import customer_names, invoice_dict, payment_dict, request_dict

router = APIRouter(prefix="/v1")


def _ledger_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ledger.LedgerError as exc:
        raise HTTPException(409, str(exc)) from exc


# ---- payments -----------------------------------------------------------------------------------
class ManualPaymentIn(BaseModel):
    customer_id: str
    invoice_id: str
    amount_paise: int = Field(gt=0, le=10**12)
    method: str = Field(pattern="^(cash|upi_claim|bank_transfer_claim)$")
    evidence_type: str = Field(pattern="^(cash_in_hand|screenshot|bank_sms|verbal)$")
    note: str = Field(min_length=3, max_length=1000)


class NoteIn(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


class ResolveIn(NoteIn):
    outcome: str = Field(pattern="^(upheld|rejected)$")


class AllocateIn(BaseModel):
    invoice_id: str
    amount_paise: int = Field(gt=0)


@router.get("/payments")
def list_payments(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    names = customer_names(db, p.merchant_id)
    rows = db.scalars(select(Payment).where(Payment.merchant_id == p.merchant_id).order_by(Payment.received_at.desc())).all()
    return [payment_dict(db, x, names) for x in rows]


@router.post("/payments/manual", status_code=201)
def record_manual_payment(body: ManualPaymentIn, p: Principal = Depends(can_write), db: Session = Depends(get_db)):
    """Record a claimed receipt (cash note, screenshot, SMS, verbal). It stays `manual_unverified`
    and does not change any balance until an owner confirms it."""
    owned(db, Customer, body.customer_id, p.merchant_id)
    inv = owned(db, Invoice, body.invoice_id, p.merchant_id)
    if inv.customer_id != body.customer_id:
        raise HTTPException(422, "Invoice does not belong to this customer")
    pay = Payment(merchant_id=p.merchant_id, customer_id=body.customer_id, provider="manual",
                  provider_payment_id=f"manual_{uuid.uuid4().hex[:16]}", intended_invoice_id=inv.id,
                  amount_paise=body.amount_paise, state="manual_unverified", mode="manual", method=body.method,
                  evidence_type=body.evidence_type, note=body.note)
    db.add(pay)
    db.flush()
    ledger.audit(db, p.merchant_id, p.user_id, "payment.manual_recorded", "payment", pay.id,
                 amount_paise=body.amount_paise, evidence_type=body.evidence_type, invoice_id=inv.id)
    return payment_dict(db, pay, customer_names(db, p.merchant_id))


@router.post("/payments/{payment_id}/confirm")
def confirm_manual_payment(payment_id: str, body: NoteIn, p: Principal = Depends(owner_only), db: Session = Depends(get_db)):
    """Authorised finance reconciliation: an owner states how they verified the money. The receipt becomes
    `merchant_confirmed` (reported separately from provider-verified) and is applied to its invoice."""
    pay = owned(db, Payment, payment_id, p.merchant_id)
    if pay.state != "manual_unverified":
        raise HTTPException(409, f"Only unverified manual receipts can be confirmed (this one is {pay.state})")
    pay.state = "merchant_confirmed"
    ledger.audit(db, p.merchant_id, p.user_id, "payment.merchant_confirmed", "payment", pay.id, reconciliation_note=body.note)
    inv = db.get(Invoice, pay.intended_invoice_id)
    applied = _ledger_call(ledger.allocate_available, db, pay, inv, p.user_id, f"owner confirmation: {body.note}")
    if applied < pay.amount_paise:
        ledger.open_mismatch(db, p.merchant_id, "unallocated_funds",
                             f"{format_inr(pay.amount_paise - applied)} of a confirmed manual receipt exceeds the invoice balance "
                             "and is held unallocated.", pay.id)
    return payment_dict(db, pay, customer_names(db, p.merchant_id))


@router.post("/payments/{payment_id}/dispute")
def dispute_payment(payment_id: str, body: NoteIn, p: Principal = Depends(can_write), db: Session = Depends(get_db)):
    pay = owned(db, Payment, payment_id, p.merchant_id)
    if pay.state in ("disputed", "reversed", "failed"):
        raise HTTPException(409, f"Payment is already {pay.state}")
    ledger.mark_disputed(db, pay, p.user_id, body.note)
    return payment_dict(db, pay, customer_names(db, p.merchant_id))


@router.post("/payments/{payment_id}/resolve-dispute")
def resolve_dispute(payment_id: str, body: ResolveIn, p: Principal = Depends(owner_only), db: Session = Depends(get_db)):
    pay = owned(db, Payment, payment_id, p.merchant_id)
    _ledger_call(ledger.resolve_dispute, db, pay, body.outcome, p.user_id, body.note)
    return payment_dict(db, pay, customer_names(db, p.merchant_id))


@router.post("/payments/{payment_id}/allocate")
def allocate_payment(payment_id: str, body: AllocateIn, p: Principal = Depends(owner_only), db: Session = Depends(get_db)):
    """Apply unallocated confirmed funds to another invoice of the same merchant."""
    pay = owned(db, Payment, payment_id, p.merchant_id)
    inv = owned(db, Invoice, body.invoice_id, p.merchant_id)
    _ledger_call(ledger.allocate, db, pay, inv, body.amount_paise, p.user_id, "manual allocation by owner")
    return payment_dict(db, pay, customer_names(db, p.merchant_id))


# ---- payment requests ("payment intents") -------------------------------------------------------
class IntentIn(BaseModel):
    invoice_id: str
    amount_paise: int = Field(gt=0)


class IntentApproveIn(BaseModel):
    provider: str = Field(default="demo", pattern="^(demo|razorpay)$")


@router.get("/payment-intents")
def list_intents(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    names = customer_names(db, p.merchant_id)
    rows = db.scalars(select(PaymentRequest).where(PaymentRequest.merchant_id == p.merchant_id)
                      .order_by(PaymentRequest.created_at.desc())).all()
    numbers = dict(db.execute(select(Invoice.id, Invoice.number).where(Invoice.merchant_id == p.merchant_id)).all())
    return [{**request_dict(r), "customer_name": names.get(r.customer_id), "invoice_number": numbers.get(r.invoice_id)} for r in rows]


@router.post("/payment-intents", status_code=201)
def propose_intent(body: IntentIn, p: Principal = Depends(can_write), db: Session = Depends(get_db)):
    """Proposal only. Nothing is created at a provider and nothing is sent to the customer."""
    inv = owned(db, Invoice, body.invoice_id, p.merchant_id)
    due = ledger.invoice_due(db, inv)
    if body.amount_paise > due:
        raise HTTPException(422, f"Amount exceeds the invoice balance of {format_inr(due)}")
    req = PaymentRequest(merchant_id=p.merchant_id, invoice_id=inv.id, customer_id=inv.customer_id,
                         amount_paise=body.amount_paise, proposed_by=p.user_id)
    db.add(req)
    db.flush()
    ledger.audit(db, p.merchant_id, p.user_id, "payment_request.proposed", "invoice", inv.id, payment_request_id=req.id,
                 amount_paise=body.amount_paise)
    return request_dict(req)


@router.post("/payment-intents/{request_id}/approve")
def approve_intent(request_id: str, body: IntentApproveIn, p: Principal = Depends(owner_only), db: Session = Depends(get_db)):
    """Owner approval creates the request at the provider (demo simulator or Razorpay test mode).
    The link is returned to the merchant; this system never sends it to the customer."""
    req = owned(db, PaymentRequest, request_id, p.merchant_id)
    if req.status != "proposed":
        raise HTTPException(409, f"Payment request is already {req.status}")
    inv = db.get(Invoice, req.invoice_id)
    if req.amount_paise > ledger.invoice_due(db, inv):
        raise HTTPException(409, "Invoice balance is now lower than this request; cancel it and propose a new one")
    provider = get_provider(body.provider, get_settings())
    try:
        created = provider.create_payment_request(req.id, req.amount_paise, f"Invoice {inv.number}")
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Provider error: {type(exc).__name__}") from exc
    req.status, req.provider, req.mode = "approved", provider.name, provider.mode
    req.provider_ref, req.link_url = created.provider_ref, created.link_url
    req.approved_by, req.approved_at = p.user_id, clock.now()
    ledger.audit(db, p.merchant_id, p.user_id, "payment_request.approved", "invoice", inv.id, payment_request_id=req.id,
                 provider=provider.name, mode=provider.mode)
    return request_dict(req)


@router.post("/payment-intents/{request_id}/cancel")
def cancel_intent(request_id: str, p: Principal = Depends(can_write), db: Session = Depends(get_db)):
    req = owned(db, PaymentRequest, request_id, p.merchant_id)
    if req.status not in ("proposed", "approved"):
        raise HTTPException(409, f"Payment request is already {req.status}")
    req.status = "cancelled"
    ledger.audit(db, p.merchant_id, p.user_id, "payment_request.cancelled", "invoice", req.invoice_id, payment_request_id=req.id)
    return request_dict(req)


# ---- provider webhooks (unauthenticated routes; trust comes only from the raw-body signature) -----
async def _raw(request: Request) -> bytes:
    return await request.body()


def _respond(res: reconciliation.IngestResult) -> JSONResponse:
    return JSONResponse({"status": res.status, "detail": res.detail}, status_code=res.http_status)


@router.post("/webhooks/demo")
def demo_webhook(request: Request, raw: bytes = Depends(_raw), db: Session = Depends(get_db)):
    return _respond(reconciliation.ingest_webhook(db, get_settings(), "demo", raw,
                                                  request.headers.get("x-demo-signature"),
                                                  request.headers.get("x-demo-event-id")))


@router.post("/webhooks/razorpay")
def razorpay_webhook(request: Request, raw: bytes = Depends(_raw), db: Session = Depends(get_db)):
    return _respond(reconciliation.ingest_webhook(db, get_settings(), "razorpay", raw,
                                                  request.headers.get("x-razorpay-signature"),
                                                  request.headers.get("x-razorpay-event-id")))


# ---- verification views ---------------------------------------------------------------------------
@router.get("/webhook-events")
def list_webhook_events(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(WebhookEvent).where(WebhookEvent.merchant_id == p.merchant_id)
                      .order_by(WebhookEvent.received_at.desc()).limit(100)).all()
    return [{"id": e.id, "provider": e.provider, "event_id": e.event_id, "event_type": e.event_type,
             "signature_valid": e.signature_valid, "status": e.status, "detail": e.detail,
             "duplicate_deliveries": e.duplicate_deliveries, "received_at": clock.iso(e.received_at)} for e in rows]


@router.get("/mismatches")
def list_mismatches(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(Mismatch).where(Mismatch.merchant_id == p.merchant_id)
                      .order_by(Mismatch.status, Mismatch.created_at.desc())).all()
    return [{"id": m.id, "kind": m.kind, "detail": m.detail, "payment_id": m.payment_id, "status": m.status,
             "resolution_note": m.resolution_note, "created_at": clock.iso(m.created_at)} for m in rows]


@router.post("/mismatches/{mismatch_id}/resolve")
def resolve_mismatch(mismatch_id: str, body: NoteIn, p: Principal = Depends(owner_only), db: Session = Depends(get_db)):
    m = owned(db, Mismatch, mismatch_id, p.merchant_id)
    if m.kind == "dispute_open":
        raise HTTPException(409, "Resolve the dispute on the payment itself")
    m.status, m.resolution_note, m.resolved_by = "resolved", body.note, p.user_id
    ledger.audit(db, p.merchant_id, p.user_id, "mismatch.resolved", "mismatch", m.id, note=body.note)
    return {"id": m.id, "status": m.status}


# ---- demo provider simulator ------------------------------------------------------------------------
class SimulateIn(BaseModel):
    event_type: str = Field(default="payment.captured",
                            pattern=r"^(payment\.(authorized|captured|failed|dispute\.created)|refund\.processed)$")
    payment_request_id: str | None = None
    payment_id: str | None = None  # our payment id: reuse its provider payment (for authorise->capture, refund, dispute)
    amount_paise: int | None = Field(default=None, gt=0)
    currency: str = "INR"
    deliver_twice: bool = False
    tamper_signature: bool = False


def _demo_only():
    if not get_settings().demo_mode:
        raise HTTPException(404, "Demo tools are disabled")


@router.post("/demo/simulate-payment-event", dependencies=[Depends(_demo_only)])
def simulate_event(body: SimulateIn, p: Principal = Depends(can_write), db: Session = Depends(get_db)):
    """Acts as the demo provider: builds a signed event and delivers it through the same ingestion path
    as a real webhook. Simulated money only."""
    settings = get_settings()
    provider = DemoPaymentProvider(settings)
    account = db.scalar(select(MerchantProviderAccount).where(MerchantProviderAccount.merchant_id == p.merchant_id,
                                                              MerchantProviderAccount.provider == "demo"))
    amount, provider_payment_id, request_id = body.amount_paise, f"pay_demo_{uuid.uuid4().hex[:14]}", None
    if body.payment_id:
        pay = owned(db, Payment, body.payment_id, p.merchant_id)
        if pay.provider != "demo":
            raise HTTPException(422, "Only demo-provider payments can be simulated")
        provider_payment_id, amount, request_id = pay.provider_payment_id, amount or pay.amount_paise, pay.payment_request_id
    if body.payment_request_id:
        req = owned(db, PaymentRequest, body.payment_request_id, p.merchant_id)
        if req.provider != "demo" or req.status not in ("approved", "paid"):
            raise HTTPException(409, "Approve this payment request with the demo provider first")
        request_id, amount = req.id, amount or req.amount_paise
    if amount is None:
        raise HTTPException(422, "amount_paise is required when no payment request or payment is given")
    raw, sig, event_id = provider.build_event(event_type=body.event_type, account_id=account.account_id,
                                              payment_id=provider_payment_id, amount_paise=amount,
                                              currency=body.currency, payment_request_id=request_id)
    if body.tamper_signature:
        sig = "0" * 64
    deliveries = []
    for _ in range(2 if body.deliver_twice else 1):
        res = reconciliation.ingest_webhook(db, settings, "demo", raw, sig, event_id)
        deliveries.append({"http_status": res.http_status, "status": res.status, "detail": res.detail})
    payment = db.scalar(select(Payment).where(Payment.provider == "demo", Payment.provider_payment_id == provider_payment_id))
    invoice = db.get(Invoice, payment.intended_invoice_id) if payment and payment.intended_invoice_id else None
    return {"simulated": True, "event_id": event_id, "deliveries": deliveries,
            "payment": payment_dict(db, payment, customer_names(db, p.merchant_id)) if payment else None,
            "invoice": invoice_dict(db, invoice) if invoice else None}


@router.post("/demo/reset", dependencies=[Depends(_demo_only)])
def demo_reset(p: Principal = Depends(owner_only), db: Session = Depends(get_db)):
    reset(db, get_settings())
    return {"status": "reset", "detail": "Demo data restored. Sign in again."}
