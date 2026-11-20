"""Voice adapters. Voice is a read-only layer over the assistant tools; it never mutates the ledger."""
from app.config import Settings


class DemoVoiceAdapter:
    """No external service: the browser's own speech recognition/synthesis drives the text assistant."""
    name = "browser_speech"
    label = "simulated"

    def session(self) -> dict:
        return {"provider": self.name, "label": self.label, "signed_url": None,
                "note": "Browser speech (Web Speech API) over the read-only text assistant. No ElevenLabs credentials configured."}


class ElevenLabsVoiceAdapter:
    """ElevenLabs Agents browser session. Returns a short-lived signed URL; the API key stays server-side.
    Not exercised against a live account in this MVP."""
    name = "elevenlabs"
    label = "live"

    def __init__(self, settings: Settings):
        self._s = settings

    def session(self) -> dict:
        from elevenlabs.client import ElevenLabs  # optional dependency

        client = ElevenLabs(api_key=self._s.elevenlabs_api_key)
        res = client.conversational_ai.conversations.get_signed_url(agent_id=self._s.elevenlabs_agent_id)
        return {"provider": self.name, "label": self.label, "signed_url": res.signed_url,
                "note": "ElevenLabs agent session. The agent must be configured with the /v1/voice-tools/* server tools."}


def get_voice_adapter(settings: Settings):
    if settings.elevenlabs_api_key and settings.elevenlabs_agent_id:
        return ElevenLabsVoiceAdapter(settings)
    return DemoVoiceAdapter()
