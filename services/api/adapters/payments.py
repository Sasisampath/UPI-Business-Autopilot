"""Payment providers. Both speak the same Razorpay-shaped webhook envelope so one deterministic
reconciliation path serves the simulator and the real test-mode provider."""
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass

from app.config import Settings


@dataclass
class ProviderRequest:
    provider_ref: str
    link_url: str


def _hmac_hex(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


class DemoPaymentProvider:
    """Deterministic mock. No money moves; everything it produces is labelled `simulated`."""
    name = "demo"
    mode = "simulated"

    def __init__(self, settings: Settings):
        self._secret = settings.demo_webhook_secret
        self._web = settings.web_base_url.rstrip("/")

    def verify_signature(self, raw_body: bytes, signature: str | None) -> bool:
        return bool(signature) and hmac.compare_digest(_hmac_hex(self._secret, raw_body), signature)

    def create_payment_request(self, request_id: str, amount_paise: int, description: str) -> ProviderRequest:
        ref = f"demo_plink_{uuid.uuid4().hex[:12]}"
        return ProviderRequest(provider_ref=ref, link_url=f"{self._web}/payments?simulate={request_id}")

    # --- simulator side: what a provider would send us -------------------------------------
    def build_event(self, *, event_type: str, account_id: str, payment_id: str, amount_paise: int,
                    currency: str = "INR", payment_request_id: str | None = None, method: str = "upi",
                    created_at: int | None = None, event_id: str | None = None) -> tuple[bytes, str, str]:
        """Returns (raw_body, signature, event_id) for a signed provider event."""
        notes = {"payment_request_id": payment_request_id} if payment_request_id else {}
        status = {"payment.captured": "captured", "payment.authorized": "authorized",
                  "payment.failed": "failed"}.get(event_type, "captured")
        payload: dict = {"payment": {"entity": {"id": payment_id, "amount": amount_paise, "currency": currency,
                                                "status": status, "method": method, "notes": notes,
                                                "created_at": created_at}}}
        if event_type.startswith("refund."):
            payload["refund"] = {"entity": {"id": f"rfnd_{uuid.uuid4().hex[:10]}", "payment_id": payment_id,
                                            "amount": amount_paise, "currency": currency}}
        if event_type.startswith("payment.dispute."):
            payload["dispute"] = {"entity": {"id": f"disp_{uuid.uuid4().hex[:10]}", "payment_id": payment_id,
                                             "amount": amount_paise, "currency": currency,
                                             "reason_code": "simulated_dispute"}}
        body = json.dumps({"entity": "event", "account_id": account_id, "event": event_type,
                           "contains": list(payload), "payload": payload}, separators=(",", ":")).encode()
        return body, _hmac_hex(self._secret, body), event_id or f"evt_{uuid.uuid4().hex[:16]}"


class RazorpayProvider:
    """Razorpay TEST MODE only. Live keys are refused. Not exercised against a real account in this MVP."""
    name = "razorpay"
    mode = "test"

    def __init__(self, settings: Settings):
        self._s = settings

    @property
    def configured(self) -> bool:
        s = self._s
        return bool(s.razorpay_key_id and s.razorpay_key_secret and s.razorpay_webhook_secret
                    and s.razorpay_key_id.startswith("rzp_test_"))

    def verify_signature(self, raw_body: bytes, signature: str | None) -> bool:
        secret = self._s.razorpay_webhook_secret
        if not secret or not signature:
            return False
        return hmac.compare_digest(_hmac_hex(secret, raw_body), signature)

    def create_payment_request(self, request_id: str, amount_paise: int, description: str) -> ProviderRequest:
        if not self.configured:
            raise RuntimeError("Razorpay test-mode keys (rzp_test_...) and webhook secret are not configured")
        import razorpay  # optional dependency

        client = razorpay.Client(auth=(self._s.razorpay_key_id, self._s.razorpay_key_secret))
        # One independent link per requested amount (UPI links do not support partial payments).
        # notify=false: the provider never contacts the customer; the merchant shares the link themselves.
        link = client.payment_link.create({
            "amount": amount_paise, "currency": "INR", "accept_partial": False, "description": description[:250],
            "reference_id": request_id, "notes": {"payment_request_id": request_id},
            "notify": {"sms": False, "email": False}, "reminder_enable": False,
        })
        return ProviderRequest(provider_ref=link["id"], link_url=link["short_url"])


def get_provider(name: str, settings: Settings):
    if name == "demo":
        return DemoPaymentProvider(settings)
    if name == "razorpay":
        return RazorpayProvider(settings)
    raise KeyError(name)
