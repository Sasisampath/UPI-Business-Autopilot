"use client";
import { useEffect, useState } from "react";
import { useMe } from "@/components/shell";
import { Badge, Button, Card, Empty, ErrorBox, Field, Loading, Notice, PageHeader, SimTag, inputCls, useAction } from "@/components/ui";
import { api, fmtDate, fmtDateTime, inr, parseRupees, post, rupeesText, useApi } from "@/lib/api";
import type { Customer, Invoice, PromiseRow } from "@/lib/types";

interface Message {
  id: string;
  direction: "inbound" | "outbound";
  channel: string;
  message_type: string;
  body: string;
  status: string;
  block_reason: string | null;
  simulated: boolean;
  created_at: string;
}

interface Proposal {
  amount: string;
  promised_date: string;
  method: string;
  pickup_window: string;
}

const TYPES: Record<string, string> = {
  invoice_share: "Share an invoice",
  payment_request_share: "Share a payment request",
  promise_confirmation: "Confirm what they promised",
  overdue_reminder: "Overdue reminder",
};

export default function ConversationsPage() {
  const me = useMe();
  const canWrite = me.role !== "viewer";
  const customers = useApi<Customer[]>("/v1/customers");
  const invoices = useApi<Invoice[]>("/v1/invoices");
  const promises = useApi<PromiseRow[]>("/v1/promises");
  const [customerId, setCustomerId] = useState<string | null>(null);
  const messages = useApi<Message[]>(customerId ? `/v1/customers/${customerId}/messages` : null);
  const [reply, setReply] = useState("₹3,000 on Friday, ₹2,000 on Monday");
  const [evidence, setEvidence] = useState<{ text: string; messageId: string | null; source: string } | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [invoiceId, setInvoiceId] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [outType, setOutType] = useState("invoice_share");
  const [outBody, setOutBody] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const act = useAction();

  useEffect(() => {
    if (customerId || !customers.data?.length) return;
    const wanted = new URLSearchParams(window.location.search).get("customer");
    setCustomerId(customers.data.find((c) => c.id === wanted)?.id ?? customers.data[0].id);
  }, [customers.data, customerId]);
  useEffect(() => {
    setEvidence(null);
    setProposals([]);
    setInvoiceId("");
    setNote(null);
  }, [customerId]);

  const customer = customers.data?.find((c) => c.id === customerId);
  const openInvoices = invoices.data?.filter((i) => i.customer_id === customerId && i.due_paise > 0) ?? [];
  const mine = promises.data?.filter((p) => p.customer_id === customerId) ?? [];

  function startProposals(raw: { amount_paise: number; promised_date: string; method: string | null }[], text: string, messageId: string | null, source: string) {
    setEvidence({ text, messageId, source });
    setConfirmed(false);
    setProposals(raw.length ? raw.map((p) => ({ amount: rupeesText(p.amount_paise), promised_date: p.promised_date, method: p.method ?? customer?.preferred_method ?? "upi", pickup_window: "" })) : [{ amount: "", promised_date: me.today, method: "upi", pickup_window: "" }]);
    setNote(raw.length ? null : "No amount with a day was found in those words. Enter the commitment only if the customer stated it.");
  }
  const simulateReply = () =>
    act.run("reply", async () => {
      const r = await post("/v1/demo/inbox/inbound", { customer_id: customerId, body: reply });
      messages.reload();
      startProposals(r.proposals, r.message.body, r.message.id, "demo_inbox");
    });
  const readMessage = (m: Message) =>
    act.run(`read-${m.id}`, async () => {
      const r = await post("/v1/promises/parse", { text: m.body });
      startProposals(r.proposals, m.body, m.id, m.channel);
    });
  const savePromises = () =>
    act.run("save", async () => {
      await post("/v1/promises", {
        customer_id: customerId,
        invoice_id: invoiceId || null,
        evidence_source: evidence!.source,
        evidence_text: evidence!.text,
        source_message_id: evidence!.messageId,
        customer_confirmed: confirmed,
        items: proposals.map((p) => ({ amount_paise: parseRupees(p.amount), promised_date: p.promised_date, method: p.method, pickup_window: p.method === "cash" && p.pickup_window.trim() ? p.pickup_window.trim() : null })),
      });
      setEvidence(null);
      setProposals([]);
      promises.reload();
      customers.reload();
    });
  const sendOutbound = () =>
    act.run("out", async () => {
      const d = await post("/v1/messages/drafts", { customer_id: customerId, channel: "demo_inbox", message_type: outType, body: outBody });
      const r = await post(`/v1/messages/${d.message.id}/approve`);
      setNote(r.policy.allowed ? "Delivered to the demo inbox only (simulated). Nothing was sent to the customer." : `Blocked: ${r.policy.reason}`);
      setOutBody("");
      messages.reload();
    });
  const setStatus = (p: PromiseRow, status: string) => act.run(`st-${p.id}`, async () => (await api(`/v1/promises/${p.id}`, { method: "PATCH", json: { status } }), promises.reload(), customers.reload()));
  const valid = proposals.length > 0 && proposals.every((p) => (parseRupees(p.amount) ?? 0) > 0 && p.promised_date);

  if (customers.error) return <ErrorBox message={customers.error} onRetry={customers.reload} />;
  if (!customers.data) return <Loading />;
  if (!customers.data.length) return <Empty>Add a customer first.</Empty>;

  return (
    <>
      <PageHeader title="Conversations and promises" subtitle="Record what customers say they will pay. A promise never changes a balance." />
      <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
        {customers.data.map((c) => (
          <button key={c.id} onClick={() => setCustomerId(c.id)} aria-pressed={c.id === customerId} className={`shrink-0 rounded-full border px-3 py-1.5 text-sm ${c.id === customerId ? "border-brand bg-brand text-white" : "border-line bg-white"}`}>
            {c.name}
          </button>
        ))}
      </div>
      {act.error && <div className="mb-3"><ErrorBox message={act.error} /></div>}
      {note && <div className="mb-3"><Notice tone="amber">{note}</Notice></div>}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <Card title="Inbox" action={<Badge label="Simulator" tone="violet" />}>
            {messages.loading && !messages.data && <Loading />}
            {messages.data?.length === 0 && <Empty>No messages with this customer.</Empty>}
            <ul className="space-y-2">
              {messages.data?.map((m) => (
                <li key={m.id} className={`flex ${m.direction === "outbound" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${m.direction === "outbound" ? "bg-brand-soft" : "bg-slate-100"}`}>
                    <p className="whitespace-pre-wrap break-words">{m.body}</p>
                    <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                      {fmtDateTime(m.created_at)} <SimTag show={m.simulated} />
                      {m.direction === "outbound" && <Badge status={m.status} />}
                      {m.direction === "inbound" && canWrite && <button className="font-medium text-brand underline" onClick={() => readMessage(m)}>Record promise from this</button>}
                    </p>
                    {m.block_reason && <p className="mt-1 text-[11px] text-rose-700">{m.block_reason}</p>}
                  </div>
                </li>
              ))}
            </ul>
            {canWrite && me.demo_mode && (
              <form className="mt-3 border-t border-line pt-3" onSubmit={(e) => (e.preventDefault(), simulateReply())}>
                <Field label="Simulate a reply from the customer" hint="Stored as a simulated message. Try Tamil-English too: “naalaiku 1500 cash”.">
                  <div className="flex gap-2">
                    <input className={inputCls} value={reply} onChange={(e) => setReply(e.target.value)} maxLength={2000} />
                    <Button type="submit" variant="secondary" busy={act.busy === "reply"} disabled={!reply.trim()}>Receive</Button>
                  </div>
                </Field>
              </form>
            )}
          </Card>

          {canWrite && (
            <Card title="Send to this customer" action={<Badge label="Approval + opt-in required" tone="gray" />}>
              <div className="space-y-2">
                <select aria-label="Message type" className={inputCls} value={outType} onChange={(e) => setOutType(e.target.value)}>
                  {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <textarea aria-label="Message" className={inputCls} rows={2} value={outBody} onChange={(e) => setOutBody(e.target.value)} placeholder="Message text" maxLength={2000} />
                <Button variant="secondary" busy={act.busy === "out"} disabled={!outBody.trim()} onClick={sendOutbound}>Approve and deliver to demo inbox</Button>
                <p className="text-xs text-muted">
                  Demo inbox consent: {customer?.consents.demo_inbox === "opt_in" ? "opted in" : customer?.consents.demo_inbox === "opt_out" ? "opted out" : "none recorded"}. Real WhatsApp sending is not built; overdue or collection reminders are always refused.
                </p>
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          {evidence && (
            <Card title="Confirm the commitment" action={<Badge label="Not saved yet" tone="amber" />}>
              <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm">“{evidence.text}”</p>
              <div className="mt-3 space-y-2">
                {proposals.map((p, i) => {
                  const set = (patch: Partial<Proposal>) => setProposals((all) => all.map((x, j) => (j === i ? { ...x, ...patch } : x)));
                  return (
                    <div key={i} className="grid grid-cols-2 gap-2 rounded-lg border border-line p-2 sm:grid-cols-4">
                      <input aria-label="Amount in rupees" className={`${inputCls} tabular`} inputMode="decimal" placeholder="₹ amount" value={p.amount} onChange={(e) => set({ amount: e.target.value })} />
                      <input aria-label="Promised date" type="date" className={inputCls} value={p.promised_date} onChange={(e) => set({ promised_date: e.target.value })} />
                      <select aria-label="Method" className={inputCls} value={p.method} onChange={(e) => set({ method: e.target.value })}>
                        <option value="upi">UPI</option>
                        <option value="cash">Cash</option>
                        <option value="other">Other</option>
                      </select>
                      {p.method === "cash" ? <input aria-label="Pickup time the customer confirmed" className={inputCls} placeholder="Pickup time, if stated" value={p.pickup_window} onChange={(e) => set({ pickup_window: e.target.value })} /> : <button className="text-left text-xs text-rose-700 underline" onClick={() => setProposals((all) => all.filter((_, j) => j !== i))}>Remove</button>}
                    </div>
                  );
                })}
                <Button variant="ghost" onClick={() => setProposals((all) => [...all, { amount: "", promised_date: me.today, method: "upi", pickup_window: "" }])}>+ Add another</Button>
                <Field label="Against invoice (optional)">
                  <select className={inputCls} value={invoiceId} onChange={(e) => setInvoiceId(e.target.value)}>
                    <option value="">Not tied to one invoice</option>
                    {openInvoices.map((i) => <option key={i.id} value={i.id}>{i.number} · {inr(i.due_paise)} due</option>)}
                  </select>
                </Field>
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" className="mt-0.5" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                  The customer explicitly stated these amounts and dates.
                </label>
                <div className="flex gap-2">
                  <Button busy={act.busy === "save"} disabled={!valid || !confirmed} onClick={savePromises}>Save {proposals.length} promise{proposals.length === 1 ? "" : "s"}</Button>
                  <Button variant="ghost" onClick={() => (setEvidence(null), setProposals([]))}>Discard</Button>
                </div>
                <p className="text-xs text-muted">Saved as promises only. No receipt is created and the balance does not change.</p>
              </div>
            </Card>
          )}

          <Card title={`Promises from ${customer?.name ?? "customer"}`} action={canWrite && !evidence ? <Button variant="ghost" onClick={() => startProposals([], "Told me in person", null, "in_person")}>Add in-person promise</Button> : undefined}>
            {promises.loading && !promises.data && <Loading />}
            {mine.length === 0 && promises.data && <Empty>No promises recorded for this customer.</Empty>}
            <ul className="divide-y divide-line">
              {mine.map((p) => (
                <li key={p.id} className="py-2.5 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="flex flex-wrap items-center gap-1.5"><Badge status={p.status} /> {fmtDate(p.promised_date)} · {p.method.toUpperCase()}{p.pickup_window && ` · pickup ${p.pickup_window}`} <SimTag show={p.simulated} /></span>
                    <span className="tabular font-semibold">{inr(p.amount_paise)}</span>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted">“{p.evidence_text}”</p>
                  {canWrite && p.status === "open" && (
                    <div className="mt-1 flex gap-3 text-xs">
                      <button className="text-brand underline" onClick={() => setStatus(p, "kept")}>Mark kept</button>
                      <button className="text-brand underline" onClick={() => setStatus(p, "broken")}>Mark not kept</button>
                      <button className="text-muted underline" onClick={() => setStatus(p, "cancelled")}>Cancel</button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            {mine.some((p) => p.status === "kept") && <p className="mt-2 text-xs text-muted">“Kept” is your own note. It does not record a payment; receipts are recorded on the invoice.</p>}
          </Card>
        </div>
      </div>
    </>
  );
}
