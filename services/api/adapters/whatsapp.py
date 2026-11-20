"""WhatsApp adapters. Default is a local inbox simulator. The Meta Cloud API adapter is INBOUND ONLY:
signature-checked webhook parsing and media retrieval. No outbound send exists in this codebase."""
import hashlib
import hmac

import httpx

from app.config import Settings


class DemoWhatsAppAdapter:
    """Inbox simulator: messages are stored locally and flagged simulated. Nothing is sent anywhere."""
    channel = "demo_inbox"
    label = "simulated"


class MetaCloudWhatsAppAdapter:
    channel = "whatsapp"
    label = "live"

    def __init__(self, settings: Settings):
        self._s = settings

    @property
    def configured(self) -> bool:
        return bool(self._s.whatsapp_app_secret and self._s.whatsapp_verify_token)

    def verify_signature(self, raw_body: bytes, header: str | None) -> bool:
        """X-Hub-Signature-256: 'sha256=<hex hmac of raw body with the app secret>'."""
        secret = self._s.whatsapp_app_secret
        if not secret or not header or not header.startswith("sha256="):
            return False
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, header[7:])

    @staticmethod
    def parse_messages(body: dict) -> list[dict]:
        out = []
        for entry in body.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
                for m in value.get("messages") or []:
                    kind = m.get("type")
                    media = m.get(kind) if kind in ("image", "document", "audio") else None
                    out.append({"id": m.get("id"), "from": m.get("from"), "type": kind,
                                "phone_number_id": phone_number_id,
                                "text": (m.get("text") or {}).get("body") or (media or {}).get("caption") or "",
                                "media_id": (media or {}).get("id"), "mime_type": (media or {}).get("mime_type"),
                                "filename": (media or {}).get("filename")})
        return out

    def download_media(self, media_id: str) -> tuple[bytes, str]:
        """Two-step Graph API media retrieval. Requires WHATSAPP_ACCESS_TOKEN."""
        headers = {"Authorization": f"Bearer {self._s.whatsapp_access_token}"}
        base = f"https://graph.facebook.com/{self._s.whatsapp_graph_version}"
        with httpx.Client(timeout=30) as client:
            meta = client.get(f"{base}/{media_id}", headers=headers)
            meta.raise_for_status()
            info = meta.json()
            blob = client.get(info["url"], headers=headers)
            blob.raise_for_status()
            return blob.content, info.get("mime_type") or "application/octet-stream"
