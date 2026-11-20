"use client";
import { useState } from "react";
import { PaymentRow, RequestRow } from "@/components/payments";
import { useMe } from "@/components/shell";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, Notice, PageHeader, Table, inputCls, useAction } from "@/components/ui";
import { fmtDateTime, inr, parseRupees, post, useApi } from "@/lib/api";
import type { Payment, PaymentRequest } from "@/lib/types";

interface Mismatch {
  id: string;
  kind: string;
  detail: string;
  status: string;
  resolution_note: string | null;
}

interface WebhookEvent {
  id: string;
  provider: string;
  event_id: string | null;
  event_type: string | null;
  signature_valid: boolean;
  status: string;
  detail: string | null;
  duplicate_deliveries: number;
  received_at: string;
}

const EVENTS: Record<string, string> = {
  "payment.captured": "Payment captured",
  "payment.authorized": "Authorised only (not captured)",
  "payment.failed": "Payment failed",
  "refund.processed": "Refund of an existing payment",
  "payment.dispute.created": "Dispute on an existing payment",
};

export default function PaymentsPage() {
  const me = useMe();
  const payments = useApi<Payment[]>("/v1/payments");
  const requests = useApi<PaymentRequest[]>("/v1/payment-intents");
  const mismatches = useApi<Mismatch[]>("/v1/mismatches");
  const events = useApi<WebhookEvent[]>("/v1/webhook-events");
  const reloadAll = () => (payments.reload(), requests.reload(), mismatches.reload(), events.reload());

  const [eventType, setEventType] = useState("payment.captured");
  const [target, setTarget] = useState("");
  const [amount, setAmount] = useState("");
  const [twice, setTwice] = useState(false);
  const [tamper, setTamper] = useState(false);
  const [result, setResult] = useState<{ deliveries: { http_status: number; status: string; detail: string }[] } | null>(null);
  const act = useAction();

  const needsPayment = eventType === "refund.processed" || eventType === "payment.dispute.created";
  const approved = requests.data?.filter((r) => r.status === "approved" && r.mode === "simulated") ?? [];
  const demoPayments = payments.data?.filter((p) => p.provider === "demo") ?? [];
  const open = mismatches.data?.filter((m) => m.status === "open" && m.kind !== "dispute_open") ?? [];
  const pendingRequests = requests.data?.filter((r) => ["proposed", "approved"].includes(r.status)) ?? [];

  const simulate = () =>
    act.run("sim", async () => {
      const body: Record<string, unknown> = { event_type: eventType, deliver_twice: twice, tamper_signature: tamper };
      if (needsPayment) body.payment_id = target;
      else if (target) body.payment_request_id = target;
      const paise = parseRupees(amount);
      if (paise) body.amount_paise = paise;
      setResult(await post("/v1/demo/simulate-payment-event", body));
      reloadAll();
    });
  const error = payments.error ?? requests.error ?? mismatches.error ?? events.error;

  return (
    <>
      <PageHeader title="Payment verification" subtitle="Only a signed provider event or an owner's confirmation changes a balance." />
      <div className="space-y-4">
        {error && <ErrorBox message={error} onRetry={reloadAll} />}

        <Card title="Unresolved mismatches">
          {mismatches.loading && !mismatches.data && <Loading />}
          {mismatches.data && open.length === 0 && <Empty>Nothing to resolve.</Empty>}
          <ul className="divide-y divide-line">
            {open.map((m) => <MismatchRow key={m.id} m={m} onChange={reloadAll} owner={me.role === "owner"} />)}
          </ul>
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Receipts">
            {payments.loading && !payments.data && <Loading />}
            {payments.data?.length === 0 && <Empty>No receipts yet.</Empty>}
            <ul className="divide-y divide-line">{payments.data?.map((p) => <PaymentRow key={p.id} p={p} onChange={reloadAll} showCustomer />)}</ul>
          </Card>
          <div className="space-y-4">
            <Card title="Payment requests in progress">
              {requests.data && pendingRequests.length === 0 && <Empty>No open requests. Prepare one from an invoice.</Empty>}
              <ul className="divide-y divide-line">{pendingRequests.map((r) => <RequestRow key={r.id} r={r} onChange={reloadAll} showInvoice />)}</ul>
            </Card>

            {me.demo_mode && me.role !== "viewer" && (
              <Card title="Demo provider simulator" action={<Badge label="Simulated money" tone="violet" />}>
                <div className="space-y-3">
                  <Field label="Event the provider sends">
                    <select className={inputCls} value={eventType} onChange={(e) => (setEventType(e.target.value), setTarget(""))}>
                      {Object.entries(EVENTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </Field>
                  <Field label={needsPayment ? "Existing demo payment" : "For payment request"} hint={needsPayment ? undefined : "Choose none to simulate money arriving with no matching request."}>
                    <select className={inputCls} value={target} onChange={(e) => setTarget(e.target.value)}>
                      <option value="">{needsPayment ? "Choose a payment" : "None (unmatched payment)"}</option>
                      {needsPayment
                        ? demoPayments.map((p) => <option key={p.id} value={p.id}>{p.customer_name ?? "Unmatched"} · {inr(p.amount_paise)} · {p.state.replaceAll("_", " ")}</option>)
                        : approved.map((r) => <option key={r.id} value={r.id}>{r.customer_name} · {r.invoice_number} · {inr(r.amount_paise)}</option>)}
                    </select>
                  </Field>
                  {!needsPayment && (
                    <Field label="Amount paid (₹)" hint={target ? "Leave empty to pay the requested amount. Enter a different amount to test a mismatch." : "Required when there is no request."}>
                      <input className={`${inputCls} tabular`} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
                    </Field>
                  )}
                  <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={twice} onChange={(e) => setTwice(e.target.checked)} /> Deliver the same webhook twice</label>
                  <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={tamper} onChange={(e) => setTamper(e.target.checked)} /> Send with a forged signature</label>
                  {act.error && <ErrorBox message={act.error} />}
                  <Button busy={act.busy === "sim"} disabled={needsPayment ? !target : !target && !parseRupees(amount)} onClick={simulate}>Send signed webhook</Button>
                  {result && (
                    <ul className="space-y-1 text-sm" aria-live="polite">
                      {result.deliveries.map((d, i) => (
                        <li key={i} className="flex flex-wrap items-center gap-1.5">
                          <span className="text-muted">Delivery {i + 1}:</span> <Badge status={d.status} /> <span className="text-xs text-muted">HTTP {d.http_status} · {d.detail}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </Card>
            )}
          </div>
        </div>

        <Card title="Provider webhook log">
          {events.data?.length === 0 && <Empty>No provider events received.</Empty>}
          {!!events.data?.length && (
            <Table head={["Received", "Event", "Signature", "Outcome", "Detail"]}>
              {events.data.map((e) => (
                <tr key={e.id}>
                  <td className="whitespace-nowrap py-2 pr-3 text-muted">{fmtDateTime(e.received_at)}</td>
                  <td className="py-2 pr-3">{e.event_type ?? "—"}<span className="block text-xs text-muted">{e.provider}</span></td>
                  <td className="py-2 pr-3">{e.signature_valid ? <Badge label="Valid" tone="green" /> : <Badge label="Invalid" tone="red" />}</td>
                  <td className="py-2 pr-3"><Badge status={e.status} />{e.duplicate_deliveries > 0 && <span className="ml-1 text-xs text-muted">+{e.duplicate_deliveries} repeat{e.duplicate_deliveries === 1 ? "" : "s"} ignored</span>}</td>
                  <td className="py-2 pr-3 text-xs text-muted">{e.detail}</td>
                </tr>
              ))}
            </Table>
          )}
          <p className="mt-2 text-xs text-muted">Events with an invalid signature are rejected before they are linked to any merchant, so they do not appear here.</p>
        </Card>
        <Notice tone="blue">A bank SMS, a screenshot or a customer saying “paid” is recorded as an unverified claim. It never counts as received until an owner confirms it after their own check.</Notice>
      </div>
    </>
  );
}

function MismatchRow({ m, onChange, owner }: { m: Mismatch; onChange: () => void; owner: boolean }) {
  const [note, setNote] = useState("");
  const [open, setOpen] = useState(false);
  const act = useAction();
  return (
    <li className="py-2.5 text-sm">
      <p><Badge label={m.kind.replaceAll("_", " ")} tone="amber" /> <span className="ml-1">{m.detail}</span></p>
      {owner && !open && <button className="mt-1 text-xs font-medium text-brand underline" onClick={() => setOpen(true)}>Mark resolved</button>}
      {open && (
        <div className="mt-2 flex flex-wrap gap-2">
          <input aria-label="Resolution note" className={`${inputCls} max-w-md`} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What did you do about it?" />
          <Button variant="secondary" busy={!!act.busy} disabled={note.trim().length < 3} onClick={() => act.run("r", async () => (await post(`/v1/mismatches/${m.id}/resolve`, { note }), onChange()))}>Resolve</Button>
          {act.error && <ErrorBox message={act.error} />}
        </div>
      )}
    </li>
  );
}
