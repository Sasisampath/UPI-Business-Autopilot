---
name: upi-business-autopilot
summary: Build and extend a WhatsApp-first, voice-assisted Indian merchant sales billing, partial-payment, payment coordination and cash-flow application with strict verified-ledger safeguards.
description: Use when planning, coding, reviewing or testing UPI Business Autopilot, handwritten bill intake, Gemini extraction, ElevenLabs voice, customer payment commitments, Razorpay sandbox reconciliation, WhatsApp integrations or merchant daily reports.
---

# UPI Business Autopilot — Agent Skill

## Mission
Build a **real, working local-first MVP** for Indian micro/small merchants and B2B distributors. Convert a photo/PDF/voice note of an ordinary sales bill into a **merchant-confirmed** digital invoice; track partial payment receipts, customer-stated payment intentions, invoice allocation, and accurate daily cash-flow intelligence. The merchant stays in control. Do not build a loan recovery product.

## Before every implementation
1. Read `docs/PRODUCT_SPEC.md` for scope and user flows.
2. Read `docs/ARCHITECTURE.md` for source of truth, event boundaries and transaction rules.
3. Read `docs/INTEGRATIONS_AND_COMPLIANCE.md` before touching WhatsApp, calling, payment APIs, personal data or credentials.
4. Read `docs/TEST_PLAN.md` before marking a feature complete.
5. Read `docs/RESEARCH_GITHUB.md` before choosing a reusable library, and check upstream API/licence if integrating.
6. Follow project root `AGENTS.md` and the user-facing brief `BUILD_PROMPT.md`.

## Product language and boundaries
- Position as **sales-to-payment coordination** and cash-flow management. Not lending, repayment collection or coercive recovery.
- Target a wholesaler/FMCG distributor serving repeat retail shops; later adapt to neighbourhood kirana vendors.
- Make a **merchant dashboard + merchant WhatsApp bill intake + merchant voice inquiry** first. For customer communications, provide a simulated inbox/approval workflow until provider/platform clearance.
- Customer preferences (preferred payment method, availability, promise date) must be **explicitly stated, dated, editable**; do not infer willingness or creditworthiness.
- Show separation between **invoice amount, promised amount, expected cash, confirmed payment, unverified/manual claim**.
- Prefer simple Indian English; Tamil/English code-switching should work for voice notes and conversations, with visible correction UI.

## Technical stack, unless existing repo dictates otherwise
- Web: Next.js / TypeScript / Tailwind.
- API: Python FastAPI with typed Pydantic models.
- DB: PostgreSQL (SQLite temporary for a local standalone demo if migrations remain portable).
- AI: Google `google-genai` for document extraction; `google-adk` for approved business-tool orchestration. Keep deterministic business rules outside prompts.
- Voice: ElevenLabs agent + authenticated server tools; can use browser voice if telephony is unavailable.
- WhatsApp: Meta official Cloud API with signature-checked webhook and permitted categories only; demo inbox adapter by default.
- Payments: Razorpay official Python SDK + verified webhook adapter; sandbox and deterministic mock providers by default.
- Hosting later: Cloud Run, managed PostgreSQL, encrypted object storage.

## Critical financial invariants
- Store currency as **integer paise**. Never use LLMs or binary floating point to calculate balances.
- Invoice `due = total - sum(confirmed allocations) + sum(reversal adjustments)`; derive values through a transaction-safe ledger.
- A payment event has state `pending`, `provider_verified`, `manual_unverified`, `disputed`, `reversed` or `simulated`; **never mix these in one 'received' number**.
- Payments can map to invoices using `PaymentAllocation`; never allocate over available confirmed funds or invoice balance.
- Every provider webhook must verify raw-body signature, idempotency/event ID, merchant ownership, currency, amount and payment reference. Handle retries and out-of-order events.
- A customer receipt screenshot, bank SMS or agent's words **do not prove bank settlement**. Show `unverified` until confirmed by an authorised provider or authorised finance reconciliation.
- AI extraction makes a **draft only**. Flag ambiguity, duplicate bills, missing buyer data, calculation discrepancies and GST/invoice-tax uncertainties. User approval required.
- Any message, payment request, supplier payment or ledger correction affecting the outside world requires authorisation appropriate to that action; no autonomous payouts.

## AI agent responsibilities
- `bill_intake_agent`: parse bill/document to draft fields with per-field confidence/review flags; cannot commit ledger.
- `merchant_assistant`: read balances, recent verified payments, confirmed promises, expected collection plan, merchant FAQs.
- `coordination_agent`: propose customer communications/payment links; records customer-stated commitments only from confirmed communications; blocked from unsanctioned outbound action.
- `reconciliation_service`: **deterministic backend**, not AI, owns reconciliation and financial posting.
- `report_service`: compute metrics from recorded events with explicit definitions and provenance.

## Required API tool boundaries
- `extract_invoice_draft(upload_id)` -> draft + issues (never posts an invoice).
- `approve_invoice(draft_id, merchant_id, actor_id)` -> approved invoice.
- `get_customer_balance(customer_id, merchant_id)` -> verified outstanding.
- `record_payment_intent(invoice_id, amount_paise, promised_date, method, evidence)` -> commitment (not receipt).
- `prepare_payment_request(invoice_id, amount_paise)` -> proposal or sandbox link, never unapproved send.
- `apply_verified_webhook(provider_event)` -> idempotent financial event + allocation.
- `get_daily_collection_report(merchant_id, date, tz=Asia/Kolkata)` -> separate expected vs received.

## Scope and priority
**P0:** upload/photo -> extraction review -> invoice approval -> receivable -> partial-payment simulator/webhook -> daily report -> merchant voice readout.
**P1:** official WhatsApp inbound bill media; ElevenLabs live browser voice; Razorpay test-mode link/webhook; manual reconciliation approval.
**P2:** provider-approved transactional messaging, opt-ins, visit coordination, inventory item capture, supplier invoices; never auto-pay suppliers.

## Tests required before done
- Invoice ₹20,000, confirmed partials ₹5,000 and ₹10,000, due ₹5,000.
- Customer 'Friday ₹3,000, Monday ₹2,000' produces two promises and zero receipts.
- Duplicate/out-of-order webhook does not double-credit.
- Forged screenshot/SMS, incorrect webhook signature, cross-merchant access and over-allocation are rejected/flagged.
- Text/image extraction uncertainty leads to a visible approval step.
- WhatsApp outbound automation stays disabled without explicit `OUTBOUND_POLICY_APPROVED=true` plus approved message type, channel permissions and recorded opt-in; do not silently auto-enable based on this flag alone.

## References
Read the relevant file instead of guessing: `docs/PRODUCT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/RESEARCH_GITHUB.md`, `docs/INTEGRATIONS_AND_COMPLIANCE.md`, `docs/TEST_PLAN.md`, `docs/MVP_ROADMAP.md`.
