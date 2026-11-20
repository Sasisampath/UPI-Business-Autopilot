"use client";
import Link from "next/link";
import { useMe } from "@/components/shell";
import { Avatar, Badge, Button } from "@/components/ui";
import { setToken } from "@/lib/api";

const ITEMS = [
  { href: "/customers", label: "Customers", hint: "Who owes what, and what they said", icon: "M16 19v-1a4 4 0 00-8 0v1M12 11a3 3 0 100-6 3 3 0 000 6zM3 21h18" },
  { href: "/invoices", label: "Invoices", hint: "Every bill and its balance", icon: "M6 3h12v18l-3-2-3 2-3-2-3 2V3zm3.5 5h5M9.5 12h5" },
  { href: "/assistant", label: "Ask the assistant", hint: "Type or speak a question", icon: "M12 4a4 4 0 014 4v3a4 4 0 01-8 0V8a4 4 0 014-4zm-7 7a7 7 0 0014 0M12 18v3" },
  { href: "/settings", label: "Settings and connections", hint: "What is live, test or demo", icon: "M12 9a3 3 0 100 6 3 3 0 000-6zM4 12h2m12 0h2M12 4v2m0 12v2M6.3 6.3l1.4 1.4m8.6 8.6l1.4 1.4m0-11.4l-1.4 1.4m-8.6 8.6l-1.4 1.4" },
];

export default function MorePage() {
  const me = useMe();
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 rounded-2xl border border-line bg-white p-4">
        <Avatar name={me.name} size="h-12 w-12 text-base" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-base font-bold">{me.name}</p>
          <p className="truncate text-sm text-muted">{me.merchant_name}</p>
        </div>
        <Badge label={me.role} tone="gray" />
      </div>
      <ul className="overflow-hidden rounded-2xl border border-line bg-white">
        {ITEMS.map((i) => (
          <li key={i.href} className="border-b border-line last:border-0">
            <Link href={i.href} className="flex items-center gap-3 px-4 py-3.5 active:bg-brand-soft">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={i.icon} /></svg>
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-semibold">{i.label}</span>
                <span className="block truncate text-xs text-muted">{i.hint}</span>
              </span>
              <svg viewBox="0 0 24 24" className="h-4 w-4 text-muted" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M9 5l7 7-7 7" /></svg>
            </Link>
          </li>
        ))}
      </ul>
      <Button variant="secondary" className="w-full" onClick={() => setToken(null)}>Switch user</Button>
    </div>
  );
}
