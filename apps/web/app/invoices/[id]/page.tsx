"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ManualReceipt, PaymentRow, ProposeRequest, RequestRow } from "@/components/payments";
import { useMe } from "@/components/shell";
import { AuditList, Badge, Card, Empty, ErrorBox, Loading, PageHeader, SimTag, Table } from "@/components/ui";
import { fmtDate, fmtDateTime, inr, useApi } from "@/lib/api";
import type { Audit, Invoice, Payment, PaymentRequest, PromiseRow } from "@/lib/types";

interface Detail extends Invoice {
  draft_id: string | null;
  lines: { description: string; quantity: string; unit_price_paise: number; line_total_paise: number }[];
  allocations: { id: string; payment_id: string; amount_paise: number; kind: string; reason: string | null; created_by: string; created_at: string }[];
  payments: Payment[];
  payment_requests: PaymentRequest[];
  promises: PromiseRow[];
  promised_open_paise: number;
  audit: Audit[];
}

export default function InvoicePage() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const { data: inv, error, loading, reload } = useApi<Detail>(`/v1/invoices/${id}`);
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (loading && !inv) return <Loading label="Loading invoice" />;
  if (!inv) return null;
  const canWrite = me.role !== "viewer";
  let running = inv.total_paise;

  return (
    <>
      <PageHeader
        title={inv.number}
        back={{ href: "/invoices", label: "Invoices" }}
        subtitle={<><Link href={`/customers/${inv.customer_id}`} className="text-brand hover:underline">{inv.customer_name}</Link> · {fmtDate(inv.invoice_date)}</>}
        action={<Badge status={inv.status} />}
      />
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            { label: "Invoice total", v: inv.total_paise, c: "" },
            { label: "Confirmed received", v: inv.allocated_paise, c: "text-emerald-700" },
            { label: "Still due", v: inv.due_paise, c: "" },
            { label: "Promised (not received)", v: inv.promised_open_paise, c: "text-sky-700" },
          ].map((s) => (
            <div key={s.label} className="rounded-xl border border-line bg-white p-4">
              <p className="text-xs font-medium text-muted">{s.label}</p>
              <p className={`tabular mt-1 text-xl font-semibold ${s.c}`}>{inr(s.v)}</p>
            </div>
          ))}
        </div>

        <Card title="How the balance was reached">
          <ol className="space-y-1.5 text-sm">
            <li className="flex justify-between"><span>Invoice issued</span><span className="tabular font-medium">{inr(inv.total_paise)}</span></li>
            {inv.allocations.map((a) => {
              running -= a.amount_paise;
              const pay = inv.payments.find((p) => p.id === a.payment_id);
              return (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-x-3">
                  <span className="flex flex-wrap items-center gap-1.5">
                    {a.kind === "reversal" ? <Badge label="Reversal" tone="red" /> : <Badge label="Receipt applied" tone="green" />}
                    <SimTag show={pay?.mode === "simulated"} />
                    <span className="text-xs text-muted">{fmtDateTime(pay?.received_at ?? a.created_at)}</span>
                  </span>
                  <span className="tabular">
                    {a.amount_paise > 0 ? "−" : "+"}{inr(Math.abs(a.amount_paise))} <span className="text-muted">→ due {inr(running)}</span>
                  </span>
                </li>
              );
            })}
            <li className="flex justify-between border-t border-line pt-1.5 font-semibold"><span>Due now</span><span className="tabular">{inr(inv.due_paise)}</span></li>
          </ol>
          <p className="mt-2 text-xs text-muted">Entries are never edited or deleted; corrections appear as reversals. Promises and unverified claims are not in this list.</p>
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Receipts">
            {inv.payments.length === 0 ? <Empty>No receipts recorded for this invoice.</Empty> : (
              <ul className="divide-y divide-line">{inv.payments.map((p) => <PaymentRow key={p.id} p={p} onChange={reload} />)}</ul>
            )}
            {canWrite && inv.due_paise > 0 && <div className="mt-2"><ManualReceipt invoiceId={inv.id} customerId={inv.customer_id} onChange={reload} /></div>}
          </Card>
          <Card title="UPI payment requests">
            {inv.payment_requests.length === 0 ? <Empty>No payment requests yet.</Empty> : (
              <ul className="divide-y divide-line">{inv.payment_requests.map((r) => <RequestRow key={r.id} r={r} onChange={reload} />)}</ul>
            )}
            {canWrite && inv.due_paise > 0 && <div className="mt-3 border-t border-line pt-3"><ProposeRequest invoiceId={inv.id} duePaise={inv.due_paise} onChange={reload} /></div>}
            {inv.due_paise === 0 && <p className="mt-2 text-xs text-muted">This invoice is fully paid; no further requests can be prepared.</p>}
          </Card>
        </div>

        <Card title="Promises on this invoice" action={<Link href={`/conversations?customer=${inv.customer_id}`} className="text-sm text-brand hover:underline">Record a promise</Link>}>
          {inv.promises.length === 0 ? <Empty>The customer has not stated when they will pay.</Empty> : (
            <ul className="divide-y divide-line">
              {inv.promises.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="flex flex-wrap items-center gap-1.5"><Badge status={p.status} /> {fmtDate(p.promised_date)} · {p.method.toUpperCase()} <SimTag show={p.simulated} /></span>
                  <span className="tabular font-medium">{inr(p.amount_paise)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Items">
          <Table head={["Description", "₹Qty", "₹Unit price", "₹Amount"]}>
            {inv.lines.map((l, i) => (
              <tr key={i}>
                <td className="py-2 pr-3">{l.description}</td>
                <td className="tabular py-2 pr-3 text-right">{l.quantity}</td>
                <td className="tabular py-2 pr-3 text-right">{inr(l.unit_price_paise)}</td>
                <td className="tabular py-2 pr-3 text-right">{inr(l.line_total_paise)}</td>
              </tr>
            ))}
            {inv.tax_paise > 0 && <tr><td colSpan={3} className="py-2 pr-3 text-right text-muted">Tax</td><td className="tabular py-2 pr-3 text-right">{inr(inv.tax_paise)}</td></tr>}
            <tr><td colSpan={3} className="py-2 pr-3 text-right font-semibold">Total</td><td className="tabular py-2 pr-3 text-right font-semibold">{inr(inv.total_paise)}</td></tr>
          </Table>
          {inv.draft_id && <p className="mt-2 text-xs text-muted">Created from a reviewed bill. <Link href={`/bills/${inv.draft_id}`} className="text-brand underline">See the original</Link></p>}
        </Card>

        <Card title="History"><AuditList items={inv.audit} /></Card>
      </div>
    </>
  );
}
