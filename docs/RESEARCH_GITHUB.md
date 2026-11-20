# GitHub and ecosystem research map
Research verified against repository pages and primary documentation on **20 November 2026**. This is a practical shortlist of reusable components, **not every repository on GitHub**. Verify licences, API changes, maintained branches, pricing and supported countries before shipping.

## A. Build now (Tier 1)
| Repo | License / reuse caution | Fit | What to copy or learn |
|---|---|---|---|
| [google/adk-python](https://github.com/google/adk-python) | Apache-2.0 | Core orchestration | Python tools, human-in-the-loop and agent tests; use stable pinned SDK |
| [googleapis/python-genai](https://github.com/googleapis/python-genai) | Open-source SDK; confirm current repo LICENSE | Core Gemini SDK | image input, structured model output and validation |
| [fbsamples/whatsapp-api-examples](https://github.com/fbsamples/whatsapp-api-examples) | **Meta Platform Policy license**, not MIT | Official integration example | `media-messages-js`, `basic-webhook-js`, `signature-validation-with-webhooks-payloads`; follow SDK docs; do not wholesale redistribute |
| [elevenlabs/elevenlabs-python](https://github.com/elevenlabs/elevenlabs-python) | MIT | Voice integration | official SDK; server tool authentication and transcript metadata |
| [razorpay/razorpay-python](https://github.com/razorpay/razorpay-python) | SDK; check LICENSE | Payments | Payment Links API, webhook validation; use test-mode API keys |
| [fastapi/fastapi](https://github.com/fastapi/fastapi) | MIT | Backend | typed HTTP APIs, security, validation and automatic API docs |
| [google/adk-python/.agents/skills/adk-agent-builder](https://github.com/google/adk-python/tree/main/.agents/skills/adk-agent-builder) | Under repo terms | Agent coding skill | Cross-check current ADK APIs; human approvals, workflow patterns |
| [elevenlabs/skills](https://github.com/elevenlabs/skills) | Verify per-file/project licence | Voice-agent skill patterns | Official reference agent skills and tool design |

## B. Use selectively (Tier 2)
| Repo | License / caution | Fit | Decision |
|---|---|---|---|
| [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Apache-2.0 | OCR fallback | Optional, can be heavy locally; evaluate Tamil handwritten samples before promising success |
| [docling-project/docling](https://github.com/docling-project/docling) | MIT | PDF parsing | Useful for complex PDFs; Gemini first for photos |
| [chatwoot/chatwoot](https://github.com/chatwoot/chatwoot) | MIT for core; verify integrations | Operator inbox | Later if support-team takeover becomes a priority; do not deploy during hackathon |
| [activepieces/activepieces](https://github.com/activepieces/activepieces) | Community edition MIT; enterprise commercial | Integrations | Later workflow automation; can be unnecessary overhead early |
| [frappe/erpnext](https://github.com/frappe/erpnext) | GPL-3.0 | Reference for accounting/stock | Study ledger/receivables model or integrate later; avoid embedding GPL code without licence implications |
| [supabase/supabase](https://github.com/supabase/supabase) | Mixed components/licences; inspect individual repos | Managed Postgres/auth/storage | Useful hosted stack; not essential to ledger design |
| [razorpay/razorpay-node](https://github.com/razorpay/razorpay-node) | SDK; check licence | If backend changes to Node | Alternative payment adapter to Python SDK |

## C. Study / inspiration, NOT unrestricted open-source reuse
| Product or source | Why relevant | Caution |
|---|---|---|
| [Invoice Ninja v5](https://github.com/invoiceninja/invoiceninja) | Invoice creation, reporting, customer UX | **Elastic License**, source-available; do not treat as standard open-source code |
| [Khatabook](https://khatabook.com/en/) | Credit ledger, QR collections, lightweight merchant UX | Proprietary product, competition and UX research |
| [PraecisAI](https://www.praecisai.in/ai-collections-agent) | Voice follow-up, commitment logging, B2B receivables | Proprietary; demonstrates competition; do not imitate coercive recovery workflow |
| [Autowhat](https://autowhat.ai/ai-collections-agent) | Bill-photo/WhatsApp input and finance agents | Proprietary; category competition, positioning research |

## D. Important official reference documentation
- WhatsApp Business policy: https://whatsappbusiness.com/policy/
- WhatsApp Platform overview: https://developers.facebook.com/documentation/business-messaging/whatsapp/overview/
- ElevenLabs WhatsApp: https://elevenlabs.io/docs/eleven-agents/whatsapp/getting-started
- ElevenLabs webhook tools: https://elevenlabs.io/docs/eleven-agents/customization/tools/webhook-tools
- Razorpay webhook validation: https://github.com/razorpay/markdown-docs/blob/master/webhooks/validate-test.md
- Razorpay partial payment restrictions: https://github.com/razorpay/markdown-docs/blob/master/payments/payment-links/partial-payments.md
- RBI PA Master Direction (11 Nov 2026 update): https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12896
- TRAI advice to senders: https://trai.gov.in/advice-to-senders
- India DPDP implementation Gazette 13 Nov 2025: https://egazette.gov.in/WriteReadData/2025/267647.pdf

## E. What research changed in our strategy
- A simple khata is not novel. The differentiator must be **end-to-end zero-entry bill → explicit promise → verified partial payment → realistic expected cash**.
- ElevenLabs can handle WhatsApp voice notes/text, but number registration and single-provider ownership need careful design. Use independent merchant browser voice for fastest demo.
- UPI-only payment links from Razorpay **do not support partial payments** on one link. Maintain one invoice balance in our own ledger and create independent requests appropriate to the payment amount (or provider-specific standard link features if enabled).
- Razorpay can resend events and ordering is not guaranteed; persistence + idempotency is nonnegotiable.
- Meta's messaging policy explicitly lists debt collection as prohibited activity, even when the seller calls it an invoice reminder. Design merchant-approved, opt-in transactional workflows, avoid prohibited automated outreach, and seek channel/provider approval.
- A bank SMS, voice claim or screenshot is not independent proof of receipt. Use provider-signed events or documented authorised reconciliation.
- Licence matters: Meta sample code and Invoice Ninja are **not** generally permissively licensed like MIT/Apache.

## F. Source provenance / validation limits
These are primary GitHub project pages and official vendor documentation, corroborated by search on 20 Nov 2026. Their existence, advertised capabilities and visible licensing were reviewed. No dependency audit, source-code security audit, API credential run or live WhatsApp/Razorpay connection was performed. Claims about provider capabilities can change; verify in the developer account before turning on real users.
