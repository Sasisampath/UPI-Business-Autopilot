# ElevenLabs voice for the merchant assistant

## Status
- **App side is built and tested with a stand-in; not yet connected to a real ElevenLabs account.**
  No ElevenLabs credentials were available. The dashboard field names below are from the
  ElevenLabs Agents product as I know it and were not re-checked against today's docs; confirm
  labels when you set it up.
- Voice is **read-only and inbound to the merchant only**: the merchant talks to the agent in the
  browser. There is no outbound calling code, and no tool can change the ledger.

## How it connects
```
Merchant's browser --(signed URL, mic)--> ElevenLabs agent --(HTTPS webhook tool + secret)--> this app's /api/v1/voice-tools/*
```
- The browser asks this app for a short-lived signed URL (`GET /api/v1/voice/session`, signed-in
  users only). The ElevenLabs API key stays on the server.
- The agent answers money questions only by calling the tools below. Each tool returns
  `spoken_answer`, text produced from ledger entries by this app; the agent reads it out.

## 1. Server environment
```bash
ELEVENLABS_API_KEY=...                 # server only
ELEVENLABS_AGENT_ID=...                # from step 2
VOICE_TOOL_SECRET=<random, 24+ chars>  # e.g. openssl rand -hex 32
VOICE_TOOL_MERCHANT_ID=mer_demo_a      # the one merchant this agent may read
pip install -r services/api/requirements-integrations.txt
```
The app must be reachable over HTTPS (the shared preview URL) so ElevenLabs can call the tools.

## 2. Create the agent (ElevenLabs dashboard → Agents)
- **Authentication**: turn on "require authentication" / private agent, so it can only be opened
  with a signed URL from this app.
- **Language**: English (India). Add Tamil if you want Tamil speech.
- **First message**: `Vanakkam. Ask me who promised to pay today, what a customer owes, or what has come in.`
- **System prompt**:
  ```
  You are the read-only voice helper for an Indian wholesale merchant's payment ledger.
  For ANY question about money, customers, promises or payments, call the ask_ledger tool with the
  merchant's question in their own words, then say the tool's spoken_answer exactly. Never invent,
  round or add numbers. If the tool has no answer, say you can only answer questions about pending
  money, today's promises, payments received and what a customer owes.
  You cannot record payments, send messages, call customers or change anything; say so if asked.
  Never ask for or repeat a UPI PIN, OTP or password. Keep answers short. Speak rupee amounts naturally.
  ```

## 3. Add the tools (type: Webhook / server tool)
Add this header to every tool, with the value stored as an ElevenLabs **secret**, not typed inline:

| Header | Value |
|---|---|
| `X-Voice-Tool-Secret` | the `VOICE_TOOL_SECRET` value |

Base URL: `https://<your-preview-host>/api/v1/voice-tools`

| Tool name | Method + URL | JSON body | Description to give the agent |
|---|---|---|---|
| `ask_ledger` (required) | `POST /ask` | `question` (string, required): the merchant's question, verbatim | "Answers any question about pending money, promises due today, payments received, or a customer's balance, from the merchant's ledger. Read-only." |
| `customer_balance` | `POST /customer-balance` | `customer_name` (string, required) | "What one customer still owes." |
| `customer_payments` | `POST /customer-payments` | `customer_name` (string, required) | "What one customer has paid, split into verified and unverified." |
| `today_promises` | `POST /today-promises` | none (`{}`) | "Who promised to pay today and how much." |
| `today_received` | `POST /today-received` | none (`{}`) | "Money confirmed as received today." |

`ask_ledger` alone is enough; the other four are narrower alternatives. Example response:
```json
{"spoken_answer": "2 promise(s) for today, ₹9,000 expected: Kavitha Supermarket ₹4,000 by cash; Murugan Stores ₹5,000 by upi. These are stated intentions, not receipts.", "tool": "get_today_promises", "read_only": true}
```

## 4. Test
```bash
curl -s -X POST https://<host>/api/v1/voice-tools/ask -H 'content-type: application/json' \
  -H "X-Voice-Tool-Secret: $VOICE_TOOL_SECRET" -d '{"question":"Who agreed to pay today?"}'
```
A wrong or missing secret returns 401. Then open the app → More → Ask the assistant → "Talk to
ElevenLabs voice agent" (the link appears only when the two ElevenLabs variables are set).

## What stays off
- No outbound calls or customer-facing voice. Do not attach a phone number or batch-calling to this agent.
- Do not connect the agent to WhatsApp; the app's customer messaging gate is separate and off.
- Tools are pinned to one merchant by `VOICE_TOOL_MERCHANT_ID`; a second merchant needs its own agent and secret.
