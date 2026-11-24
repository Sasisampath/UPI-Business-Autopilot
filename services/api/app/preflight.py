"""Shared-preview guard. With PREVIEW_MODE=true the server refuses to start unless it is locked
down: demo data only, an access code, non-default secrets, and no credential that could move real
money or message real customers."""
from .config import Settings

DEFAULT_WEBHOOK_SECRET = "demo-webhook-secret-change-me"


def preview_problems(s: Settings) -> list[str]:
    problems = []
    if not s.demo_mode:
        problems.append("DEMO_MODE must be true (the preview has no production sign-in).")
    if not s.demo_access_code or len(s.demo_access_code) < 8:
        problems.append("DEMO_ACCESS_CODE must be set to at least 8 characters.")
    if s.demo_webhook_secret == DEFAULT_WEBHOOK_SECRET or len(s.demo_webhook_secret) < 24:
        problems.append("DEMO_WEBHOOK_SECRET must be a random value of at least 24 characters (not the repo default).")
    if s.razorpay_key_id or s.razorpay_key_secret or s.razorpay_webhook_secret:
        problems.append("RAZORPAY_* must be empty: a shared preview uses simulated payments only.")
    if s.whatsapp_access_token or s.whatsapp_app_secret:
        problems.append("WHATSAPP_* must be empty: a shared preview must not be connected to a real WhatsApp number.")
    if s.outbound_policy_approved or s.outbound_approved_message_types:
        problems.append("OUTBOUND_POLICY_APPROVED must be false and OUTBOUND_APPROVED_MESSAGE_TYPES empty.")
    if (s.elevenlabs_api_key or s.voice_tool_merchant_id) and (not s.voice_tool_secret or len(s.voice_tool_secret) < 24):
        problems.append("VOICE_TOOL_SECRET must be a random value of at least 24 characters when voice is configured.")
    if s.database_url.startswith("sqlite") is False and "localhost" not in s.database_url and "sslmode" not in s.database_url:
        problems.append("DATABASE_URL points at a remote PostgreSQL without sslmode; add ?sslmode=require.")
    return problems


def enforce(s: Settings) -> None:
    if s.preview_mode and (problems := preview_problems(s)):
        raise RuntimeError("PREVIEW_MODE is on but the server is not locked down:\n- " + "\n- ".join(problems))


if __name__ == "__main__":  # `python -m app.preflight`: print problems and exit non-zero if any
    import sys

    from .config import get_settings

    found = preview_problems(get_settings())
    print("Preview lock-down check: " + ("OK" if not found else "NOT READY\n- " + "\n- ".join(found)))
    sys.exit(1 if found else 0)
