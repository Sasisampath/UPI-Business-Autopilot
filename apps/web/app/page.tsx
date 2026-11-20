"use client";
import Link from "next/link";
import { useState } from "react";
import { useMe } from "@/components/shell";
import { Avatar, Badge, Card, Empty, ErrorBox, Loading, SimTag, Stat } from "@/components/ui";
import { fmtDate, inr, useApi } from "@/lib/api";

interface PromiseRow {
  id: string;
  customer_id: string;
  customer_name: string;
  amount_paise: number;
  method: string;
  pickup_window: string | null;
  promised_date: string;
  evidence_text: string;
  simulated: boolean;
}

interface Contact {
  count: number;
  simulated_count: number;
}

interface Report {
  date: string;
  outstanding_paise: number;
  open_invoice_count: number;
  expected_today_paise: number;
  received: {
    provider_verified_paise: number;
    provider_verified_by_mode: Record<string, number>;
    merchant_confirmed_paise: number;
    confirmed_total_paise: number;
    unverified_claims_paise: number;
  };
  promises_due_today: PromiseRow[];
  promises_made_today: PromiseRow[];
  cash_pickups: PromiseRow[];
  contacted: Contact;
  replied: Contact;
  disputes: { id: string; customer_name: string | null; amount_paise: number }[];
  open_mismatches: { id: string; kind: string; detail: string }[];
  definitions: Record<string, string>;
}

const ACTIONS = [
  { href: "/bills", label: "Add bill", icon: "M6 3h12v18l-3-2-3 2-3-2-3 2V3zM12 8v6m-3-3h6" },
  { href: "/invoices", label: "UPI request", icon: "M4 12h13m-5-5l5 5-5 5M20 5v14" },
  { href: "/conversations", label: "Note promise", icon: "M4 5h16v11H10l-5 4v-4H4V5zm4.5 5.5l2.5 2.5 4.5-5" },
  { href: "/assistant", label: "Ask", icon: "M12 4a4 4 0 014 4v3a4 4 0 01-8 0V8a4 4 0 014-4zm-7 7a7 7 0 0014 0M12 18v3" },
];

export default function HomePage() {
  const me = useMe();
  const [date, setDate] = useState(me.today);
  const { data: r, error, loading, reload } = useApi<Report>(`/v1/reports/today?date=${date}`);
  const isToday = date === me.today;
  const first = me.name.split(/[\s(]/)[0];

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-sm text-muted">Vanakkam, {first}</p>
          <h1 className="text-[22px] font-bold leading-tight tracking-tight">{isToday ? "Today" : fmtDate(date)}</h1>
        </div>
        <label className="relative rounded-full border border-line bg-white px-3 py-1.5 text-xs font-semibold text-brand">
          {isToday ? fmtDate(date) : "Change day"}
          <input type="date" aria-label="Report date" className="absolute inset-0 cursor-pointer opacity-0" value={date} max={me.today} onChange={(e) => e.target.value && setDate(e.target.value)} />
        </label>
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !r && <Loading label="Getting today's numbers" />}
      {r && (
        <>
          <section className="rounded-3xl bg-brand p-4 text-white shadow-lg shadow-emerald-900/20">
            <p className="text-[13px] font-semibold text-white/80">Pending from customers</p>
            <p className="tabular mt-0.5 text-[40px] font-bold leading-none tracking-tight">{inr(r.outstanding_paise)}</p>
            <p className="mt-1.5 text-xs text-white/80">
              {r.open_invoice_count} open bill{r.open_invoice_count === 1 ? "" : "s"} · promises do not reduce this
            </p>
            <div className="mt-4 rounded-2xl bg-white/12 p-3">
              <CashBar received={r.received.confirmed_total_paise} expected={r.expected_today_paise} />
            </div>
          </section>

          <div className="grid grid-cols-3 gap-2">
            <Stat label="Received, confirmed" paise={r.received.confirmed_total_paise} tone="text-emerald-700" hint={<SimTag show={!!r.received.provider_verified_by_mode.simulated} />} />
            <Stat label={isToday ? "Promised for today" : "Promised that day"} paise={r.expected_today_paise} tone="text-amber-700" hint="Not money yet" />
            <Stat label="Not verified yet" paise={r.received.unverified_claims_paise} tone="text-orange-700" hint="Not counted" />
          </div>

          <div className="grid grid-cols-4 gap-2">
            {ACTIONS.map((a) => (
              <Link key={a.href} href={a.href} className="flex flex-col items-center gap-1.5 rounded-2xl border border-line bg-white px-1 py-3 text-center text-[11px] font-semibold leading-tight active:bg-brand-soft">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-soft text-brand">
                  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={a.icon} /></svg>
                </span>
                {a.label}
              </Link>
            ))}
          </div>

          <Card title="Ready to collect" action={r.promises_due_today.length > 0 ? <span className="tabular text-sm font-bold text-amber-700">{inr(r.expected_today_paise)}</span> : undefined}>
            {r.promises_due_today.length === 0 ? (
              <Empty>No customer has promised to pay {isToday ? "today" : "on this day"}.</Empty>
            ) : (
              <ul className="-my-1 divide-y divide-line">
                {r.promises_due_today.map((p) => (
                  <li key={p.id}>
                    <Link href={`/customers/${p.customer_id}`} className="flex items-center gap-3 py-2.5">
                      <Avatar name={p.customer_name} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[15px] font-semibold">{p.customer_name}</span>
                        <span className="mt-0.5 flex flex-wrap items-center gap-1">
                          {p.method === "cash" ? <Badge label={p.pickup_window ? `Cash pickup · ${p.pickup_window}` : "Cash"} tone="amber" /> : <Badge label={p.method === "upi" ? "UPI ready" : "Other"} tone="green" />}
                          <SimTag show={p.simulated} />
                        </span>
                      </span>
                      <span className="tabular text-base font-bold">{inr(p.amount_paise)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-[11px] text-muted">From what customers themselves said. A promise is not a payment.</p>
          </Card>

          {r.cash_pickups.length > 0 && (
            <Card title="Cash pickups this week">
              <ul className="-my-1 divide-y divide-line">
                {r.cash_pickups.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">{p.customer_name}</span>
                      <span className="text-xs text-muted">{fmtDate(p.promised_date)} · {p.pickup_window}</span>
                    </span>
                    <span className="tabular font-bold">{inr(p.amount_paise)}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-[11px] text-muted">Only customers who confirmed a pickup time are listed.</p>
            </Card>
          )}

          {(r.disputes.length > 0 || r.open_mismatches.some((m) => m.kind !== "dispute_open")) && (
            <Link href="/payments" className="block rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
              <p className="font-bold">Needs your attention</p>
              <p className="mt-0.5 text-[13px]">
                {r.disputes.length > 0 && `${r.disputes.length} disputed payment${r.disputes.length === 1 ? "" : "s"}. `}
                {r.open_mismatches.filter((m) => m.kind !== "dispute_open").length > 0 && `${r.open_mismatches.filter((m) => m.kind !== "dispute_open").length} payment mismatch to check. `}
                Tap to open Payments.
              </p>
            </Link>
          )}

          <Card title="Customer activity">
            <dl className="grid grid-cols-3 gap-2 text-center">
              <Activity label="Contacted" c={r.contacted} />
              <Activity label="Replied" c={r.replied} />
              <div>
                <dd className="tabular text-xl font-bold">{r.promises_made_today.length}</dd>
                <dt className="text-[11px] font-semibold text-muted">New promises</dt>
              </div>
            </dl>
            <p className="mt-2 text-[11px] leading-snug text-muted">Counted only from recorded messages. Demo inbox activity is shown separately, never as real contact.</p>
          </Card>

          <details className="rounded-2xl border border-line bg-white px-4 py-3 text-sm">
            <summary className="cursor-pointer font-semibold">How these numbers are counted</summary>
            <dl className="mt-2 space-y-1.5 text-xs leading-snug text-muted">
              {Object.entries(r.definitions).map(([k, v]) => (
                <div key={k}>
                  <dt className="inline font-semibold capitalize text-ink">{k.replaceAll("_", " ")}: </dt>
                  <dd className="inline">{v}</dd>
                </div>
              ))}
            </dl>
          </details>
        </>
      )}
    </div>
  );
}

function CashBar({ received, expected }: { received: number; expected: number }) {
  const max = Math.max(received, expected, 1);
  return (
    <div className="space-y-2 text-xs">
      {[
        { label: "Cash in, confirmed", value: received, color: "bg-white" },
        { label: "Promised for the day", value: expected, color: "bg-amber-300" },
      ].map((row) => (
        <div key={row.label}>
          <div className="flex justify-between font-semibold">
            <span className="text-white/85">{row.label}</span>
            <span className="tabular">{inr(row.value)}</span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/20">
            <div className={`h-full rounded-full ${row.color}`} style={{ width: `${(row.value / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function Activity({ label, c }: { label: string; c: Contact }) {
  return (
    <div>
      <dd className="tabular text-xl font-bold">{c.count}</dd>
      <dt className="text-[11px] font-semibold text-muted">{label}</dt>
      {c.simulated_count > 0 && <dd className="text-[11px] font-semibold text-violet-700">+{c.simulated_count} demo</dd>}
    </div>
  );
}
