"use client";
import { useEffect, useRef, useState } from "react";
import { api, post } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, inputCls } from "./ui";

const SUGGESTIONS = ["Who agreed to pay today?", "How much did Murugan Stores pay?", "What is my confirmed cash in?"];

interface Answer {
  answer: string;
  tool: string | null;
  routed_by: string;
  evidence: Record<string, unknown>;
}

interface VoiceSession {
  provider: string;
  label: string;
  signed_url: string | null;
  note: string;
}

/** Read-only merchant assistant: text, browser speech, or an ElevenLabs agent when configured. */
export function Assistant() {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [speak, setSpeak] = useState(false);
  const [voice, setVoice] = useState<VoiceSession | null>(null);
  const [live, setLive] = useState<{ status: string; lines: string[] } | null>(null);
  const liveRef = useRef<{ endSession: () => Promise<void> } | null>(null);
  const [canListen, setCanListen] = useState(false);

  useEffect(() => {
    setCanListen("webkitSpeechRecognition" in window || "SpeechRecognition" in window);
    api<VoiceSession>("/v1/voice/session").then(setVoice).catch(() => setVoice(null));
    return () => {
      liveRef.current?.endSession().catch(() => {});
      window.speechSynthesis?.cancel();
    };
  }, []);

  async function ask(q: string, readAloud = speak) {
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    setAsked(q);
    try {
      const a = await post<Answer>("/v1/assistant/ask", { question: q });
      setAnswer(a);
      setQuestion("");
      if (readAloud && window.speechSynthesis) {
        const u = new SpeechSynthesisUtterance(a.answer.replaceAll("₹", "rupees "));
        u.lang = "en-IN";
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(u);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function listen() {
    const w = window as unknown as Record<string, any>;
    const Rec = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Rec) return;
    const rec = new Rec();
    rec.lang = "en-IN";
    rec.onresult = (e: any) => {
      const text = e.results[0][0].transcript as string;
      setQuestion(text);
      setSpeak(true);
      ask(text, true);
    };
    rec.onerror = () => setError("Could not hear that. Check microphone permission, or type your question.");
    rec.onend = () => setListening(false);
    setListening(true);
    rec.start();
  }

  async function toggleLive() {
    if (liveRef.current) {
      await liveRef.current.endSession().catch(() => {});
      liveRef.current = null;
      return setLive(null);
    }
    if (!voice?.signed_url) return;
    setLive({ status: "Connecting", lines: [] });
    try {
      const { Conversation } = await import("@elevenlabs/client");
      liveRef.current = await Conversation.startSession({
        signedUrl: voice.signed_url,
        onMessage: (m: { message: string; source?: string }) =>
          setLive((l) => l && { ...l, lines: [...l.lines.slice(-5), `${m.source === "user" ? "You" : "Agent"}: ${m.message}`] }),
        onError: (message: string) => setError(`Voice agent: ${message}`),
        onDisconnect: () => ((liveRef.current = null), setLive(null)),
      });
      setLive((l) => l && { ...l, status: "Listening" });
    } catch (e) {
      setLive(null);
      setError(`Could not start the voice agent: ${(e as Error).message}`);
    }
  }

  return (
    <Card title="Ask about your money" action={<Badge label="Read-only" tone="gray" />}>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <input className={inputCls} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask in plain words…" aria-label="Question" maxLength={500} />
        {canListen && (
          <Button type="button" variant="secondary" onClick={listen} busy={listening} aria-label="Ask by voice">
            {listening ? "Listening" : "Speak"}
          </Button>
        )}
        <Button type="submit" busy={busy}>
          Ask
        </Button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => ask(s)} className="rounded-full border border-line px-2.5 py-1 text-xs text-ink hover:border-brand hover:bg-brand-soft">
            {s}
          </button>
        ))}
      </div>
      {error && (
        <div className="mt-3">
          <ErrorBox message={error} />
        </div>
      )}
      {answer && (
        <div className="mt-3 rounded-lg bg-brand-soft p-3" aria-live="polite">
          <p className="text-xs text-muted">{asked}</p>
          <p className="mt-1 text-sm font-medium leading-relaxed">{answer.answer}</p>
          <details className="mt-2 text-xs text-muted">
            <summary className="cursor-pointer">
              Evidence · {answer.tool ? `tool ${answer.tool}` : "no tool matched"} · routed by {answer.routed_by}
            </summary>
            <pre className="mt-1 max-h-48 overflow-auto rounded bg-white p-2 text-[11px] leading-snug text-ink">{JSON.stringify(answer.evidence, null, 2)}</pre>
          </details>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={speak} onChange={(e) => setSpeak(e.target.checked)} /> Read answers aloud
        </label>
        {voice?.signed_url ? (
          <button className="font-medium text-brand underline" onClick={toggleLive}>
            {live ? `End ElevenLabs voice agent (${live.status})` : "Talk to the ElevenLabs voice agent"}
          </button>
        ) : (
          <span>Voice: browser speech (simulated voice layer; ElevenLabs not configured).</span>
        )}
      </div>
      {live && live.lines.length > 0 && (
        <ul className="mt-2 space-y-1 rounded-lg border border-line p-2 text-xs">
          {live.lines.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}
