"use client";
import Link from "next/link";
import { useState } from "react";
import { Assistant } from "@/components/assistant";
import { useMe } from "@/components/shell";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, SimTag, Stat } from "@/components/ui";
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
  customers: { customer_id: string; customer_name: string; simulated: boolean }[];
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
    disputed_paise: number;
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

export default function TodayPage() {
  const me = useMe();
  const [date, setDate] = useState(me.today);
  const { data: r, error, loading, reload } = useApi<Report>(`/v1/reports/today?date=${date}`);

  return (
    <>
      <PageHeader
        title={date === me.today ? "Today" : "Daily report"}
        subtitle={fmtDate(date)}
        action={<input type="date" aria-label="Report date" className="rounded-lg border border-line bg-white px-3 py-2 text-sm" value={date} max={me.today} onChange={(e) => e.target.value && setDate(e.target.value)} />}
      />
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !r && <Loading label="Loading report" />}
      {r && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Pending from customers" paise={r.outstanding_paise} hint={`${r.open_invoice_count} open invoice${r.open_invoice_count === 1 ? "" : "s"}`} />
            <Stat
              label="Confirmed received"
              paise={r.received.confirmed_total_paise}
              tone="text-emerald-700"
              hint={
                <>
                  {inr(r.received.provider_verified_paise)} provider verified
                  <SimTag show={!!r.received.provider_verified_by_mode.simulated} />
                  {r.received.merchant_confirmed_paise > 0 && <span>· {inr(r.received.merchant_confirmed_paise)} merchant confirmed</span>}
                </>
              }
            />
            <Stat label="Promised for this day" paise={r.expected_today_paise} tone="text-sky-700" hint="Stated intentions, not money" />
            <Stat label="Claimed, not verified" paise={r.received.unverified_claims_paise} tone="text-amber-700" hint="Not counted as received" />
          </div>

          <Card title="Cash in vs expected">
            <CashBar received={r.received.confirmed_total_paise} expected={r.expected_today_paise} />
          </Card>

          {date === me.today && <Assistant />}

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Customers who promised to pay this day">
              {r.promises_due_today.length === 0 ? <Empty>No promises are dated for this day.</Empty> : <PromiseList rows={r.promises_due_today} />}
            </Card>
            <Card title="Proposed collection visits" action={<Badge label="Confirmed availability only" tone="gray" />}>
              {r.cash_pickups.length === 0 ? (
                <Empty>No customer has confirmed a cash pickup time in the next 7 days.</Empty>
              ) : (
                <ul className="divide-y divide-line">
                  {r.cash_pickups.map((p) => (
                    <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                      <div className="min-w-0">
                        <Link href={`/customers/${p.customer_id}`} className="font-medium hover:underline">
                          {p.customer_name}
                        </Link>
                        <p className="text-xs text-muted">
                          {fmtDate(p.promised_date)} · {p.pickup_window} <SimTag show={p.simulated} />
                        </p>
                      </div>
                      <span className="tabular font-medium">{inr(p.amount_paise)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Customer activity">
              <dl className="grid grid-cols-3 gap-3 text-sm">
                <Activity label="Contacted" c={r.contacted} />
                <Activity label="Replied" c={r.replied} />
                <div>
                  <dt className="text-xs text-muted">New promises</dt>
                  <dd className="tabular mt-0.5 text-lg font-semibold">{r.promises_made_today.length}</dd>
                </div>
              </dl>
              <p className="mt-3 text-xs text-muted">Counts come only from recorded messages. Simulated inbox activity is shown separately and never counted as real contact.</p>
            </Card>
            <Card title="Needs your attention" action={<Link href="/payments" className="text-sm text-brand hover:underline">Open payments</Link>}>
              {r.disputes.length + r.open_mismatches.length === 0 ? (
                <Empty>No disputes or unresolved mismatches.</Empty>
              ) : (
                <ul className="space-y-2 text-sm">
                  {r.disputes.map((d) => (
                    <li key={d.id} className="flex items-center justify-between gap-2">
                      <span>
                        <Badge status="disputed" /> {d.customer_name ?? "Unknown payer"}
                      </span>
                      <span className="tabular">{inr(d.amount_paise)}</span>
                    </li>
                  ))}
                  {r.open_mismatches.filter((m) => m.kind !== "dispute_open").map((m) => (
                    <li key={m.id}>
                      <Badge label={m.kind.replaceAll("_", " ")} tone="amber" /> <span className="text-muted">{m.detail}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <details className="rounded-xl border border-line bg-white px-4 py-3 text-sm">
            <summary className="cursor-pointer font-medium">How these numbers are defined</summary>
            <dl className="mt-2 space-y-1.5 text-xs text-muted">
              {Object.entries(r.definitions).map(([k, v]) => (
                <div key={k}>
                  <dt className="inline font-medium text-ink">{k.replaceAll("_", " ")}: </dt>
                  <dd className="inline">{v}</dd>
                </div>
              ))}
            </dl>
          </details>
        </div>
      )}
    </>
  );
}

function CashBar({ received, expected }: { received: number; expected: number }) {
  const max = Math.max(received, expected, 1);
  return (
    <div className="space-y-2 text-sm">
      {[
        { label: "Confirmed received", value: received, color: "bg-emerald-600" },
        { label: "Promised (expected)", value: expected, color: "bg-sky-500" },
      ].map((row) => (
        <div key={row.label} className="grid grid-cols-[9.5rem_1fr_auto] items-center gap-3">
          <span className="text-muted">{row.label}</span>
          <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
            <div className={`h-full rounded-full ${row.color}`} style={{ width: `${(row.value / max) * 100}%` }} />
          </div>
          <span className="tabular font-medium">{inr(row.value)}</span>
        </div>
      ))}
      <p className="text-xs text-muted">Shown side by side, never added together: a receipt may or may not be the payment that was promised.</p>
    </div>
  );
}

function PromiseList({ rows }: { rows: PromiseRow[] }) {
  return (
    <ul className="divide-y divide-line">
      {rows.map((p) => (
        <li key={p.id} className="py-2 text-sm">
          <div className="flex items-center justify-between gap-3">
            <Link href={`/customers/${p.customer_id}`} className="font-medium hover:underline">
              {p.customer_name}
            </Link>
            <span className="tabular font-medium">{inr(p.amount_paise)}</span>
          </div>
          <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
            <Badge label={p.method.toUpperCase()} tone="blue" />
            <SimTag show={p.simulated} />
            <span className="truncate">“{p.evidence_text}”</span>
          </p>
        </li>
      ))}
    </ul>
  );
}

function Activity({ label, c }: { label: string; c: Contact }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="tabular mt-0.5 text-lg font-semibold">{c.count}</dd>
      {c.simulated_count > 0 && <dd className="text-xs text-violet-700">+{c.simulated_count} simulated</dd>}
    </div>
  );
}
