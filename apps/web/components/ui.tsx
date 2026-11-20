"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { inr } from "@/lib/api";

type Tone = "green" | "amber" | "orange" | "red" | "blue" | "violet" | "gray";

const TONES: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-800 ring-emerald-600/25",
  amber: "bg-amber-100 text-amber-900 ring-amber-600/30",
  orange: "bg-orange-50 text-orange-900 ring-orange-600/30",
  red: "bg-rose-50 text-rose-800 ring-rose-600/25",
  blue: "bg-sky-50 text-sky-800 ring-sky-600/25",
  violet: "bg-violet-50 text-violet-800 ring-violet-600/25",
  gray: "bg-stone-100 text-stone-700 ring-stone-500/20",
};

/** One vocabulary for every status in the product, so the same word always means the same thing. */
const STATUS: Record<string, [string, Tone]> = {
  // payments
  provider_verified: ["Verified", "green"],
  merchant_confirmed: ["Confirmed by you", "green"],
  manual_unverified: ["Not verified yet", "orange"],
  authorised: ["Authorised, not captured", "orange"],
  pending: ["Pending", "gray"],
  failed: ["Failed", "red"],
  disputed: ["Disputed", "red"],
  reversed: ["Reversed", "red"],
  // invoices
  paid: ["Paid", "green"],
  partially_paid: ["Part paid", "blue"],
  unpaid: ["Unpaid", "gray"],
  // drafts
  needs_review: ["Check and confirm", "amber"],
  approved: ["Approved", "green"],
  rejected: ["Discarded", "gray"],
  // promises
  open: ["Promised", "amber"],
  kept: ["Kept", "green"],
  broken: ["Not kept", "red"],
  cancelled: ["Cancelled", "gray"],
  // requests / messages / events
  proposed: ["Needs your approval", "blue"],
  draft: ["Draft", "gray"],
  sent_simulated: ["Delivered (simulated)", "violet"],
  blocked: ["Blocked by policy", "red"],
  received: ["Received", "gray"],
  processed: ["Processed", "green"],
  ignored: ["Ignored", "gray"],
  duplicate: ["Duplicate, not re-applied", "gray"],
  resolved: ["Resolved", "gray"],
  // integration labels
  simulated: ["Simulated", "violet"],
  live: ["Live", "green"],
  "test mode": ["Test mode", "blue"],
  "not configured": ["Not set up", "gray"],
  disabled: ["Off", "gray"],
  local: ["Local", "gray"],
  sqlite: ["SQLite", "gray"],
  postgresql: ["PostgreSQL", "gray"],
};

export function Badge({ status, label, tone }: { status?: string; label?: string; tone?: Tone }) {
  const [text, t] = status ? (STATUS[status] ?? [status.replaceAll("_", " "), "gray"]) : [label ?? "", tone ?? "gray"];
  return (
    <span className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${TONES[tone ?? t]}`}>
      {label ?? text}
    </span>
  );
}

/** Marks anything that did not involve the real world: simulated money, simulated messages. */
export function SimTag({ show = true }: { show?: boolean }) {
  return show ? <Badge label="Demo" tone="violet" /> : null;
}

export function Card({ title, action, children, className = "" }: { title?: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-line bg-white shadow-[0_1px_2px_rgb(27_36_32/0.04)] ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 px-4 pt-3.5">
          <h2 className="text-[13px] font-bold uppercase tracking-wide text-muted">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({ label, paise, hint, tone = "text-ink" }: { label: string; paise: number; hint?: React.ReactNode; tone?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-3">
      <p className="text-[11px] font-semibold leading-tight text-muted">{label}</p>
      <p className={`tabular mt-1 text-lg font-bold leading-tight ${tone}`}>{inr(paise)}</p>
      {hint && <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px] leading-tight text-muted">{hint}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, back, action }: { title: string; subtitle?: React.ReactNode; back?: { href: string; label: string }; action?: React.ReactNode }) {
  return (
    <div className="mb-3">
      {back && (
        <Link href={back.href} className="-ml-1 mb-1 inline-flex items-center gap-0.5 rounded-full px-1 py-0.5 text-sm font-medium text-brand">
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M15 5l-7 7 7 7" /></svg>
          {back.label}
        </Link>
      )}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[22px] font-bold leading-tight tracking-tight">{title}</h1>
          {subtitle && <div className="mt-0.5 text-sm text-muted">{subtitle}</div>}
        </div>
        {action}
      </div>
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-8 text-sm text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />
      {label}…
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">
      <span>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="font-semibold underline">
          Try again
        </button>
      )}
    </div>
  );
}

export function Notice({ tone = "violet", children }: { tone?: "violet" | "amber" | "blue"; children: React.ReactNode }) {
  const c = { violet: "border-violet-200 bg-violet-50 text-violet-900", amber: "border-amber-200 bg-amber-50 text-amber-900", blue: "border-sky-200 bg-sky-50 text-sky-900" }[tone];
  return <div className={`rounded-xl border px-3 py-2 text-[13px] leading-snug ${c}`}>{children}</div>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-4 text-center text-sm text-muted">{children}</p>;
}

export function Button({ variant = "primary", busy, className = "", children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost"; busy?: boolean }) {
  const v = {
    primary: "bg-brand text-white active:bg-brand-dark",
    secondary: "border border-line bg-white text-ink active:bg-stone-50",
    danger: "border border-rose-300 bg-white text-rose-800 active:bg-rose-50",
    ghost: "text-brand active:bg-brand-soft",
  }[variant];
  return (
    <button {...rest} disabled={rest.disabled || busy} className={`inline-flex min-h-11 items-center justify-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-45 ${v} ${className}`}>
      {busy && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  );
}

export const inputCls = "w-full min-h-11 rounded-xl border border-line px-3 py-2 text-[15px] outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

export function Field({ label, error, hint, children }: { label: string; error?: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-semibold">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-muted">{hint}</span>}
      {error && <span className="mt-1 block text-xs font-semibold text-rose-700">{error}</span>}
    </label>
  );
}

/** Runs an async action with busy + error state; used for every mutating button. */
export function useAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(null);
    }
  }
  return { busy, error, run, setError };
}

/** Pill tabs. Pass `href` options for navigation or `onChange` for in-page switching. */
export function Segmented({ options, value, onChange }: { options: { value: string; label: string; href?: string; count?: number }[]; value: string; onChange?: (v: string) => void }) {
  return (
    <div className="mb-3 flex gap-1 rounded-full bg-stone-200/70 p-1" role="tablist">
      {options.map((o) => {
        const cls = `flex-1 whitespace-nowrap rounded-full px-1 py-2 text-center text-[12.5px] font-semibold ${o.value === value ? "bg-white text-brand shadow-sm" : "text-muted"}`;
        const inner = (
          <>
            {o.label}
            {!!o.count && <span className="ml-1 rounded-full bg-rose-600 px-1.5 py-px text-[10px] text-white">{o.count}</span>}
          </>
        );
        return o.href ? (
          <Link key={o.value} href={o.href} role="tab" aria-selected={o.value === value} className={cls}>{inner}</Link>
        ) : (
          <button key={o.value} role="tab" aria-selected={o.value === value} className={cls} onClick={() => onChange?.(o.value)}>{inner}</button>
        );
      })}
    </div>
  );
}

/** Bottom sheet anchored to the phone viewport. */
export function Sheet({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: React.ReactNode }) {
  const [host, setHost] = useState<Element | null>(null);
  useEffect(() => setHost(document.querySelector(".phone")), []);
  if (!open || !host) return null;
  return createPortal(
    <div className="absolute inset-0 z-30 flex flex-col justify-end" role="dialog" aria-modal="true" aria-label={title}>
      <button aria-label="Close" className="fade-in absolute inset-0 bg-black/45" onClick={onClose} />
      <div className="sheet-up relative max-h-[88%] overflow-y-auto rounded-t-3xl bg-white px-4 pb-6 pt-2 scroll-area">
        <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-stone-300" />
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-lg font-bold">{title}</h2>
          <button onClick={onClose} className="rounded-full px-2 py-1 text-sm font-semibold text-muted">Close</button>
        </div>
        {children}
      </div>
    </div>,
    host,
  );
}

/** Round initials avatar, as in a chat list. */
export function Avatar({ name, size = "h-10 w-10 text-sm" }: { name: string; size?: string }) {
  const initials = name.split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("");
  const hues = ["bg-emerald-100 text-emerald-800", "bg-amber-100 text-amber-900", "bg-sky-100 text-sky-800", "bg-rose-100 text-rose-800", "bg-teal-100 text-teal-800"];
  const hue = hues[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % hues.length];
  return <span className={`flex shrink-0 items-center justify-center rounded-full font-bold ${size} ${hue}`} aria-hidden>{initials}</span>;
}

export function AuditList({ items }: { items: { id: string; actor: string; action: string; data: Record<string, unknown>; created_at: string }[] }) {
  if (!items.length) return <Empty>No history yet.</Empty>;
  return (
    <ol className="relative space-y-3 border-l-2 border-line pl-4 text-sm">
      {items.map((a) => (
        <li key={a.id} className="relative">
          <span className="absolute -left-[22px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-brand" />
          <p className="font-semibold capitalize leading-snug">
            {a.action.replaceAll("_", " ").replace(".", " ")}
            {typeof a.data.amount_paise === "number" && <span className="tabular ml-1.5 font-bold">{inr(a.data.amount_paise as number)}</span>}
          </p>
          <p className="text-xs text-muted">
            {a.actor.replaceAll("_", " ")} · {new Date(a.created_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}
          </p>
        </li>
      ))}
    </ol>
  );
}
