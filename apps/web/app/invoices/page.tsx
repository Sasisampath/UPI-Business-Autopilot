"use client";
import Link from "next/link";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, Table } from "@/components/ui";
import { fmtDate, inr, useApi } from "@/lib/api";
import type { Invoice } from "@/lib/types";

export default function InvoicesPage() {
  const { data, error, loading, reload } = useApi<Invoice[]>("/v1/invoices");
  return (
    <>
      <PageHeader title="Invoices" subtitle="Balances are calculated from confirmed receipts only." action={<Link href="/bills" className="rounded-lg bg-brand px-3 py-2 text-sm font-medium text-white">Add a bill</Link>} />
      <Card>
        {error && <ErrorBox message={error} onRetry={reload} />}
        {loading && !data && <Loading />}
        {data?.length === 0 && <Empty>No invoices yet. Approve a bill to create the first one.</Empty>}
        {!!data?.length && (
          <Table head={["Invoice", "Customer", "Date", "₹Total", "₹Due", "Status"]}>
            {data.map((i) => (
              <tr key={i.id} className="hover:bg-slate-50">
                <td className="py-2.5 pr-3"><Link href={`/invoices/${i.id}`} className="font-medium text-brand hover:underline">{i.number}</Link></td>
                <td className="py-2.5 pr-3">{i.customer_name}</td>
                <td className="py-2.5 pr-3 text-muted">{fmtDate(i.invoice_date)}</td>
                <td className="tabular py-2.5 pr-3 text-right">{inr(i.total_paise)}</td>
                <td className="tabular py-2.5 pr-3 text-right font-semibold">{inr(i.due_paise)}</td>
                <td className="py-2.5"><Badge status={i.status} /></td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}
