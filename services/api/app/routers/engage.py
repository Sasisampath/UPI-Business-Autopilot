"""Promises, conversations (demo inbox + gated outbound), reports, assistant, voice and integrations."""
import hmac
import json
import re
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from adapters import assistant_router
from adapters.payments import RazorpayProvider
from adapters.voice import get_voice_adapter
from adapters.whatsapp import MetaCloudWhatsAppAdapter
from domain import assistant, intents, ledger, outbound_policy, reports
from workers.media_ingestion import fetch_whatsapp_media

from .. import clock
from ..auth import Principal, can_write, current_principal, owned
from ..config import get_settings
from ..db import get_db
from ..models import (ContactEvent, Customer, Invoice, MerchantProviderAccount, Message, Promise, Upload, User, WebhookEvent)
from .core import audit_dicts, customer_names
from .money import _demo_only, _raw

router = APIRouter(prefix="/v1")


# ---- promises -----------------------------------------------------------------------------------
class PromiseItem(BaseModel):
    amount_paise: int = Field(gt=0, le=10**12)
    promised_date: date
    method: str = Field(pattern="^(cash|upi|other)$")
    pickup_window: str | None = Field(default=None, max_length=100)


class PromisesIn(BaseModel):
    customer_id: str
    invoice_id: str | None = None
    items: list[PromiseItem] = Field(min_length=1, max_length=12)
    evidence_source: str = Field(pattern="^(demo_inbox|whatsapp|in_person|phone_call)$")
    evidence_text: str = Field(min_length=3, max_length=2000)
    source_message_id: str | None = None
    customer_confirmed: bool


class PromisePatch(BaseModel):
    amount_paise: int | None = Field(default=None, gt=0)
    promised_date: date | None = None
    method: str | None = Field(default=None, pattern="^(cash|upi|other)$")
    pickup_window: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, pattern="^(open|kept|broken|cancelled)$")


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/promises/parse")
def parse_promises(body: ParseIn, p: Principal = Depends(current_principal)):
    """Proposals only, from the customer's own words. Nothing is saved."""
    return {"proposals": intents.parse_commitments(body.text, clock.today_ist()), "saved": False}


@router.get("/promises")
def list_promises(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    names = customer_names(db, p.merchant_id)
    rows = db.scalars(select(Promise).where(Promise.merchant_id == p.merchant_id)
                      .order_by(Promise.promised_date, Promise.created_at)).all()
    return [reports.promise_dict(x, names) for x in rows]


@router.post("/promises", status_code=201)
def create_promises(body: PromisesIn, p: Principal = Depends(can_write), db: Session = Depends(get_db)):
    """Record customer-stated commitments with evidence. A promise is never a receipt and never changes a balance."""
    if not body.customer_confirmed:
        raise HTTPException(422, "Only commitments the customer explicitly stated can be recorded (customer_confirmed must be true)")
    owned(db, Customer, body.customer_id, p.merchant_id)
    if body.invoice_id and owned(db, Invoice, body.invoice_id, p.merchant_id).customer_id != body.customer_id:
        raise HTTPException(422, "Invoice does not belong to this customer")
    simulated = False
    if body.source_message_id:
        msg = owned(db, Message, body.source_message_id, p.merchant_id)
        if msg.customer_id != body.customer_id or msg.direction != "inbound":
            raise HTTPException(422, "Evidence message must be an inbound message from this customer")
        simulated = msg.simulated
    names = customer_names(db, p.merchant_id)
    out = []
    for item in body.items:
        pr = Promise(merchant_id=p.merchant_id, customer_id=body.customer_id, invoice_id=body.invoice_id,
                     evidence_source=body.evidence_source, evidence_text=body.evidence_text,
                     source_message_id=body.source_message_id, simulated=simulated, recorded_by=p.user_id,
                     **item.model_dump())
        db.add(pr)
        db.flush()
        ledger.audit(db, p.merchant_id, p.user_id, "promise.recorded", "promise", pr.id, amount_paise=pr.amount_paise,
                     promised_date=pr.promised_date.isoformat(), method=pr.method, evidence_source=pr.evidence_source)
        out.append(reports.promise_dict(pr, names))
    return out


@router.patch("/promises/{promise_id}")
def update_promise(promise_id: str, body: PromisePatch, p: Principal = Depends(can_write), db: Session = Depends(get_db)):
    pr = owned(db, Promise, promise_id, p.merchant_id)
    changes = body.model_dump(exclude_unset=True)
    before = {k: (getattr(pr, k).isoformat() if isinstance(getattr(pr, k), date) else getattr(pr, k)) for k in changes}
    for k, v in changes.items():
        setattr(pr, k, v)
    ledger.audit(db, p.merchant_id, p.user_id, "promise.updated", "promise", pr.id, before=before,
                 after={k: (v.isoformat() if isinstance(v, date) else v) for k, v in changes.items()})
    db.flush()
    return reports.promise_dict(pr, customer_names(db, p.merchant_id))


# ---- conversations --------------------------------------------------------------------------------
class InboundIn(BaseModel):
    customer_id: str
    body: str = Field(min_length=1, max_length=2000)


class OutboundDraftIn(BaseModel):
    customer_id: str
    channel: str = Field(default="demo_inbox", pattern="^(demo_inbox|whatsapp)$")
    message_type: str = Field(max_length=40)
    body: str = Field(min_length=1, max_length=2000)


def message_dict(m: Message) -> dict:
    return {"id": m.id, "customer_id": m.customer_id, "direction": m.direction, "channel": m.channel,
            "message_type": m.message_type, "body": m.body, "status": m.status, "block_reason": m.block_reason,
            "simulated": m.simulated, "created_at": clock.iso(m.created_at)}


@router.get("/customers/{customer_id}/messages")
def customer_messages(customer_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    owned(db, Customer, customer_id, p.merchant_id)
    rows = db.scalars(select(Message).where(Message.merchant_id == p.merchant_id, Message.customer_id == customer_id)
                      .order_by(Message.created_at, Message.id)).all()
    return [message_dict(m) for m in rows]


@router.post("/demo/inbox/inbound", status_code=201, dependencies=[Depends(_demo_only)])
def simulate_inbound(body: InboundIn, p: Principal = Depends(can_write), db: Session = Depends(get_db)):
    """Inbox simulator: stores a customer reply flagged `simulated`. Proposed commitments are returned for
    the merchant to confirm; none are saved here."""
    owned(db, Customer, body.customer_id, p.merchant_id)
    m = Message(merchant_id=p.merchant_id, customer_id=body.customer_id, direction="inbound", channel="demo_inbox",
                body=body.body, status="received", simulated=True, created_by=p.user_id)
    db.add(m)
    db.flush()
    db.add(ContactEvent(merchant_id=p.merchant_id, customer_id=body.customer_id, kind="replied", channel="demo_inbox",
                        message_id=m.id, simulated=True))
    return {"message": message_dict(m), "proposals": intents.parse_commitments(body.body, clock.today_ist())}


@router.post("/messages/drafts", status_code=201)
def draft_outbound(body: OutboundDraftIn, p: Principal = Depends(can_write), db: Session = Depends(get_db)):
    """Prepare an outbound message. It is a draft until a merchant approves it and it passes the policy gate."""
    owned(db, Customer, body.customer_id, p.merchant_id)
    allowed, reason = outbound_policy.check_outbound(db, get_settings(), p.merchant_id, body.customer_id, body.channel,
                                                     body.message_type)
    m = Message(merchant_id=p.merchant_id, customer_id=body.customer_id, direction="outbound", channel=body.channel,
                message_type=body.message_type, body=body.body, status="draft", created_by=p.user_id,
                simulated=body.channel == "demo_inbox")
    db.add(m)
    db.flush()
    ledger.audit(db, p.merchant_id, p.user_id, "message.drafted", "message", m.id, channel=body.channel, message_type=body.message_type)
    return {"message": message_dict(m), "policy": {"allowed": allowed, "reason": reason}}


@router.post("/messages/{message_id}/approve")
def approve_outbound(message_id: str, p: Principal = Depends(can_write), db: Session = Depends(get_db)):
    m = owned(db, Message, message_id, p.merchant_id)
    if m.direction != "outbound" or m.status != "draft":
        raise HTTPException(409, "Only outbound drafts can be approved")
    allowed, reason = outbound_policy.check_outbound(db, get_settings(), p.merchant_id, m.customer_id, m.channel, m.message_type)
    if allowed:
        m.status, m.approved_by = "sent_simulated", p.user_id
        db.add(ContactEvent(merchant_id=p.merchant_id, customer_id=m.customer_id, kind="contacted", channel=m.channel,
                            message_id=m.id, simulated=True))
    else:
        m.status, m.block_reason = "blocked", reason
    ledger.audit(db, p.merchant_id, p.user_id, f"message.{m.status}", "message", m.id, reason=reason)
    return {"message": message_dict(m), "policy": {"allowed": allowed, "reason": reason}}


# ---- WhatsApp Cloud API webhook (inbound only) ------------------------------------------------------
def _digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")[-10:]


@router.get("/webhooks/whatsapp")
def whatsapp_verify(mode: str = Query(None, alias="hub.mode"), token: str = Query(None, alias="hub.verify_token"),
                    challenge: str = Query(None, alias="hub.challenge")):
    expected = get_settings().whatsapp_verify_token
    if mode == "subscribe" and expected and token and hmac.compare_digest(expected, token):
        return PlainTextResponse(challenge or "")
    raise HTTPException(403, "Verification failed")


@router.post("/webhooks/whatsapp")
def whatsapp_webhook(request: Request, background: BackgroundTasks, raw: bytes = Depends(_raw), db: Session = Depends(get_db)):
    adapter = MetaCloudWhatsAppAdapter(get_settings())
    if not adapter.verify_signature(raw, request.headers.get("x-hub-signature-256")):
        return JSONResponse({"status": "rejected", "detail": "invalid signature"}, status_code=401)
    stored = 0
    for msg in adapter.parse_messages(json.loads(raw)):
        account = db.scalar(select(MerchantProviderAccount).where(MerchantProviderAccount.provider == "whatsapp",
                                                                  MerchantProviderAccount.account_id == str(msg["phone_number_id"])))
        if account is None or not msg["id"]:
            continue
        try:
            with db.begin_nested():
                db.add(WebhookEvent(merchant_id=account.merchant_id, provider="whatsapp", event_id=msg["id"],
                                    event_type=f"message.{msg['type']}", signature_valid=True, status="processed",
                                    raw_body=json.dumps(msg)))
                db.flush()
        except IntegrityError:
            continue  # already ingested
        sender = _digits(msg["from"])
        user = next((u for u in db.scalars(select(User).where(User.merchant_id == account.merchant_id))
                     if u.phone and _digits(u.phone) == sender), None)
        customer = next((c for c in db.scalars(select(Customer).where(Customer.merchant_id == account.merchant_id))
                         if c.phone and _digits(c.phone) == sender), None)
        if user and msg["media_id"] and msg["type"] in ("image", "document"):
            up = Upload(merchant_id=account.merchant_id, filename=msg["filename"] or "whatsapp-bill",
                        content_type=msg["mime_type"] or "application/octet-stream", size_bytes=0, sha256="",
                        source="whatsapp", external_media_id=msg["media_id"], created_by=user.id)
            db.add(up)
            db.flush()
            background.add_task(fetch_whatsapp_media, up.id)  # media retrieval is a separate job
            stored += 1
        elif customer and msg["text"]:
            m = Message(merchant_id=account.merchant_id, customer_id=customer.id, direction="inbound", channel="whatsapp",
                        body=msg["text"][:2000], status="received", simulated=False)
            db.add(m)
            db.flush()
            db.add(ContactEvent(merchant_id=account.merchant_id, customer_id=customer.id, kind="replied",
                                channel="whatsapp", message_id=m.id, simulated=False))
            stored += 1
    return {"status": "ok", "stored": stored}


# ---- reports, assistant, voice --------------------------------------------------------------------
@router.get("/reports/today")
def report_today(day: date | None = Query(default=None, alias="date"), p: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    r = reports.today_report(db, p.merchant_id, day or clock.today_ist())
    r["demo_mode"] = get_settings().demo_mode
    return r


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.post("/assistant/ask")
def ask(body: AskIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    tool = assistant_router.choose_tool(get_settings(), body.question, assistant.TOOLS)
    return assistant.answer(db, p.merchant_id, body.question, clock.today_ist(), tool=tool,
                            routed_by="gemini" if tool else "rules")


@router.get("/voice/session")
def voice_session(p: Principal = Depends(current_principal)):
    try:
        return get_voice_adapter(get_settings()).session()
    except Exception as exc:
        raise HTTPException(502, f"Voice provider error: {type(exc).__name__}") from exc


class VoiceToolIn(BaseModel):
    customer_name: str | None = Field(default=None, max_length=200)


def _voice_merchant(x_voice_tool_secret: str | None = Header(default=None)) -> str:
    """ElevenLabs server tools authenticate with a shared secret header and are pinned to one merchant."""
    s = get_settings()
    if not (s.voice_tool_secret and s.voice_tool_merchant_id and x_voice_tool_secret
            and hmac.compare_digest(s.voice_tool_secret, x_voice_tool_secret)):
        raise HTTPException(401, "Voice tools are not configured or the secret is wrong")
    return s.voice_tool_merchant_id


@router.post("/voice-tools/customer-balance")
def voice_customer_balance(body: VoiceToolIn, merchant_id: str = Depends(_voice_merchant), db: Session = Depends(get_db)):
    """Strictly read-only, limited fields."""
    customer = assistant.find_customer(db, merchant_id, body.customer_name or "")
    if customer is None:
        return {"found": False, "message": "No matching customer."}
    res = assistant.answer(db, merchant_id, f"outstanding {customer.name}", clock.today_ist(), tool="get_outstanding", routed_by="voice_tool")
    return {"found": True, "customer_name": customer.name, "outstanding_paise": res["evidence"]["outstanding_paise"],
            "spoken_answer": res["answer"]}


@router.post("/voice-tools/today-promises")
def voice_today_promises(merchant_id: str = Depends(_voice_merchant), db: Session = Depends(get_db)):
    res = assistant.answer(db, merchant_id, "promises today", clock.today_ist(), tool="get_today_promises", routed_by="voice_tool")
    return {"spoken_answer": res["answer"], "expected_today_paise": res["evidence"]["expected_today_paise"]}


@router.post("/voice-tools/today-received")
def voice_today_received(merchant_id: str = Depends(_voice_merchant), db: Session = Depends(get_db)):
    res = assistant.answer(db, merchant_id, "received today", clock.today_ist(), tool="get_today_received", routed_by="voice_tool")
    return {"spoken_answer": res["answer"], "confirmed_total_paise": res["evidence"]["confirmed_total_paise"]}


# ---- integrations + audit -------------------------------------------------------------------------
@router.get("/integrations")
def integrations(p: Principal = Depends(current_principal)):
    s = get_settings()
    rzp = RazorpayProvider(s)
    wa = MetaCloudWhatsAppAdapter(s)
    eleven = bool(s.elevenlabs_api_key and s.elevenlabs_agent_id)
    return {"demo_mode": s.demo_mode, "items": [
        {"key": "payments_demo", "name": "Demo payment provider", "label": "simulated", "active": True,
         "detail": "Signed mock webhooks through the real reconciliation path. No real money moves."},
        {"key": "payments_razorpay", "name": "Razorpay", "label": "test mode" if rzp.configured else "not configured",
         "active": rzp.configured,
         "detail": "Payment Links + signed webhook, test keys only (live keys are refused). Not exercised against a real account in this build."},
        {"key": "extraction", "name": "Bill extraction", "label": "live" if s.gemini_api_key else "simulated", "active": True,
         "detail": f"Gemini ({s.gemini_model}) reads the uploaded bill." if s.gemini_api_key else
                   "No GEMINI_API_KEY: a fixed sample draft is returned. It does not read your file."},
        {"key": "assistant", "name": "Merchant assistant", "label": "live", "active": True,
         "detail": ("Gemini picks the tool; " if s.gemini_api_key else "Rule-based routing; ") +
                   "answers always come from read-only ledger tools."},
        {"key": "voice", "name": "Merchant voice", "label": "live" if eleven else "simulated", "active": True,
         "detail": "ElevenLabs browser agent (not exercised against a real account in this build)." if eleven else
                   "Browser speech recognition/synthesis over the text assistant. No ElevenLabs credentials."},
        {"key": "whatsapp_demo", "name": "Customer inbox simulator", "label": "simulated", "active": True,
         "detail": "Messages stay in this app and are flagged simulated."},
        {"key": "whatsapp_inbound", "name": "WhatsApp Cloud API (inbound)", "label": "live" if wa.configured else "not configured",
         "active": wa.configured, "detail": "Signature-checked webhook for merchant bill media and customer replies. Not exercised against a real account in this build."},
        {"key": "whatsapp_outbound", "name": "WhatsApp outbound to customers", "label": "disabled", "active": False,
         "detail": "No live send is implemented. Collection/overdue reminders are always refused. "
                   f"OUTBOUND_POLICY_APPROVED={'true' if s.outbound_policy_approved else 'false'}."},
        {"key": "outbound_calls", "name": "Outbound AI calls to customers", "label": "disabled", "active": False,
         "detail": "Not built."},
        {"key": "storage", "name": "File storage", "label": "local", "active": True,
         "detail": "Uploads are stored unencrypted on local disk for the demo. Use encrypted object storage in production."},
        {"key": "database", "name": "Database", "label": "sqlite" if s.database_url.startswith("sqlite") else "postgresql",
         "active": True, "detail": "Alembic migrations; set DATABASE_URL for PostgreSQL."},
    ]}


@router.get("/audit")
def audit_log(entity_type: str, entity_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return audit_dicts(db, p.merchant_id, entity_type, [entity_id])
