"""Media ingestion jobs: bill extraction and (optional) WhatsApp media retrieval."""
import hashlib
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.extraction import get_extraction_adapter
from adapters.whatsapp import MetaCloudWhatsAppAdapter
from app import clock
from app.config import Settings
from app.models import Customer, InvoiceDraft, Upload
from domain import ledger
from domain.extraction_rules import EMPTY_PAYLOAD

_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}


def run_extraction(db: Session, settings: Settings, upload: Upload, actor: str) -> InvoiceDraft:
    """Create a reviewable draft from an upload. Never creates an invoice."""
    adapter = get_extraction_adapter(settings)
    source, error = adapter.source, None
    try:
        with open(upload.storage_path, "rb") as fh:
            payload = adapter.extract(fh.read(), upload.content_type, clock.today_ist().isoformat())
    except Exception as exc:  # extraction is best-effort; the merchant can still key the bill in by hand
        payload, source, error = dict(EMPTY_PAYLOAD), "manual", f"Extraction failed ({type(exc).__name__}). Enter the bill manually."
    payload["source_file_id"] = upload.id
    payload["needs_human_review"] = True
    name = (payload.get("customer_name") or "").strip().lower()
    customer = db.scalar(select(Customer).where(Customer.merchant_id == upload.merchant_id,
                                                func.lower(Customer.name) == name)) if name else None
    draft = InvoiceDraft(merchant_id=upload.merchant_id, upload_id=upload.id, extraction_source=source,
                         extraction_error=error, payload=payload, customer_id=customer.id if customer else None)
    db.add(draft)
    db.flush()
    ledger.audit(db, upload.merchant_id, actor, "draft.extracted", "draft", draft.id, source=source, upload_id=upload.id)
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
