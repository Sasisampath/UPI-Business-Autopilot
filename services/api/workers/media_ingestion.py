"""Media ingestion jobs: bill extraction and (optional) WhatsApp media retrieval."""
import hashlib
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.extraction import ExtractionError, get_extraction_adapter
from adapters.whatsapp import MetaCloudWhatsAppAdapter
from app import clock
from app.config import Settings
from app.models import AuditEvent, Customer, InvoiceDraft, Upload
from domain import ledger
from domain.extraction_rules import EMPTY_PAYLOAD

_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}


def _gemini_reads_today(db: Session, merchant_id: str) -> int:
    start, end = clock.ist_day_bounds(clock.today_ist())
    rows = db.scalars(select(AuditEvent).where(AuditEvent.merchant_id == merchant_id, AuditEvent.action == "draft.extracted",
                                               AuditEvent.created_at >= start, AuditEvent.created_at < end))
    return sum(1 for a in rows if (a.data or {}).get("requested") == "gemini")


def run_extraction(db: Session, settings: Settings, upload: Upload, actor: str, mode: str = "auto",
                   draft: InvoiceDraft | None = None) -> InvoiceDraft:
    """Create (or re-read into) a reviewable draft. Never creates an invoice.

    A failed read is recorded as a failure: the draft is left empty for typing by hand,
    `extraction_source` is 'manual' and `extraction_error` says what went wrong. It is never
    silently replaced by sample data; the simulated fallback is used only when asked for
    (mode='simulated') or when no Gemini key exists at all (mode='auto')."""
    adapter = get_extraction_adapter(settings, mode)
    source, error, code = adapter.source, None, None
    try:
        if adapter.source == "gemini" and settings.gemini_daily_limit and _gemini_reads_today(db, upload.merchant_id) >= settings.gemini_daily_limit:
            raise ExtractionError("daily_limit", "Today's limit for AI bill reading has been reached. Type the bill in by hand, or try again tomorrow.")
        if not upload.storage_path:
            raise ExtractionError("file_missing", "The uploaded file is not available yet.")
        with open(upload.storage_path, "rb") as fh:
            payload = adapter.extract(fh.read(), upload.content_type, clock.today_ist().isoformat())
    except ExtractionError as exc:
        payload, source, error, code = dict(EMPTY_PAYLOAD), "manual", exc.message, exc.code
    except Exception:  # anything unexpected is still a reported failure, with no internals leaked
        payload, source, error, code = dict(EMPTY_PAYLOAD), "manual", "The bill could not be read. Type it in by hand, or try again.", "unexpected"
    payload["source_file_id"] = upload.id
    payload["needs_human_review"] = True
    name = (payload.get("customer_name") or "").strip().lower()
    customer = db.scalar(select(Customer).where(Customer.merchant_id == upload.merchant_id,
                                                func.lower(Customer.name) == name)) if name else None
    if draft is None:
        draft = InvoiceDraft(merchant_id=upload.merchant_id, upload_id=upload.id, extraction_source=source, payload=payload)
        db.add(draft)
    draft.extraction_source, draft.extraction_error, draft.payload = source, error, payload
    draft.customer_id = customer.id if customer else None
    db.flush()
    ledger.audit(db, upload.merchant_id, actor, "draft.extracted", "draft", draft.id, source=source,
                 requested=adapter.source, outcome="failed" if error else "ok", error_code=code, upload_id=upload.id)
    return draft


def fetch_whatsapp_media(upload_id: str) -> None:
    """Background job: download inbound WhatsApp media for a merchant's bill and create a draft."""
    from app.config import get_settings
    from app.db import SessionLocal

    settings = get_settings()
    if not settings.whatsapp_access_token:
        return
    with SessionLocal() as db:
        upload = db.get(Upload, upload_id)
        if upload is None or upload.storage_path or not upload.external_media_id:
            return
        data, mime = MetaCloudWhatsAppAdapter(settings).download_media(upload.external_media_id)
        if mime not in _EXT or len(data) > settings.max_upload_bytes:
            return
        folder = os.path.join(settings.upload_dir, upload.merchant_id)
        os.makedirs(folder, exist_ok=True)
        upload.storage_path = os.path.join(folder, upload.id + _EXT[mime])
        upload.content_type, upload.size_bytes, upload.sha256 = mime, len(data), hashlib.sha256(data).hexdigest()
        with open(upload.storage_path, "wb") as fh:
            fh.write(data)
        run_extraction(db, settings, upload, actor="whatsapp_inbound")
        db.commit()
