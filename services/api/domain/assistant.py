"""Read-only merchant assistant. Tools are tenant-scoped and audited; answers are rendered by
templates from tool output, so no language model ever produces a number. A model (if configured)
may only choose which tool to call."""
import difflib
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Customer, Invoice, Payment

from . import ledger, reports
from .money import format_inr

TOOLS = ("get_today_promises", "get_today_received", "get_outstanding", "get_customer_payments", "get_total_outstanding")


def find_customer(db: Session, merchant_id: str, text: str) -> Customer | None:
    customers = db.scalars(select(Customer).where(Customer.merchant_id == merchant_id)).all()
    low = text.lower()
    for c in sorted(customers, key=lambda c: -len(c.name)):
        if c.name.lower() in low:
            return c
    for c in customers:  # first distinctive word, e.g. "Murugan"
        if re.search(rf"\b{re.escape(c.name.split()[0].lower())}\b", low):
            return c
    words = re.findall(r"[a-z]+", low)
    for c in customers:
        if difflib.get_close_matches(c.name.split()[0].lower(), words, n=1, cutoff=0.8):
            return c
    return None


# --- tools (read-only) ------------------------------------------------------------------------
def get_today_promises(db: Session, merchant_id: str, day: date) -> dict:
    r = reports.today_report(db, merchant_id, day)
    return {"date": r["date"], "expected_today_paise": r["expected_today_paise"], "promises": r["promises_due_today"]}


def get_today_received(db: Session, merchant_id: str, day: date) -> dict:
    r = reports.today_report(db, merchant_id, day)
    return {"date": r["date"], **{k: v for k, v in r["received"].items()}}


def get_outstanding(db: Session, merchant_id: str, customer: Customer) -> dict:
    invoices = db.scalars(select(Invoice).where(Invoice.merchant_id == merchant_id,
                                                Invoice.customer_id == customer.id).order_by(Invoice.invoice_date)).all()
    rows = [{"invoice_id": i.id, "number": i.number, "total_paise": i.total_paise, "due_paise": ledger.invoice_due(db, i)}
            for i in invoices]
    return {"customer_id": customer.id, "customer_name": customer.name,
            "outstanding_paise": sum(r["due_paise"] for r in rows), "invoices": [r for r in rows if r["due_paise"] > 0]}


def get_customer_payments(db: Session, merchant_id: str, customer: Customer) -> dict:
    names = {customer.id: customer.name}
    payments = db.scalars(select(Payment).where(Payment.merchant_id == merchant_id, Payment.customer_id == customer.id)
                          .order_by(Payment.received_at)).all()
    totals: dict[str, int] = {}
    for p in payments:
        totals[p.state] = totals.get(p.state, 0) + p.amount_paise
    return {"customer_id": customer.id, "customer_name": customer.name, "totals_by_state": totals,
            "payments": [reports.payment_brief(p, names) for p in payments]}


# --- routing + rendering ------------------------------------------------------------------------
def route(question: str) -> str | None:
    q = question.lower()
    if re.search(r"\b(promis|agreed|agree|commit|said they|going to pay|will pay)", q):
        return "get_today_promises"
    if re.search(r"\b(cash in|cash-in|received|collected|came in|got today|receipts?)\b", q):
        return "get_today_received"
    if re.search(r"\b(paid|pay|payments?)\b", q):
        return "get_customer_payments"
    if re.search(r"\b(owe|owes|outstanding|pending|balance|due)\b", q):
        return "get_outstanding"
    return None


def _sim(mode_totals: dict) -> str:
    return " (demo provider: simulated, no real money moved)" if mode_totals.get("simulated") else ""


def answer(db: Session, merchant_id: str, question: str, day: date, tool: str | None = None,
           routed_by: str = "rules") -> dict:
    tool = tool if tool in TOOLS else route(question)
    customer = find_customer(db, merchant_id, question)
    if tool == "get_outstanding" and customer is None:
        tool = "get_total_outstanding"
    if tool == "get_customer_payments" and customer is None:
        tool = "get_today_received"

    if tool == "get_today_promises":
        data = get_today_promises(db, merchant_id, day)
        if not data["promises"]:
            text = "No customer has an open promise to pay today."
        else:
            parts = [f"{p['customer_name']} {format_inr(p['amount_paise'])} by {p['method']}" for p in data["promises"]]
            text = (f"{len(parts)} promise(s) for today, {format_inr(data['expected_today_paise'])} expected: "
                    + "; ".join(parts) + ". These are stated intentions, not receipts.")
    elif tool == "get_today_received":
        data = get_today_received(db, merchant_id, day)
        text = (f"Confirmed cash in today is {format_inr(data['confirmed_total_paise'])}: "
                f"{format_inr(data['provider_verified_paise'])} provider-verified{_sim(data['provider_verified_by_mode'])} "
                f"and {format_inr(data['merchant_confirmed_paise'])} merchant-confirmed.")
        if data["unverified_claims_paise"]:
            text += f" A further {format_inr(data['unverified_claims_paise'])} is claimed but unverified and is not counted."
    elif tool == "get_customer_payments":
        data = get_customer_payments(db, merchant_id, customer)
        t = data["totals_by_state"]
        sim = any(p["mode"] == "simulated" and p["state"] == "provider_verified" for p in data["payments"])
        text = (f"{customer.name} has paid {format_inr(t.get('provider_verified', 0))} provider-verified"
                f"{' (demo provider: simulated)' if sim else ''} and {format_inr(t.get('merchant_confirmed', 0))} merchant-confirmed.")
        if t.get("manual_unverified"):
            text += f" {format_inr(t['manual_unverified'])} more is claimed but unverified."
        if t.get("disputed"):
            text += f" {format_inr(t['disputed'])} is disputed."
        text += f" Outstanding now: {format_inr(get_outstanding(db, merchant_id, customer)['outstanding_paise'])}."
    elif tool == "get_outstanding":
        data = get_outstanding(db, merchant_id, customer)
        inv = ", ".join(f"{i['number']} {format_inr(i['due_paise'])}" for i in data["invoices"]) or "nothing open"
        text = f"{customer.name} owes {format_inr(data['outstanding_paise'])} ({inv})."
    elif tool == "get_total_outstanding":
        data = {"outstanding_paise": reports.total_outstanding(db, merchant_id)}
        text = f"Total outstanding across all customers is {format_inr(data['outstanding_paise'])}."
    else:
        data = {}
        text = ("I can answer read-only questions about today's promises, confirmed cash in, a customer's payments "
                "or what a customer owes. Try: 'Who agreed to pay today?'")
    ledger.audit(db, merchant_id, "merchant_assistant", "assistant.query", "assistant", tool or "none",
                 question=question[:500], routed_by=routed_by)
    return {"answer": text, "tool": tool, "routed_by": routed_by, "evidence": data,
            "as_of": clock.iso(clock.now()), "read_only": True}
