"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DEMO_OWNER, GuideState, resetDemo, useGuide, writeGuide } from "@/lib/demo";
import { useMe } from "./shell";
import { Button, TextAction } from "./ui";

interface Step {
  title: string;
  text: string;
  href: (g: GuideState) => string;
  /** The real action the step waits for; absent = an explain-only step with a Next button. */
  waitFor?: string;
  doing?: string;
  fill?: boolean;
}

const INV = "/invoices/inv_demo_0001";

const STEPS: Step[] = [
  { title: "Lakshmi's day at a glance", text: "She sells to nearby shops on credit. Green is money that has really come in. Amber is only promised.", href: () => "/" },
  { title: "A handwritten bill arrives", text: "Tap “Try a sample WhatsApp bill”.", href: () => "/bills", waitFor: "draft-created", doing: "Waiting for the sample bill" },
  { title: "Check what the AI read", text: "Two lines are wrong on purpose. Fix them yourself or tap “Fill corrections”. Then scroll down, tick the box and approve.", href: (g) => (g.draftId ? `/bills/${g.draftId}` : "/bills"), waitFor: "invoice-approved", doing: "Waiting for your approval", fill: true },
  { title: "Now it is an invoice", text: "Nothing was posted until you approved. The full amount is due.", href: (g) => (g.invoiceId ? `/invoices/${g.invoiceId}` : "/invoices") },
  { title: "Part payments, tracked exactly", text: "Murugan Stores: ₹20,000 bill, paid ₹5,000 and ₹10,000. ₹5,000 is still due.", href: () => INV },
  { title: "A customer promises to pay", text: "Tap “Receive”, tick the box and save. Watch: the amount to collect does not change.", href: () => "/conversations?customer=cus_anbu&say=Will%20pay%20%E2%82%B92%2C500%20by%20UPI%20tomorrow", waitFor: "promise-saved", doing: "Waiting for the promise to be saved" },
  { title: "Real payment comes in", text: "Under “Send UPI request”: type 5000, Prepare request, Approve, then “Customer pays”. A signed payment closes the bill, once.", href: () => INV, waitFor: "payment-verified", doing: "Waiting for the verified payment" },
  { title: "Home is up to date", text: "Still-to-collect is down and received is up. Promises stay separate from money.", href: () => "/" },
];

const pathOf = (href: string) => href.split("?")[0];

/** Optional walkthrough for judges. It only points at the real screens and waits for the real,
 *  validated actions; it never performs a financial action itself. */
export function GuideBar() {
  const me = useMe();
  const guide = useGuide();
  const pathname = usePathname();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onEvent = (e: Event) => {
      const d = (e as CustomEvent).detail as { name: string; draftId?: string; invoiceId?: string };
      const g = { ...guide };
      const step = STEPS[g.step];
      if (!g.active || !step || step.waitFor !== d.name) return;
      writeGuide({ step: g.step + 1, collapsed: false, ...(d.draftId ? { draftId: d.draftId } : {}), ...(d.invoiceId ? { invoiceId: d.invoiceId } : {}) });
    };
    window.addEventListener("demo-event", onEvent);
    return () => window.removeEventListener("demo-event", onEvent);
  }, [guide]);

  if (!guide.active || !me.demo_mode) return null;
  const last = guide.step >= STEPS.length - 1;
  const step = STEPS[Math.min(guide.step, STEPS.length - 1)];
  const href = step.href(guide);
  const here = pathname === pathOf(href);
  const label = `Demo guide, step ${guide.step + 1} of ${STEPS.length}`;
  const restart = () => {
    setBusy(true);
    resetDemo(me.role === "owner" ? me.user_id : DEMO_OWNER, true).catch(() => setBusy(false));
  };

  if (guide.collapsed)
    return (
      <button onClick={() => writeGuide({ collapsed: false })} aria-label={`${label}. Show`} className="flex min-h-11 w-full items-center justify-between gap-2 border-t border-amber-300 bg-amber-50 px-4 text-left text-[13px] font-semibold text-amber-950">
        <span className="truncate">Guide {guide.step + 1}/{STEPS.length} · {step.title}</span>
        <span aria-hidden>Show</span>
      </button>
    );

  return (
    <section aria-label={label} className="guide-in border-t border-amber-300 bg-amber-50 px-4 pb-2 pt-2.5 text-amber-950 shadow-[0_-6px_16px_-10px_rgb(27_36_32/0.35)]">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-amber-800">Step {guide.step + 1} of {STEPS.length}</span>
          <span className="flex items-center gap-0.5" aria-hidden>
            {STEPS.map((_, i) => (
              <span key={i} className={`h-1.5 rounded-full ${i < guide.step ? "w-2 bg-brand" : i === guide.step ? "w-4 bg-amber-600" : "w-2 bg-amber-200"}`} />
            ))}
          </span>
        </div>
        <div className="-mr-2 -mt-1 flex">
          <TextAction tone="muted" className="!min-h-9" onClick={() => writeGuide({ collapsed: true })}>Hide</TextAction>
          <TextAction tone="muted" className="!min-h-9" onClick={() => writeGuide({ active: false })}>End</TextAction>
        </div>
      </div>
      <h2 className="text-[15px] font-bold leading-snug">{step.title}</h2>
      <p className="mt-0.5 text-[13px] leading-snug">{step.text}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-1 gap-y-1">
        {!here ? (
          <Button className="!min-h-10" onClick={() => router.push(href)}>Take me there</Button>
        ) : last ? (
          <>
            <Button className="!min-h-10" onClick={() => writeGuide({ active: false })}>Finish</Button>
            <Button variant="secondary" className="!min-h-10" busy={busy} onClick={restart}>Reset and run again</Button>
          </>
        ) : step.waitFor ? (
          <>
            {step.fill && <Button variant="secondary" className="!min-h-10" onClick={() => window.dispatchEvent(new Event("demo-fill-review"))}>Fill corrections</Button>}
            <span className="flex items-center gap-1.5 px-1 text-[13px] font-semibold text-amber-800" aria-live="polite">
              <span className="h-2 w-2 animate-pulse rounded-full bg-amber-600" aria-hidden />
              {step.doing}
            </span>
          </>
        ) : (
          <Button className="!min-h-10" onClick={() => writeGuide({ step: guide.step + 1 })}>Next</Button>
        )}
        <span className="ml-auto flex">
          {guide.step > 0 && <TextAction tone="muted" className="!min-h-10" onClick={() => writeGuide({ step: guide.step - 1 })}>Back</TextAction>}
          {!last && (step.waitFor || !here) && <TextAction tone="muted" className="!min-h-10" onClick={() => writeGuide({ step: guide.step + 1 })}>Skip</TextAction>}
        </span>
      </div>
    </section>
  );
}
