"use client";
import Link from "next/link";
import { useState } from "react";
import { inr } from "@/lib/api";

type Tone = "green" | "amber" | "red" | "blue" | "violet" | "gray";

const TONES: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-800 ring-emerald-600/25",
  amber: "bg-amber-50 text-amber-900 ring-amber-600/30",
  red: "bg-rose-50 text-rose-800 ring-rose-600/25",
  blue: "bg-sky-50 text-sky-800 ring-sky-600/25",
  violet: "bg-violet-50 text-violet-800 ring-violet-600/25",
  gray: "bg-slate-100 text-slate-700 ring-slate-500/20",
};

/** One vocabulary for every status in the product, so the same word always means the same thing. */
const STATUS: Record<string, [string, Tone]> = {
  // payments
  provider_verified: ["Provider verified", "green"],
  merchant_confirmed: ["Merchant confirmed", "green"],
  manual_unverified: ["Unverified claim", "amber"],
  authorised: ["Authorised, not captured", "amber"],
  pending: ["Pending", "gray"],
  failed: ["Failed", "red"],
  disputed: ["Disputed", "red"],
  reversed: ["Reversed", "red"],
  // invoices
  paid: ["Paid", "green"],
  partially_paid: ["Part paid", "blue"],
  unpaid: ["Unpaid", "gray"],
  // drafts
  needs_review: ["Needs review", "amber"],
  approved: ["Approved", "green"],
  rejected: ["Rejected", "gray"],
  // promises
  open: ["Promised", "blue"],
  kept: ["Kept", "green"],
  broken: ["Not kept", "red"],
  cancelled: ["Cancelled", "gray"],
  // requests / messages / events
  proposed: ["Awaiting approval", "amber"],
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
  "not configured": ["Not configured", "gray"],
  disabled: ["Disabled", "gray"],
  local: ["Local", "gray"],
  sqlite: ["SQLite", "gray"],
  postgresql: ["PostgreSQL", "gray"],
};

export function Badge({ status, label, tone }: { status?: string; label?: string; tone?: Tone }) {
  const [text, t] = status ? (STATUS[status] ?? [status.replaceAll("_", " "), "gray"]) : [label ?? "", tone ?? "gray"];
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone ?? t]}`}>
      {label ?? text}
    </span>
  );
}

/** Marks anything that did not involve the real world: simulated money, simulated messages. */
export function SimTag({ show = true }: { show?: boolean }) {
  return show ? <Badge label="Simulated" tone="violet" /> : null;
}

export function Card({ title, action, children, className = "" }: { title?: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-line bg-white ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({ label, paise, hint, tone = "text-ink" }: { label: string; paise: number; hint?: React.ReactNode; tone?: string }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4">
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className={`tabular mt-1 text-2xl font-semibold ${tone}`}>{inr(paise)}</p>
      {hint && <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, back, action }: { title: string; subtitle?: React.ReactNode; back?: { href: string; label: string }; action?: React.ReactNode }) {
  return (
    <div className="mb-4">
      {back && (
        <Link href={back.href} className="mb-1 inline-block text-sm text-brand hover:underline">
          ← {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {subtitle && <div className="mt-0.5 text-sm text-muted">{subtitle}</div>}
        </div>
        {action}
      </div>
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-8 text-sm text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />
      {label}…
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">
      <span>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="font-medium underline">
          Try again
        </button>
      )}
    </div>
  );
}

export function Notice({ tone = "violet", children }: { tone?: "violet" | "amber" | "blue"; children: React.ReactNode }) {
  const c = { violet: "border-violet-200 bg-violet-50 text-violet-900", amber: "border-amber-200 bg-amber-50 text-amber-900", blue: "border-sky-200 bg-sky-50 text-sky-900" }[tone];
  return <div className={`rounded-lg border px-3 py-2 text-sm ${c}`}>{children}</div>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-4 text-center text-sm text-muted">{children}</p>;
}

export function Button({ variant = "primary", busy, className = "", children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost"; busy?: boolean }) {
  const v = {
    primary: "bg-brand text-white hover:bg-[#0b4747]",
    secondary: "border border-line bg-white text-ink hover:bg-slate-50",
    danger: "border border-rose-300 bg-white text-rose-800 hover:bg-rose-50",
    ghost: "text-brand hover:bg-brand-soft",
  }[variant];
  return (
    <button {...rest} disabled={rest.disabled || busy} className={`inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${v} ${className}`}>
      {busy && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  );
}

export const inputCls = "w-full rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

export function Field({ label, error, hint, children }: { label: string; error?: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-muted">{hint}</span>}
      {error && <span className="mt-1 block text-xs font-medium text-rose-700">{error}</span>}
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

export function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <div className="-mx-4 overflow-x-auto px-4">
      <table className="w-full min-w-[520px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-muted">
            {head.map((h, i) => (
              <th key={i} className={`py-2 pr-3 font-medium ${h.startsWith("₹") ? "text-right" : ""}`}>
                {h.replace(/^₹/, "")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  );
}

export function AuditList({ items }: { items: { id: string; actor: string; action: string; data: Record<string, unknown>; created_at: string }[] }) {
  if (!items.length) return <Empty>No history yet.</Empty>;
  return (
    <ol className="space-y-2 text-sm">
      {items.map((a) => (
        <li key={a.id} className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-medium">{a.action.replaceAll("_", " ").replace(".", " · ")}</span>
          {typeof a.data.amount_paise === "number" && <span className="tabular">{inr(a.data.amount_paise as number)}</span>}
          <span className="text-xs text-muted">
            by {a.actor} · {new Date(a.created_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}
          </span>
        </li>
      ))}
    </ol>
  );
}
