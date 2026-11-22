# Shared demo preview: hosting requirements

**Nothing has been deployed.** This is the configuration proposed for your approval.

## Shape
One service, one HTTPS URL. The web app listens on `$PORT`; the API runs inside the same service on
`127.0.0.1:8000` and is reached only through the web app's `/api/*` proxy, so it is never directly
on the internet. Start command: `infra/start-preview.sh` (or the root `Dockerfile`).

| Requirement | Value |
|---|---|
| Instances | **Exactly 1** (the sample database and the wrong-code throttle live in that instance) |
| Memory / CPU | 1 GB / 1 vCPU is ample |
| HTTPS | Terminated by the host in front of `$PORT` |
| Disk | Ephemeral is fine; data is fictional and re-seeded on start |
| Outbound network | `generativelanguage.googleapis.com` (Gemini) and `api.elevenlabs.io`, only if those keys are set |
| Runtime | Node 22 + Python 3.11+ (the Dockerfile provides both) |

Any host that runs one container or one start command with HTTPS works (for example Cloud Run with
max instances 1, Render, Fly.io, or a small VM behind Caddy). Tell me which one and I will prepare
its exact config for you to approve.

## Lock-down is enforced, not just documented
`infra/start-preview.sh` sets `PREVIEW_MODE=true`, and the server **refuses to start** unless:

| Setting | Required | Why |
|---|---|---|
| `DEMO_ACCESS_CODE` | 8+ characters | Demo sign-in has no passwords; the code is the gate. 10 wrong codes from one address lock it for 5 minutes. |
| `DEMO_WEBHOOK_SECRET` | random, 24+ characters | The repo default is public. |
| `RAZORPAY_*` | empty | Payments stay simulated; no real money can move. |
| `WHATSAPP_*` | empty | No real WhatsApp number is connected. |
| `OUTBOUND_POLICY_APPROVED` | false | Customer messaging stays off. There is no outbound calling code. |
| `VOICE_TOOL_SECRET` | random, 24+ characters, if voice is configured | Protects the read-only voice tools. |

Optional: `GEMINI_API_KEY` (real bill reading), `ELEVENLABS_API_KEY` + `ELEVENLABS_AGENT_ID` +
`VOICE_TOOL_MERCHANT_ID` (voice). Set all secrets in the host's secret store, never in the repo.

Check a configuration without starting anything: `cd services/api && python -m app.preflight`.

Reset is owner-only and exists only in demo mode. Responses carry `X-Frame-Options: DENY`,
`nosniff`, `no-referrer` and `noindex`.

## Run it locally the same way
```bash
cd apps/web && npm ci && npm run build && cd ../..
DEMO_ACCESS_CODE='choose-a-code' DEMO_WEBHOOK_SECRET="$(openssl rand -hex 32)" PORT=3000 infra/start-preview.sh
```
To share from a laptop, put a tunnel you trust (Cloudflare Tunnel, ngrok) in front of port 3000.

## Shared-dataset limits (tell your audience)
- **Everyone with the link and code uses the same sample data.** Two people running the guided
  demo at once will see each other's bills, promises and payments, and one person's reset resets it for all.
- Use fictional data only. Uploaded files are stored unencrypted on the instance's disk and are
  lost when it restarts; with a Gemini key, uploaded files are sent to Google to be read.
- A restart or redeploy restores the seeded data and signs everyone out.
- There is no per-user rate limit beyond the access-code throttle and the daily Gemini cap.

## What was verified
- Locally: the start script refuses an unlocked config; with a locked config, sign-in without the
  code is refused, the app works through the single origin, security headers are present, and the
  API is bound to loopback.
- Not verified: the Dockerfile has **not been built** (no Docker daemon was available), and no
  hosting platform or real HTTPS endpoint has been tried.

## Before each judging session
Sign in as the owner → More → **Reset sample data only**. Home should show ₹25,900 owed.
