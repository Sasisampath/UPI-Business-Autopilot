"""Transaction-safe receivables ledger.

Invoice due is never stored: it is `total - sum(payment_allocations)`, where allocations are
immutable (+allocation / -compensating reversal) and only exist for confirmed funds.
Callers own the DB transaction; these functions lock the rows they depend on.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.models import AuditEvent, Invoice, Mismatch, Payment, PaymentAllocation

# States whose funds may be allocated to invoices.
CONFIRMED_STATES = {"provider_verified", "merchant_confirmed"}


class LedgerError(Exception):
    pass


def audit(db: Session, merchant_id: str | None, actor: str, action: str, entity_type: str, entity_id: str, **data) -> None:
    db.add(AuditEvent(merchant_id=merchant_id, actor=actor, action=action, entity_type=entity_type,
                      entity_id=entity_id, data=data, created_at=clock.now()))


def open_mismatch(db: Session, merchant_id: str, kind: str, detail: str, payment_id: str | None = None,
                  webhook_event_id: str | None = None) -> Mismatch:
    m = Mismatch(merchant_id=merchant_id, kind=kind, detail=detail, payment_id=payment_id,
                 webhook_event_id=webhook_event_id)
    db.add(m)
    return m


def invoice_allocated(db: Session, invoice_id: str) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(PaymentAllocation.amount_paise), 0))
                         .where(PaymentAllocation.invoice_id == invoice_id)))


def invoice_due(db: Session, invoice: Invoice) -> int:
    return invoice.total_paise - invoice_allocated(db, invoice.id)


def payment_allocated(db: Session, payment_id: str) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(PaymentAllocation.amount_paise), 0))
                         .where(PaymentAllocation.payment_id == payment_id)))


def payment_unallocated(db: Session, payment: Payment) -> int:
    if payment.state not in CONFIRMED_STATES:
        return 0
    return payment.amount_paise - payment_allocated(db, payment.id)


def invoice_status(total: int, due: int) -> str:
    if due <= 0:
        return "paid"
    return "unpaid" if due == total else "partially_paid"


def _lock(db: Session, model, row_id: str):
    # SELECT ... FOR UPDATE on PostgreSQL; SQLite serialises writers so the hint is a no-op there.
    return db.execute(select(model).where(model.id == row_id).with_for_update()).scalar_one()


def allocate(db: Session, payment: Payment, invoice: Invoice, amount_paise: int, actor: str,
             reason: str | None = None) -> PaymentAllocation:
    """Apply confirmed funds to an invoice. Refuses over-allocation on either side."""
    payment = _lock(db, Payment, payment.id)
    invoice = _lock(db, Invoice, invoice.id)
    if payment.merchant_id != invoice.merchant_id:
        raise LedgerError("payment and invoice belong to different merchants")
    if payment.state not in CONFIRMED_STATES:
        raise LedgerError(f"payment is {payment.state}; only confirmed funds can be allocated")
    if payment.currency != invoice.currency:
        raise LedgerError("currency mismatch")
    if not isinstance(amount_paise, int) or amount_paise <= 0:
        raise LedgerError("allocation amount must be a positive integer of paise")
    if amount_paise > payment.amount_paise - payment_allocated(db, payment.id):
        raise LedgerError("allocation exceeds the payment's unallocated confirmed funds")
    if amount_paise > invoice_due(db, invoice):
        raise LedgerError("allocation exceeds the invoice's outstanding balance")
    entry = PaymentAllocation(merchant_id=invoice.merchant_id, payment_id=payment.id, invoice_id=invoice.id,
                              amount_paise=amount_paise, kind="allocation", reason=reason, created_by=actor)
    db.add(entry)
    db.flush()
    audit(db, invoice.merchant_id, actor, "allocation.created", "invoice", invoice.id,
          payment_id=payment.id, amount_paise=amount_paise, due_after_paise=invoice_due(db, invoice))
    return entry


def reverse_allocations(db: Session, payment: Payment, actor: str, reason: str) -> int:
    """Write compensating negative entries for everything this payment currently covers."""
    payment = _lock(db, Payment, payment.id)
    rows = db.execute(select(PaymentAllocation.invoice_id, func.sum(PaymentAllocation.amount_paise))
                      .where(PaymentAllocation.payment_id == payment.id)
                      .group_by(PaymentAllocation.invoice_id)).all()
    reversed_total = 0
    for invoice_id, net in rows:
        net = int(net)
        if net <= 0:
            continue
        _lock(db, Invoice, invoice_id)
        db.add(PaymentAllocation(merchant_id=payment.merchant_id, payment_id=payment.id, invoice_id=invoice_id,
                                 amount_paise=-net, kind="reversal", reason=reason, created_by=actor))
        audit(db, payment.merchant_id, actor, "allocation.reversed", "invoice", invoice_id,
              payment_id=payment.id, amount_paise=net, reason=reason)
        reversed_total += net
    db.flush()
    return reversed_total


def allocate_available(db: Session, payment: Payment, invoice: Invoice, actor: str, reason: str) -> int:
    """Allocate as much of the payment as the invoice can take. Returns the amount applied."""
    amount = min(payment_unallocated(db, payment), invoice_due(db, invoice))
    if amount > 0:
        allocate(db, payment, invoice, amount, actor, reason)
    return max(amount, 0)


def mark_disputed(db: Session, payment: Payment, actor: str, reason: str) -> None:
    if payment.state in ("disputed", "reversed"):
        return
    payment.state_before_dispute = payment.state
    reverse_allocations(db, payment, actor, f"disputed: {reason}")
    payment.state = "disputed"
    audit(db, payment.merchant_id, actor, "payment.disputed", "payment", payment.id, reason=reason)
    open_mismatch(db, payment.merchant_id, "dispute_open", f"Receipt disputed: {reason}", payment_id=payment.id)


def mark_reversed(db: Session, payment: Payment, actor: str, reason: str) -> None:
    if payment.state == "reversed":
        return
    reverse_allocations(db, payment, actor, f"reversed: {reason}")
    payment.state = "reversed"
    audit(db, payment.merchant_id, actor, "payment.reversed", "payment", payment.id, reason=reason)


def resolve_dispute(db: Session, payment: Payment, outcome: str, actor: str, note: str) -> None:
    """outcome 'upheld' restores the receipt (and re-applies it where the invoice still has room);
    'rejected' turns it into a reversal."""
    if payment.state != "disputed":
        raise LedgerError("payment is not disputed")
    if outcome == "upheld":
        payment.state = payment.state_before_dispute or "manual_unverified"
        audit(db, payment.merchant_id, actor, "payment.dispute_upheld", "payment", payment.id, note=note)
        if payment.state in CONFIRMED_STATES and payment.intended_invoice_id:
            invoice = db.get(Invoice, payment.intended_invoice_id)
            allocate_available(db, payment, invoice, actor, "re-applied after dispute upheld")
            if payment_unallocated(db, payment) > 0:
                open_mismatch(db, payment.merchant_id, "unallocated_funds",
                              "Restored receipt could not be fully re-applied to its invoice.", payment.id)
    elif outcome == "rejected":
        payment.state = "reversed"
        audit(db, payment.merchant_id, actor, "payment.dispute_rejected", "payment", payment.id, note=note)
    else:
        raise LedgerError("outcome must be 'upheld' or 'rejected'")
    for m in db.scalars(select(Mismatch).where(Mismatch.payment_id == payment.id, Mismatch.kind == "dispute_open",
                                               Mismatch.status == "open")):
        m.status, m.resolution_note, m.resolved_by = "resolved", f"dispute {outcome}: {note}", actor
