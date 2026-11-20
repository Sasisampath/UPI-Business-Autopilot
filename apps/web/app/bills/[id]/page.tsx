"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useMe } from "@/components/shell";
import { Badge, Button, Card, ErrorBox, Field, Loading, Notice, PageHeader, inputCls, useAction } from "@/components/ui";
import { ApiError, Issue, api, inr, parseRupees, post, rupeesText, useApi } from "@/lib/api";

interface Item {
  description: string | null;
  quantity: string | null;
  unit_price_paise: number | null;
  line_total_paise: number | null;
}

interface Payload {
  customer_name: string | null;
  invoice_date: string | null;
  currency: string;
  items: Item[];
  subtotal_paise: number | null;
  tax_paise: number | null;
  total_paise: number | null;
  uncertain_fields: string[];
  source_language: string | null;
}

interface Draft {
  id: string;
  status: string;
  extraction_source: string;
  extraction_error: string | null;
  payload: Payload;
  customer_id: string | null;
  invoice_id: string | null;
  computed: { line_totals_paise: number[]; subtotal_paise: number; tax_paise: number; total_paise: number } | null;
  computed_lines: (number | null)[];
  issues: Issue[];
  upload: { id: string; filename: string; content_type: string; source: string; has_file: boolean };
}

/** Money input that keeps the raw text while typing and reports integer paise (or null). */
function Rupees({ value, onChange, flagged, label }: { value: number | null; onChange: (v: number | null) => void; flagged?: boolean; label: string }) {
  const [text, setText] = useState(rupeesText(value));
  useEffect(() => {
    if (parseRupees(text) !== value) setText(rupeesText(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <input
      aria-label={label}
      inputMode="decimal"
      className={`${inputCls} tabular text-right ${flagged ? "border-amber-500 bg-amber-50" : ""}`}
      value={text}
      placeholder="—"
      onChange={(e) => {
        setText(e.target.value);
        onChange(e.target.value.trim() === "" ? null : parseRupees(e.target.value));
      }}
    />
  );
}

export default function ReviewBillPage() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const router = useRouter();
  const { data: draft, error, loading, reload } = useApi<Draft>(`/v1/invoice-drafts/${id}`);
  const customers = useApi<{ id: string; name: string }[]>("/v1/customers");
  const [form, setForm] = useState<Payload | null>(null);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [computed, setComputed] = useState<Draft["computed"]>(null);
  const [lineCalc, setLineCalc] = useState<(number | null)[]>([]);
  const [dirty, setDirty] = useState(false);
  const [ack, setAck] = useState(false);
  const [image, setImage] = useState<string | null>(null);
  const act = useAction();

  function adopt(d: Draft) {
    setForm(d.payload);
    setCustomerId(d.customer_id);
    setIssues(d.issues);
    setComputed(d.computed);
    setLineCalc(d.computed_lines);
    setDirty(false);
  }
  useEffect(() => {
    if (draft) adopt(draft);
  }, [draft]);
  useEffect(() => {
    if (!draft?.upload.has_file) return;
    let url: string | null = null;
    api<Blob>(`/v1/uploads/${draft.upload.id}/file`).then((b) => setImage((url = URL.createObjectURL(b)))).catch(() => {});
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [draft?.upload.id, draft?.upload.has_file]);

  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (loading || !draft || !form) return <Loading label="Loading draft" />;

  const editable = draft.status === "needs_review" && me.role !== "viewer";
  const flagged = (field: string) => issues.some((i) => i.field === field || i.field.startsWith(`${field}.`)) || form.uncertain_fields.includes(field);
  const fieldError = (field: string) => issues.find((i) => i.field === field && i.severity === "blocking")?.message;
  const blocking = issues.filter((i) => i.severity === "blocking");
  const warnings = issues.filter((i) => i.severity === "warning");

  function update(patch: Partial<Payload>, touched: string) {
    setForm((f) => f && { ...f, ...patch, uncertain_fields: f.uncertain_fields.filter((u) => u !== touched && !u.startsWith(`${touched}.`)) });
    setDirty(true);
  }
  function updateItem(i: number, patch: Partial<Item>) {
    const items = form!.items.map((it, j) => (j === i ? { ...it, ...patch } : it));
    update({ items }, `items[${i}]`);
  }
  async function save() {
    const d = await api<Draft>(`/v1/invoice-drafts/${id}`, { method: "PATCH", json: { payload: form, customer_id: customerId } });
    adopt(d);
    return d;
  }
  async function approve() {
    try {
      if (dirty) await save();
      const res = await post(`/v1/invoice-drafts/${id}/approve`, { acknowledge_warnings: ack });
      router.push(`/invoices/${res.invoice.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) reload();
      throw e;
    }
  }

  return (
    <>
      <PageHeader title="Review bill" back={{ href: "/bills", label: "Bills" }} subtitle={draft.upload.filename} action={<Badge status={draft.status} />} />
      <div className="space-y-4">
        {draft.extraction_source === "simulated" && (
          <Notice>
            <strong>Simulated extraction.</strong> No Gemini key is configured, so this is a fixed sample draft. It was not read from your file. Set <code>GEMINI_API_KEY</code> to read real bills.
          </Notice>
        )}
        {draft.extraction_error && <Notice tone="amber">{draft.extraction_error}</Notice>}
        {draft.status === "approved" && draft.invoice_id && (
          <Notice tone="blue">
            Approved. <Link className="font-medium underline" href={`/invoices/${draft.invoice_id}`}>Open the invoice</Link>
          </Notice>
        )}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <Card title="Original bill">
            {draft.upload.content_type === "application/pdf" && image ? (
              <a href={image} target="_blank" rel="noreferrer" className="text-sm text-brand underline">Open the PDF in a new tab</a>
            ) : image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={image} alt="Uploaded bill" className="max-h-[70vh] w-full rounded-lg border border-line object-contain" />
            ) : (
              <p className="text-sm text-muted">{draft.upload.has_file ? "Loading image…" : "The file is not available yet."}</p>
            )}
          </Card>

          <div className="space-y-4">
            <Card title="Draft details">
              <fieldset disabled={!editable} className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Buyer as written on the bill" error={fieldError("customer_name")}>
                    <input className={`${inputCls} ${flagged("customer_name") && !customerId ? "border-amber-500 bg-amber-50" : ""}`} value={form.customer_name ?? ""} onChange={(e) => update({ customer_name: e.target.value || null }, "customer_name")} />
                  </Field>
                  <Field label="Link to customer" hint={customerId ? undefined : "Not linked: approving creates a new customer."}>
                    <select className={inputCls} value={customerId ?? ""} onChange={(e) => (setCustomerId(e.target.value || null), setDirty(true))}>
                      <option value="">New customer</option>
                      {customers.data?.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Invoice date" error={fieldError("invoice_date")}>
                    <input type="date" className={`${inputCls} ${flagged("invoice_date") ? "border-amber-500 bg-amber-50" : ""}`} value={form.invoice_date ?? ""} onChange={(e) => update({ invoice_date: e.target.value || null }, "invoice_date")} />
                  </Field>
                </div>

                <div>
                  <p className="mb-1 text-sm font-medium">Items</p>
                  <div className="space-y-2">
                    {form.items.map((it, i) => {
                      const calc = dirty ? undefined : (lineCalc[i] ?? undefined);
                      const conflict = issues.find((x) => x.field.startsWith(`items[${i}]`) && x.severity === "blocking");
                      return (
                        <div key={i} className={`rounded-lg border p-2 ${conflict ? "border-amber-500 bg-amber-50/60" : "border-line"}`}>
                          <div className="grid grid-cols-6 gap-2">
                            <input aria-label={`Item ${i + 1} description`} className={`${inputCls} col-span-6 sm:col-span-3`} placeholder="Description" value={it.description ?? ""} onChange={(e) => updateItem(i, { description: e.target.value || null })} />
                            <input aria-label={`Item ${i + 1} quantity`} inputMode="decimal" className={`${inputCls} tabular col-span-2 text-right sm:col-span-1 ${it.quantity ? "" : "border-amber-500 bg-amber-50"}`} placeholder="Qty" value={it.quantity ?? ""} onChange={(e) => updateItem(i, { quantity: e.target.value.trim() || null })} />
                            <div className="col-span-2 sm:col-span-1">
                              <Rupees label={`Item ${i + 1} unit price`} value={it.unit_price_paise} flagged={it.unit_price_paise === null} onChange={(v) => updateItem(i, { unit_price_paise: v })} />
                            </div>
                            <div className="col-span-2 sm:col-span-1">
                              <Rupees label={`Item ${i + 1} line total on bill`} value={it.line_total_paise} flagged={!!conflict} onChange={(v) => updateItem(i, { line_total_paise: v })} />
                            </div>
                          </div>
                          <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs">
                            <span className={conflict ? "font-medium text-amber-900" : "text-muted"}>{conflict ? conflict.message : dirty ? "Save to recalculate" : calc !== undefined ? `Qty × price = ${inr(calc)}` : ""}</span>
                            {editable && (
                              <span className="flex gap-3">
                                {conflict?.code === "line_total_conflict" && calc !== undefined && (
                                  <button type="button" className="font-medium text-brand underline" onClick={() => updateItem(i, { line_total_paise: calc })}>Use {inr(calc)}</button>
                                )}
                                <button type="button" className="text-rose-700 underline" onClick={() => update({ items: form.items.filter((_, j) => j !== i) }, "items")}>Remove</button>
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <p className="mt-1 text-xs text-muted">Columns: description · quantity · unit price (₹) · line total as written (₹)</p>
                  {editable && (
                    <Button type="button" variant="ghost" className="mt-1" onClick={() => update({ items: [...form.items, { description: null, quantity: null, unit_price_paise: null, line_total_paise: null }] }, "items")}>
                      + Add item
                    </Button>
                  )}
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <Field label="Subtotal on bill (₹)" error={fieldError("subtotal_paise")} hint="Leave empty if not written">
                    <Rupees label="Subtotal" value={form.subtotal_paise} flagged={flagged("subtotal_paise")} onChange={(v) => update({ subtotal_paise: v }, "subtotal_paise")} />
                  </Field>
                  <Field label="Tax (₹)" hint="Never inferred. Leave empty for none.">
                    <Rupees label="Tax" value={form.tax_paise} flagged={flagged("tax_paise")} onChange={(v) => update({ tax_paise: v }, "tax_paise")} />
                  </Field>
                  <Field label="Total on bill (₹)" error={fieldError("total_paise")}>
                    <Rupees label="Total" value={form.total_paise} flagged={flagged("total_paise")} onChange={(v) => update({ total_paise: v }, "total_paise")} />
                  </Field>
                </div>
              </fieldset>
              <div className="mt-3 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <span className="text-muted">System-calculated total</span>
                <span className="tabular font-semibold">{dirty ? "Save to recalculate" : computed ? inr(computed.total_paise) : "Incomplete lines"}</span>
              </div>
            </Card>

            {draft.status === "needs_review" && (
              <Card title="Before you approve">
                {issues.length === 0 && !dirty && <p className="text-sm text-emerald-800">Everything adds up.</p>}
                <ul className="space-y-1.5 text-sm">
                  {blocking.map((i, k) => (
                    <li key={`b${k}`} className="flex items-start gap-2"><Badge label="Fix" tone="red" /><span>{i.message}</span></li>
                  ))}
                  {warnings.map((i, k) => (
                    <li key={`w${k}`} className="flex items-start gap-2"><Badge label="Check" tone="amber" /><span>{i.message}</span></li>
                  ))}
                </ul>
                {editable && (
                  <>
                    {warnings.length > 0 && blocking.length === 0 && (
                      <label className="mt-3 flex items-start gap-2 text-sm">
                        <input type="checkbox" className="mt-0.5" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                        I have checked the points above against the paper bill.
                      </label>
                    )}
                    {act.error && <div className="mt-3"><ErrorBox message={act.error} /></div>}
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button variant="secondary" disabled={!dirty} busy={act.busy === "save"} onClick={() => act.run("save", save)}>Save changes</Button>
                      <Button disabled={(!dirty && blocking.length > 0) || (warnings.length > 0 && !ack && !dirty)} busy={act.busy === "approve"} onClick={() => act.run("approve", approve)}>
                        {dirty ? "Save and approve" : "Approve and create invoice"}
                      </Button>
                      <Button variant="danger" busy={act.busy === "reject"} onClick={() => act.run("reject", async () => (await post(`/v1/invoice-drafts/${id}/reject`), router.push("/bills")))}>Discard draft</Button>
                    </div>
                  </>
                )}
              </Card>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
