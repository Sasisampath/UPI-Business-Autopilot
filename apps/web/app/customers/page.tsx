"use client";
import Link from "next/link";
import { useState } from "react";
import { useMe } from "@/components/shell";
import { Button, Card, Empty, ErrorBox, Field, Loading, PageHeader, Table, inputCls, useAction } from "@/components/ui";
import { inr, post, useApi } from "@/lib/api";
import type { Customer } from "@/lib/types";

export default function CustomersPage() {
  const me = useMe();
  const { data, error, loading, reload } = useApi<Customer[]>("/v1/customers");
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const act = useAction();
  return (
    <>
      <PageHeader title="Customers" subtitle="What each shop owes, and what they have said they will pay." action={me.role !== "viewer" && !adding ? <Button onClick={() => setAdding(true)}>Add customer</Button> : undefined} />
      <div className="space-y-4">
        {adding && (
          <Card title="New customer">
            <form
              className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
              onSubmit={(e) => {
                e.preventDefault();
                act.run("add", async () => (await post("/v1/customers", { name, phone: phone || null }), setAdding(false), setName(""), setPhone(""), reload()));
              }}
            >
              <Field label="Shop name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} required /></Field>
              <Field label="Phone (optional)"><input className={inputCls} value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" /></Field>
              <div className="flex gap-2">
                <Button type="submit" busy={!!act.busy} disabled={!name.trim()}>Save</Button>
                <Button type="button" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
              </div>
              {act.error && <div className="sm:col-span-3"><ErrorBox message={act.error} /></div>}
            </form>
          </Card>
        )}
        <Card>
          {error && <ErrorBox message={error} onRetry={reload} />}
          {loading && !data && <Loading />}
          {data?.length === 0 && <Empty>No customers yet.</Empty>}
          {!!data?.length && (
            <Table head={["Customer", "Prefers", "₹Promised", "₹Owes"]}>
              {data.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="py-2.5 pr-3"><Link href={`/customers/${c.id}`} className="font-medium text-brand hover:underline">{c.name}</Link></td>
                  <td className="py-2.5 pr-3 text-muted">{c.preferred_method ? c.preferred_method.toUpperCase() : "Not stated"}</td>
                  <td className="tabular py-2.5 pr-3 text-right text-sky-700">{inr(c.promised_open_paise)}</td>
                  <td className="tabular py-2.5 pr-3 text-right font-semibold">{inr(c.outstanding_paise)}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>
    </>
  );
}
