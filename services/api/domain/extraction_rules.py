"""Deterministic review of an extracted invoice draft. The model's arithmetic is never trusted:
every line and total is recomputed here, and anything missing, conflicting or uncertain becomes an
issue the merchant must resolve (blocking) or acknowledge (warning) before an invoice can exist."""
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceDraft, Upload

from .money import format_inr, line_total_paise

EMPTY_PAYLOAD = {"customer_name": None, "invoice_date": None, "currency": "INR", "items": [],
                 "subtotal_paise": None, "tax_paise": None, "total_paise": None, "uncertain_fields": [],
                 "source_language": None, "needs_human_review": True}


def _issue(code: str, field: str, severity: str, message: str) -> dict:
    return {"code": code, "field": field, "severity": severity, "message": message}


def _is_paise(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def compute_lines(payload: dict) -> list[int | None]:
    """Per-line quantity x unit price; None where a line is incomplete."""
    out: list[int | None] = []
    for item in payload.get("items") or []:
        try:
            out.append(line_total_paise(item.get("quantity"), item["unit_price_paise"])
                       if _is_paise(item.get("unit_price_paise")) else None)
        except ValueError:
            out.append(None)
    return out


def _label(field: str) -> str:
    """'items[2].quantity' -> 'line 3 quantity'; 'subtotal_paise' -> 'subtotal'."""
    m = re.match(r"items\[(\d+)\]\.?(.*)", field)
    if m:
        return f"line {int(m.group(1)) + 1} {m.group(2).replace('_paise', '').replace('_', ' ')}".strip()
    return field.replace("_paise", "").replace("_", " ")


def compute_totals(payload: dict) -> dict | None:
    """Server-side totals from line items, or None if any line is incomplete."""
    lines = []
    for item in payload.get("items") or []:
        try:
            if not _is_paise(item.get("unit_price_paise")):
                return None
            lines.append(line_total_paise(item.get("quantity"), item["unit_price_paise"]))
        except ValueError:
            return None
    if not lines:
        return None
    tax = payload.get("tax_paise") if _is_paise(payload.get("tax_paise")) else 0
    return {"line_totals_paise": lines, "subtotal_paise": sum(lines), "tax_paise": tax,
            "total_paise": sum(lines) + tax}


def review_draft(db: Session, draft: InvoiceDraft) -> list[dict]:
    p = draft.payload or {}
    issues: list[dict] = []
    uncertain = set(p.get("uncertain_fields") or [])

    if not draft.customer_id and not (p.get("customer_name") or "").strip():
        issues.append(_issue("missing_customer", "customer_name", "blocking", "Buyer name is missing."))
    elif not draft.customer_id:
        issues.append(_issue("customer_not_linked", "customer_name", "warning",
                             "Buyer is not linked to an existing customer; approving will create a new customer."))
    try:
        date.fromisoformat(p.get("invoice_date") or "")
    except ValueError:
        issues.append(_issue("missing_date", "invoice_date", "blocking", "Invoice date is missing or unreadable."))
    if p.get("currency") != "INR":
        issues.append(_issue("currency", "currency", "blocking", "Only INR invoices are supported."))

    items = p.get("items") or []
    if not items:
        issues.append(_issue("no_items", "items", "blocking", "No line items were found."))
    for i, item in enumerate(items):
        prefix = f"items[{i}]"
        if not (item.get("description") or "").strip():
            issues.append(_issue("missing_description", f"{prefix}.description", "blocking", f"Line {i + 1}: description is missing."))
        computed = None
        try:
            if not _is_paise(item.get("unit_price_paise")):
                raise ValueError
            computed = line_total_paise(item.get("quantity"), item["unit_price_paise"])
        except ValueError:
            issues.append(_issue("missing_number", f"{prefix}", "blocking",
                                 f"Line {i + 1}: quantity or unit price is missing or unreadable."))
        stated = item.get("line_total_paise")
        if computed is not None and stated is not None and stated != computed:
            issues.append(_issue("line_total_conflict", f"{prefix}.line_total_paise", "blocking",
                                 f"Line {i + 1}: bill says {format_inr(stated)} but quantity × unit price is {format_inr(computed)}."))

    totals = compute_totals(p)
    if totals:
        if p.get("subtotal_paise") is not None and p["subtotal_paise"] != totals["subtotal_paise"]:
            issues.append(_issue("subtotal_conflict", "subtotal_paise", "blocking",
                                 f"Subtotal on the bill ({format_inr(p['subtotal_paise'])}) does not match the lines "
                                 f"({format_inr(totals['subtotal_paise'])})."))
        if p.get("total_paise") is None:
            issues.append(_issue("missing_total", "total_paise", "blocking", "Bill total is missing."))
        elif p["total_paise"] != totals["total_paise"]:
            issues.append(_issue("total_conflict", "total_paise", "blocking",
                                 f"Total on the bill ({format_inr(p['total_paise'])}) does not match lines + tax "
                                 f"({format_inr(totals['total_paise'])})."))
    if p.get("tax_paise") is None:
        issues.append(_issue("tax_undetermined", "tax_paise", "warning",
                             "Tax was not determined. GST is never inferred automatically; the invoice will be "
                             "issued with no tax line. Add tax manually if it applies."))
    for field in sorted(uncertain):
        if not any(i["field"] == field or i["field"].startswith(field + ".") for i in issues):
            issues.append(_issue("uncertain", field, "warning", f"Low-confidence reading of {_label(field)}; please check it against the bill."))

    upload = db.get(Upload, draft.upload_id)
    if upload:
        dup = db.scalar(select(InvoiceDraft).join(Upload, Upload.id == InvoiceDraft.upload_id).where(
            InvoiceDraft.merchant_id == draft.merchant_id, InvoiceDraft.id != draft.id,
            InvoiceDraft.status == "approved", Upload.sha256 == upload.sha256))
        if dup:
            issues.append(_issue("duplicate_file", "source_file_id", "warning",
                                 "This exact file was already approved as an invoice. Check for a duplicate bill."))
    if draft.customer_id and totals:
        try:
            same = db.scalar(select(Invoice).where(
                Invoice.merchant_id == draft.merchant_id, Invoice.customer_id == draft.customer_id,
                Invoice.invoice_date == date.fromisoformat(p.get("invoice_date") or ""),
                Invoice.total_paise == totals["total_paise"]))
        except ValueError:
            same = None
        if same:
            issues.append(_issue("possible_duplicate", "total_paise", "warning",
                                 f"Invoice {same.number} has the same customer, date and total."))
    return issues
