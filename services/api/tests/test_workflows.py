"""Promises, bill upload review, reports, assistant, outbound gating, WhatsApp webhook, migrations."""
import hashlib
import hmac
import json
from datetime import date

from sqlalchemy import create_engine, inspect

from app.db import Base
from domain.intents import parse_commitments

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
TODAY = date(2026, 11, 18)  # Wednesday


def test_parse_two_commitments_from_customer_words():
    got = parse_commitments("₹3,000 on Friday, ₹2,000 on Monday", TODAY)
    assert [(g["amount_paise"], g["promised_date"]) for g in got] == [(300_000, "2026-11-20"), (200_000, "2026-11-23")]
    got = parse_commitments("I will pay Rs 1500 cash tomorrow and 2k by gpay on 25/11", TODAY)
    assert [(g["amount_paise"], g["promised_date"], g["method"]) for g in got] == [
        (150_000, "2026-11-19", "cash"), (200_000, "2026-11-25", "upi")]
    assert parse_commitments("ok will see", TODAY) == []
    assert parse_commitments("I will pay 3000", TODAY) == []  # no day stated => nothing proposed


def test_promises_create_two_commitments_and_zero_receipts(client, owner):
    before = client.get("/v1/customers/cus_murugan/ledger", headers=owner).json()
    inbound = client.post("/v1/demo/inbox/inbound", headers=owner,
                          json={"customer_id": "cus_murugan", "body": "₹3,000 on Friday, ₹2,000 on Monday"}).json()
    assert inbound["message"]["simulated"] is True and len(inbound["proposals"]) == 2
    assert len(client.get("/v1/promises", headers=owner).json()) == 4  # proposals are not saved
    payload = {"customer_id": "cus_murugan", "invoice_id": "inv_demo_0001", "evidence_source": "demo_inbox",
               "evidence_text": inbound["message"]["body"], "source_message_id": inbound["message"]["id"],
               "items": [{"amount_paise": p["amount_paise"], "promised_date": p["promised_date"], "method": "upi"}
                         for p in inbound["proposals"]]}
    assert client.post("/v1/promises", headers=owner, json={**payload, "customer_confirmed": False}).status_code == 422
    r = client.post("/v1/promises", headers=owner, json={**payload, "customer_confirmed": True})
    assert r.status_code == 201 and len(r.json()) == 2 and all(p["simulated"] for p in r.json())
    after = client.get("/v1/customers/cus_murugan/ledger", headers=owner).json()
    assert after["totals"]["outstanding_paise"] == before["totals"]["outstanding_paise"] == 500_000
    assert len(after["payments"]) == len(before["payments"])
    assert after["totals"]["promised_open_paise"] == before["totals"]["promised_open_paise"] + 500_000
    # Editable, and status changes never post money.
    pid = r.json()[0]["id"]
    e = client.patch(f"/v1/promises/{pid}", headers=owner, json={"status": "kept", "method": "cash"})
    assert e.status_code == 200 and e.json()["status"] == "kept"
    assert client.get("/v1/invoices/inv_demo_0001", headers=owner).json()["due_paise"] == 500_000


def test_upload_review_requires_fixes_and_explicit_approval(client, owner, staff):
    assert client.post("/v1/uploads", headers=owner, files={"file": ("x.exe", b"MZ", "application/x-msdownload")}).status_code == 415
    assert client.post("/v1/uploads", headers=owner, files={"file": ("x.png", b"not a png", "image/png")}).status_code == 415
    up = client.post("/v1/uploads", headers=staff, files={"file": ("bill.png", PNG, "image/png")}, data={"source": "whatsapp_demo"})
    assert up.status_code == 201
    invoices_before = len(client.get("/v1/invoices", headers=owner).json())
    d = client.post("/v1/invoice-drafts/extract", headers=staff, json={"upload_id": up.json()["id"]}).json()
    assert d["status"] == "needs_review" and d["extraction_source"] == "simulated" and d["payload"]["needs_human_review"]
    codes = {i["code"] for i in d["issues"]}
    assert {"line_total_conflict", "missing_number", "tax_undetermined"} <= codes
    assert len(client.get("/v1/invoices", headers=owner).json()) == invoices_before  # extraction posts nothing
    blocked = client.post(f"/v1/invoice-drafts/{d['id']}/approve", headers=staff, json={"acknowledge_warnings": True})
    assert blocked.status_code == 409 and blocked.json()["detail"]["issues"]

    p = d["payload"]
    p["items"][1]["line_total_paise"] = 80000
    p["items"][2].update(quantity="1", line_total_paise=210000)
    p.update(subtotal_paise=530000, total_paise=530000, uncertain_fields=[])
    fixed = client.patch(f"/v1/invoice-drafts/{d['id']}", headers=staff, json={"payload": p, "customer_id": d["customer_id"]}).json()
    assert [i for i in fixed["issues"] if i["severity"] == "blocking"] == []
    assert fixed["computed"]["total_paise"] == 530000
    needs_ack = client.post(f"/v1/invoice-drafts/{d['id']}/approve", headers=staff, json={})
    assert needs_ack.status_code == 409  # tax warning must be acknowledged
    ok = client.post(f"/v1/invoice-drafts/{d['id']}/approve", headers=staff, json={"acknowledge_warnings": True})
    assert ok.status_code == 200, ok.text
    inv = ok.json()["invoice"]
    assert inv["number"] == "INV-0004" and inv["total_paise"] == 530000 and inv["due_paise"] == 530000
    assert inv["customer_id"] == "cus_murugan"
    assert client.post(f"/v1/invoice-drafts/{d['id']}/approve", headers=staff, json={"acknowledge_warnings": True}).status_code == 409
    assert client.get(f"/v1/uploads/{up.json()['id']}/file", headers=owner).content == PNG
    # Same file again is flagged as a possible duplicate.
    up2 = client.post("/v1/uploads", headers=staff, files={"file": ("bill.png", PNG, "image/png")}).json()
    d2 = client.post("/v1/invoice-drafts/extract", headers=staff, json={"upload_id": up2["id"]}).json()
    assert "duplicate_file" in {i["code"] for i in d2["issues"]}


def test_draft_is_tenant_scoped(client, owner, other_owner):
    up = client.post("/v1/uploads", headers=owner, files={"file": ("bill.png", PNG, "image/png")}).json()
    d = client.post("/v1/invoice-drafts/extract", headers=owner, json={"upload_id": up["id"]}).json()
    assert client.get(f"/v1/invoice-drafts/{d['id']}", headers=other_owner).status_code == 404
    assert client.get(f"/v1/uploads/{up['id']}/file", headers=other_owner).status_code == 404
    assert client.post("/v1/invoice-drafts/extract", headers=other_owner, json={"upload_id": up["id"]}).status_code == 404


def test_today_report_separates_expected_from_received(client, owner):
    r = client.get("/v1/reports/today?date=2026-11-18", headers=owner).json()
    assert r["outstanding_paise"] == 500_000 + 1_250_000 + 840_000
    assert r["received"]["provider_verified_paise"] == 1_000_000
    assert r["received"]["provider_verified_by_mode"] == {"simulated": 1_000_000}
    assert r["received"]["unverified_claims_paise"] == 200_000 and r["received"]["confirmed_total_paise"] == 1_000_000
    assert r["expected_today_paise"] == 900_000
    assert sorted(p["customer_name"] for p in r["promises_due_today"]) == ["Kavitha Supermarket", "Murugan Stores"]
    assert [p["customer_name"] for p in r["cash_pickups"]] == ["Kavitha Supermarket"]  # only confirmed windows
    assert r["contacted"] == {"count": 0, "simulated_count": 0, "customers": []}  # no fabricated outreach
    assert r["replied"]["count"] == 0 and r["replied"]["simulated_count"] == 1
    old = client.get("/v1/reports/today?date=2026-11-11", headers=owner).json()
    assert old["received"]["provider_verified_paise"] == 500_000 and old["expected_today_paise"] == 0


def test_assistant_answers_from_ledger_tools(client, owner, viewer):
    def ask(q, h=owner):
        return client.post("/v1/assistant/ask", headers=h, json={"question": q}).json()
    a = ask("Who agreed to pay today?")
    assert a["tool"] == "get_today_promises" and "Kavitha Supermarket ₹4,000" in a["answer"] and "Murugan Stores ₹5,000" in a["answer"]
    a = ask("How much did Murugan Stores pay?", viewer)  # read-only: a viewer may ask
    assert a["tool"] == "get_customer_payments" and "₹15,000 provider-verified" in a["answer"] and "simulated" in a["answer"]
    assert len(a["evidence"]["payments"]) == 2
    a = ask("What is my confirmed cash in?")
    assert a["tool"] == "get_today_received" and "₹10,000" in a["answer"] and "₹2,000 is claimed but unverified" in a["answer"]
    assert "owes ₹12,500" in ask("How much does Anbu owe?")["answer"]
    assert ask("please mark INV-0001 as settled")["tool"] is None


def test_voice_tools_need_secret_and_are_limited(client):
    assert client.post("/v1/voice-tools/customer-balance", json={"customer_name": "Murugan"}).status_code == 401
    r = client.post("/v1/voice-tools/customer-balance", json={"customer_name": "Murugan"}, headers={"x-voice-tool-secret": "voice-secret"})
    assert r.json() == {"found": True, "customer_name": "Murugan Stores", "outstanding_paise": 500_000,
                        "spoken_answer": "Murugan Stores owes ₹5,000 (INV-0001 ₹5,000)."}


def test_outbound_is_gated(client, owner, monkeypatch, settings):
    def send(customer, channel, mtype):
        d = client.post("/v1/messages/drafts", headers=owner, json={"customer_id": customer, "channel": channel,
                                                                    "message_type": mtype, "body": "Invoice INV-0001 attached"}).json()
        assert d["message"]["status"] == "draft"  # nothing goes out without approval
        return client.post(f"/v1/messages/{d['message']['id']}/approve", headers=owner).json()
    assert send("cus_murugan", "demo_inbox", "overdue_reminder")["message"]["status"] == "blocked"
    assert send("cus_kavitha", "demo_inbox", "invoice_share")["message"]["status"] == "blocked"  # no opt-in
    ok = send("cus_murugan", "demo_inbox", "invoice_share")
    assert ok["message"]["status"] == "sent_simulated" and ok["message"]["simulated"] is True
    assert client.get("/v1/reports/today", headers=owner).json()["contacted"] == {
        "count": 0, "simulated_count": 1,
        "customers": [{"customer_id": "cus_murugan", "customer_name": "Murugan Stores", "simulated": True}]}
    client.post("/v1/customers/cus_murugan/consents", headers=owner, json={"channel": "demo_inbox", "status": "opt_out", "evidence": "Asked to stop"})
    assert send("cus_murugan", "demo_inbox", "invoice_share")["message"]["status"] == "blocked"
    # Real WhatsApp: opt-in alone is not enough, and neither is the policy flag alone.
    client.post("/v1/customers/cus_murugan/consents", headers=owner, json={"channel": "whatsapp", "status": "opt_in", "evidence": "Signed form"})
    assert "OUTBOUND_POLICY_APPROVED" in send("cus_murugan", "whatsapp", "invoice_share")["policy"]["reason"]
    monkeypatch.setattr(settings, "outbound_policy_approved", True)
    assert send("cus_murugan", "whatsapp", "invoice_share")["message"]["status"] == "blocked"
    monkeypatch.setattr(settings, "outbound_approved_message_types", "invoice_share")
    monkeypatch.setattr(settings, "whatsapp_access_token", "token")
    last = send("cus_murugan", "whatsapp", "invoice_share")
    assert last["message"]["status"] == "blocked" and "not implemented" in last["policy"]["reason"]
    assert send("cus_murugan", "whatsapp", "overdue_reminder")["message"]["status"] == "blocked"


def test_whatsapp_webhook_signature_and_inbound_reply(client, owner, db):
    from app.models import MerchantProviderAccount
    db.add(MerchantProviderAccount(merchant_id="mer_demo_a", provider="whatsapp", account_id="1055"))
    db.commit()
    body = json.dumps({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "1055"}, "messages": [
        {"id": "wamid.1", "from": "919000000001", "type": "text", "text": {"body": "Will pay 3000 on Friday"}}]}}]}]}).encode()
    sig = "sha256=" + hmac.new(b"wa-secret", body, hashlib.sha256).hexdigest()
    assert client.post("/v1/webhooks/whatsapp", content=body, headers={"x-hub-signature-256": "sha256=bad"}).status_code == 401
    assert client.post("/v1/webhooks/whatsapp", content=body, headers={"x-hub-signature-256": sig}).json()["stored"] == 1
    assert client.post("/v1/webhooks/whatsapp", content=body, headers={"x-hub-signature-256": sig}).json()["stored"] == 0
    msgs = client.get("/v1/customers/cus_murugan/messages", headers=owner).json()
    assert msgs[-1]["channel"] == "whatsapp" and msgs[-1]["simulated"] is False
    assert len(client.get("/v1/promises", headers=owner).json()) == 4  # an inbound message never auto-creates a promise
    assert client.get("/v1/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=wa-verify&hub.challenge=42").text == "42"
    assert client.get("/v1/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=nope&hub.challenge=42").status_code == 403


def test_integrations_are_labelled(client, owner):
    items = {i["key"]: i for i in client.get("/v1/integrations", headers=owner).json()["items"]}
    assert items["payments_demo"]["label"] == "simulated" and items["extraction"]["label"] == "simulated"
    assert items["payments_razorpay"]["label"] == "not configured" and items["whatsapp_outbound"]["active"] is False


def test_migrations_match_models(tmp_path):
    from alembic import command
    from alembic.config import Config
    url = f"sqlite:///{tmp_path}/mig.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    insp = inspect(create_engine(url))
    for table in Base.metadata.sorted_tables:
        assert {c["name"] for c in insp.get_columns(table.name)} == {c.name for c in table.columns}, table.name
