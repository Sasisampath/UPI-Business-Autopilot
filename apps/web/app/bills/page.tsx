"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef } from "react";
import { useMe } from "@/components/shell";
import { Badge, Button, Card, Empty, ErrorBox, Loading, Notice, PageHeader, SimTag, useAction } from "@/components/ui";
import { api, fmtDateTime, inr, post, useApi } from "@/lib/api";

interface Draft {
  id: string;
  status: string;
  extraction_source: string;
  payload: { customer_name: string | null; total_paise: number | null };
  issues: { severity: string }[];
  upload: { filename: string; source: string };
  created_at: string;
  invoice_id: string | null;
}

export default function BillsPage() {
  const me = useMe();
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const { data, error, loading, reload } = useApi<Draft[]>("/v1/invoice-drafts");
  const act = useAction();
  const canWrite = me.role !== "viewer";

  async function ingest(file: File, source: "web" | "whatsapp_demo") {
    const form = new FormData();
    form.append("file", file);
    form.append("source", source);
    const up = await api("/v1/uploads", { method: "POST", body: form });
    const draft = await post("/v1/invoice-drafts/extract", { upload_id: up.id });
    router.push(`/bills/${draft.id}`);
  }

  async function sample() {
    const blob = await (await fetch("/fixtures/sample-handwritten-bill.png")).blob();
    await ingest(new File([blob], "whatsapp-bill-photo.png", { type: "image/png" }), "whatsapp_demo");
  }

  return (
    <>
      <PageHeader title="Bills" subtitle="Photograph a paper bill. You review and approve before any invoice exists." />
      <div className="space-y-4">
        <Card title="Add a bill">
          {!canWrite ? (
            <Empty>View-only users cannot add bills.</Empty>
          ) : (
            <>
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,application/pdf"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) act.run("upload", () => ingest(f, "web"));
                  e.target.value = "";
                }}
              />
              <div className="flex flex-wrap gap-2">
                <Button busy={act.busy === "upload"} onClick={() => fileRef.current?.click()}>
                  Upload photo or PDF
                </Button>
                <Button variant="secondary" busy={act.busy === "sample"} onClick={() => act.run("sample", sample)}>
                  Try a sample WhatsApp bill photo
                </Button>
              </div>
              <p className="mt-2 text-xs text-muted">JPEG, PNG, WebP or PDF, up to 10 MB. The sample arrives as a simulated WhatsApp media message.</p>
              {act.busy && <Loading label="Reading the bill" />}
              {act.error && (
                <div className="mt-3">
                  <ErrorBox message={act.error} />
                </div>
              )}
            </>
          )}
        </Card>

        <Card title="Drafts and reviewed bills">
          {error && <ErrorBox message={error} onRetry={reload} />}
          {loading && !data && <Loading />}
          {data?.length === 0 && <Empty>No bills yet. Upload one to see the review step.</Empty>}
          <ul className="divide-y divide-line">
            {data?.map((d) => {
              const blocking = d.issues.filter((i) => i.severity === "blocking").length;
              return (
                <li key={d.id}>
                  <Link href={d.status === "approved" && d.invoice_id ? `/invoices/${d.invoice_id}` : `/bills/${d.id}`} className="flex items-center justify-between gap-3 py-2.5 text-sm hover:bg-slate-50">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{d.payload.customer_name ?? "Buyer not read"}</p>
                      <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                        {fmtDateTime(d.created_at)} · {d.upload.source === "web" ? "Upload" : "WhatsApp"} <SimTag show={d.extraction_source === "simulated" || d.upload.source === "whatsapp_demo"} />
                        {blocking > 0 && <span className="font-medium text-rose-700">{blocking} to fix</span>}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="tabular">{inr(d.payload.total_paise)}</span>
                      <Badge status={d.status} />
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Card>
        <Notice tone="blue">Extraction only ever produces a draft. Totals are recalculated by the system, and missing or conflicting numbers must be fixed by you.</Notice>
      </div>
    </>
  );
}
