"""Balances, partial payments, webhook idempotency/ordering/signature, over-allocation, disputes, tenancy."""
import pytest
from sqlalchemy import func, select

from adapters.payments import DemoPaymentProvider
from app.models import Invoice, Payment, PaymentAllocation
from domain import ledger
from domain.money import format_inr, line_total_paise

INV1 = "inv_demo_0001"


def due(client, h, invoice_id=INV1):
    return client.get(f"/v1/invoices/{invoice_id}", headers=h).json()["due_paise"]


def approved_request(client, h, amount, invoice_id=INV1):
    r = client.post("/v1/payment-intents", headers=h, json={"invoice_id": invoice_id, "amount_paise": amount})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "proposed" and r.json()["link_url"] is None  # proposal creates no link
    a = client.post(f"/v1/payment-intents/{r.json()['id']}/approve", headers=h, json={"provider": "demo"})
    assert a.status_code == 200, a.text
    assert a.json()["mode"] == "simulated"
    return a.json()["id"]


def simulate(client, h, **body):
    r = client.post("/v1/demo/simulate-payment-event", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_money_helpers():
    assert line_total_paise("2", 120000) == 240000
    assert line_total_paise("2.5", 3333) == 8333  # 8332.5 rounds half-up
    assert format_inr(2000000) == "₹20,000"
    assert format_inr(12345678) == "₹1,23,456.78"
    with pytest.raises(ValueError):
        line_total_paise("abc", 100)


def test_required_scenario_20000_then_5000_10000_leaves_5000_then_closes(client, owner):
    inv = client.get(f"/v1/invoices/{INV1}", headers=owner).json()
    assert inv["total_paise"] == 2_000_000
    assert [a["amount_paise"] for a in inv["allocations"]] == [500_000, 1_000_000]
    assert inv["due_paise"] == 500_000 and inv["status"] == "partially_paid"
    assert inv["promised_open_paise"] == 500_000  # an open promise exists and has not reduced the balance

    req = approved_request(client, owner, 500_000)
    assert due(client, owner) == 500_000  # an approved request is not a receipt
    out = simulate(client, owner, payment_request_id=req)
    assert out["deliveries"][0]["status"] == "processed"
    assert out["payment"]["state"] == "provider_verified" and out["payment"]["mode"] == "simulated"
    inv = client.get(f"/v1/invoices/{INV1}", headers=owner).json()
    assert inv["due_paise"] == 0 and inv["status"] == "paid"
    assert any(a["action"] == "allocation.created" for a in inv["audit"])
    # Nothing more can be requested against a closed invoice.
    assert client.post("/v1/payment-intents", headers=owner, json={"invoice_id": INV1, "amount_paise": 1}).status_code == 422


def test_duplicate_webhook_is_applied_once(client, owner, db):
    req = approved_request(client, owner, 200_000)
    out = simulate(client, owner, payment_request_id=req, deliver_twice=True)
    assert [d["status"] for d in out["deliveries"]] == ["processed", "duplicate"]
    assert all(d["http_status"] == 200 for d in out["deliveries"])
    assert due(client, owner) == 300_000
    assert db.scalar(select(func.count()).select_from(PaymentAllocation).where(
        PaymentAllocation.payment_id == out["payment"]["id"])) == 1
    # Same provider payment re-announced under a NEW event id must not post again either.
    again = simulate(client, owner, payment_id=out["payment"]["id"], event_type="payment.captured")
    assert again["deliveries"][0]["status"] == "ignored"
    assert due(client, owner) == 300_000


def test_out_of_order_events_do_not_regress_or_double_credit(client, owner):
    req = approved_request(client, owner, 100_000)
    out = simulate(client, owner, payment_request_id=req, event_type="payment.captured")
    late = simulate(client, owner, payment_id=out["payment"]["id"], event_type="payment.authorized")
    assert late["deliveries"][0]["status"] == "ignored" and late["payment"]["state"] == "provider_verified"
    late = simulate(client, owner, payment_id=out["payment"]["id"], event_type="payment.failed")
    assert late["payment"]["state"] == "provider_verified"
    assert due(client, owner) == 400_000


def test_authorised_is_not_received_until_captured(client, owner):
    req = approved_request(client, owner, 100_000)
    out = simulate(client, owner, payment_request_id=req, event_type="payment.authorized")
    assert out["payment"]["state"] == "authorised" and due(client, owner) == 500_000
    out = simulate(client, owner, payment_id=out["payment"]["id"], event_type="payment.captured")
    assert out["payment"]["state"] == "provider_verified" and due(client, owner) == 400_000


def test_webhook_endpoint_rejects_bad_signature_and_accepts_good(client, owner, settings):
    req = approved_request(client, owner, 100_000)
    body, sig, event_id = DemoPaymentProvider(settings).build_event(
        event_type="payment.captured", account_id="acc_demo_a", payment_id="pay_x1", amount_paise=100_000,
        payment_request_id=req)
    bad = client.post("/v1/webhooks/demo", content=body, headers={"x-demo-signature": "f" * 64, "x-demo-event-id": event_id})
    assert bad.status_code == 401 and due(client, owner) == 500_000
    tampered = body.replace(b"100000", b"500000")
    assert client.post("/v1/webhooks/demo", content=tampered,
                       headers={"x-demo-signature": sig, "x-demo-event-id": event_id}).status_code == 401
    assert client.post("/v1/webhooks/demo", content=body, headers={"x-demo-signature": sig}).status_code == 400
    ok = client.post("/v1/webhooks/demo", content=body, headers={"x-demo-signature": sig, "x-demo-event-id": event_id})
    assert ok.status_code == 200 and ok.json()["status"] == "processed" and due(client, owner) == 400_000
    replay = client.post("/v1/webhooks/demo", content=body, headers={"x-demo-signature": sig, "x-demo-event-id": event_id})
    assert replay.status_code == 200 and replay.json()["status"] == "duplicate" and due(client, owner) == 400_000
    assert client.post("/v1/webhooks/razorpay", content=body, headers={"x-razorpay-signature": sig,
                                                                     "x-razorpay-event-id": "e1"}).status_code == 401


def test_overpayment_is_held_unallocated_and_flagged(client, owner):
    req_a = approved_request(client, owner, 500_000)
    req_b = approved_request(client, owner, 500_000)  # two requests for the same last ₹5,000
    simulate(client, owner, payment_request_id=req_a)
    out = simulate(client, owner, payment_request_id=req_b)
    assert out["payment"]["state"] == "provider_verified"
    assert out["payment"]["allocated_paise"] == 0 and out["payment"]["unallocated_paise"] == 500_000
    assert due(client, owner) == 0  # never negative
    kinds = [m["kind"] for m in client.get("/v1/mismatches", headers=owner).json() if m["status"] == "open"]
    assert "unallocated_funds" in kinds
    # Owner can apply the held funds to another invoice, but not beyond funds or balance.
    pid = out["payment"]["id"]
    over = client.post(f"/v1/payments/{pid}/allocate", headers=owner, json={"invoice_id": "inv_demo_0002", "amount_paise": 500_001})
    assert over.status_code == 409
    ok = client.post(f"/v1/payments/{pid}/allocate", headers=owner, json={"invoice_id": "inv_demo_0002", "amount_paise": 500_000})
    assert ok.status_code == 200 and ok.json()["unallocated_paise"] == 0
    assert due(client, owner, "inv_demo_0002") == 750_000


def test_ledger_refuses_over_allocation_and_unconfirmed_funds(db):
    inv = db.get(Invoice, INV1)
    pay = db.scalar(select(Payment).where(Payment.provider_payment_id == "pay_demo_seed_1"))
    with pytest.raises(ledger.LedgerError):  # payment is already fully allocated
        ledger.allocate(db, pay, inv, 1, "test")
    claim = db.get(Payment, "pay_seed_claim")
    with pytest.raises(ledger.LedgerError):  # unverified claim carries no allocatable funds
        ledger.allocate(db, claim, db.get(Invoice, "inv_demo_0003"), 100, "test")
    other = db.get(Invoice, "inv_demo_b001")
    with pytest.raises(ledger.LedgerError):
        ledger.allocate(db, pay, other, 1, "test")


def test_allocations_and_audit_are_immutable(db):
    alloc = db.scalar(select(PaymentAllocation).limit(1))
    alloc.amount_paise = 1
    with pytest.raises(RuntimeError):
        db.flush()


def test_wrong_currency_and_amount_mismatch(client, owner):
    req = approved_request(client, owner, 300_000)
    out = simulate(client, owner, payment_request_id=req, currency="USD")
    assert out["deliveries"][0]["status"] == "rejected" and out["payment"] is None and due(client, owner) == 500_000
    out = simulate(client, owner, payment_request_id=req, amount_paise=250_000)
    assert out["payment"]["state"] == "provider_verified" and due(client, owner) == 250_000
    assert "amount_mismatch" in [m["kind"] for m in client.get("/v1/mismatches", headers=owner).json()]


def test_dispute_reverses_with_compensating_entry_and_can_be_upheld(client, owner):
    req = approved_request(client, owner, 500_000)
    out = simulate(client, owner, payment_request_id=req)
    assert due(client, owner) == 0
    simulate(client, owner, payment_id=out["payment"]["id"], event_type="payment.dispute.created")
    inv = client.get(f"/v1/invoices/{INV1}", headers=owner).json()
    assert inv["due_paise"] == 500_000
    assert [a["amount_paise"] for a in inv["allocations"]][-2:] == [500_000, -500_000]  # history kept
    report = client.get("/v1/reports/today", headers=owner).json()
    assert len(report["disputes"]) == 1 and report["received"]["disputed_paise"] == 500_000
    r = client.post(f"/v1/payments/{out['payment']['id']}/resolve-dispute", headers=owner,
                    json={"outcome": "upheld", "note": "provider ruled in our favour"})
    assert r.status_code == 200 and r.json()["state"] == "provider_verified" and due(client, owner) == 0


def test_refund_reverses_payment(client, owner):
    req = approved_request(client, owner, 500_000)
    out = simulate(client, owner, payment_request_id=req)
    out = simulate(client, owner, payment_id=out["payment"]["id"], event_type="refund.processed")
    assert out["payment"]["state"] == "reversed" and due(client, owner) == 500_000


def test_manual_claim_is_unverified_until_owner_confirms(client, owner, staff):
    inv3 = "inv_demo_0003"
    assert due(client, owner, inv3) == 840_000  # seeded screenshot claim of ₹2,000 has not reduced it
    r = client.post("/v1/payments/manual", headers=staff, json={
        "customer_id": "cus_kavitha", "invoice_id": inv3, "amount_paise": 400_000, "method": "cash",
        "evidence_type": "cash_in_hand", "note": "Collected at shop"})
    assert r.status_code == 201 and r.json()["state"] == "manual_unverified"
    assert due(client, owner, inv3) == 840_000
    pid = r.json()["id"]
    assert client.post(f"/v1/payments/{pid}/confirm", headers=staff, json={"note": "counted"}).status_code == 403
    c = client.post(f"/v1/payments/{pid}/confirm", headers=owner, json={"note": "Counted cash and banked it"})
    assert c.status_code == 200 and c.json()["state"] == "merchant_confirmed"
    assert due(client, owner, inv3) == 440_000
    received = client.get("/v1/reports/today", headers=owner).json()["received"]
    assert received["merchant_confirmed_paise"] == 400_000
    assert received["provider_verified_paise"] == 1_000_000  # kept separate
    assert received["unverified_claims_paise"] == 200_000
    # A disputed screenshot claim never touched the balance.
    d = client.post("/v1/payments/pay_seed_claim/dispute", headers=staff, json={"note": "No credit in bank statement"})
    assert d.status_code == 200 and d.json()["state"] == "disputed" and due(client, owner, inv3) == 440_000


def test_tenant_isolation(client, owner, other_owner, settings):
    assert client.get(f"/v1/invoices/{INV1}", headers=other_owner).status_code == 404
    assert client.get("/v1/customers/cus_murugan/ledger", headers=other_owner).status_code == 404
    assert [i["number"] for i in client.get("/v1/invoices", headers=other_owner).json()] == ["INV-0001"]
    assert all(c["name"] == "Bay Retail" for c in client.get("/v1/customers", headers=other_owner).json())
    assert client.post("/v1/payment-intents", headers=other_owner, json={"invoice_id": INV1, "amount_paise": 100}).status_code == 404
    assert client.post("/v1/payments/pay_seed_claim/confirm", headers=other_owner, json={"note": "mine"}).status_code == 404
    assert client.get("/v1/invoices").status_code == 401
    # A validly signed event from merchant B's provider account cannot settle merchant A's request.
    req = approved_request(client, owner, 500_000)
    body, sig, event_id = DemoPaymentProvider(settings).build_event(
        event_type="payment.captured", account_id="acc_demo_b", payment_id="pay_cross", amount_paise=500_000,
        payment_request_id=req)
    r = client.post("/v1/webhooks/demo", content=body, headers={"x-demo-signature": sig, "x-demo-event-id": event_id})
    assert r.json()["status"] == "rejected" and due(client, owner) == 500_000
    assert client.get("/v1/payments", headers=other_owner).json() == []


def test_viewer_is_read_only(client, viewer):
    assert client.get("/v1/invoices", headers=viewer).status_code == 200
    assert client.post("/v1/payment-intents", headers=viewer, json={"invoice_id": INV1, "amount_paise": 100}).status_code == 403
    assert client.post("/v1/demo/simulate-payment-event", headers=viewer, json={"amount_paise": 100}).status_code == 403
