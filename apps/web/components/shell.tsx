"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, post, setToken } from "@/lib/api";
import { Badge, Button, ErrorBox, Loading } from "./ui";

export interface Me {
  user_id: string;
  name: string;
  role: "owner" | "staff" | "viewer";
  merchant_name: string;
  demo_mode: boolean;
  today: string;
}

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext) as Me;

const NAV = [
  { href: "/", label: "Today", icon: "M3 12l9-8 9 8M5 10v10h14V10" },
  { href: "/bills", label: "Bills", icon: "M7 3h10l3 3v15H4V3h3zm1 7h8M8 14h8M8 18h5" },
  { href: "/invoices", label: "Invoices", icon: "M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2V3zm4 5h6M9 12h6" },
  { href: "/customers", label: "Customers", icon: "M16 19v-1a4 4 0 00-8 0v1M12 11a3 3 0 100-6 3 3 0 000 6zM3 21h18" },
  { href: "/conversations", label: "Promises", icon: "M4 5h16v11H9l-5 4V5z" },
  { href: "/payments", label: "Payments", icon: "M3 7h18v10H3V7zm0 4h18M7 15h3" },
  { href: "/settings", label: "Settings", icon: "M12 9a3 3 0 100 6 3 3 0 000-6zM4 12h2m12 0h2M12 4v2m0 12v2M6.3 6.3l1.4 1.4m8.6 8.6l1.4 1.4m0-11.4l-1.4 1.4m-8.6 8.6l-1.4 1.4" },
];

function Login({ onDone }: { onDone: () => void }) {
  const [users, setUsers] = useState<{ user_id: string; name: string; role: string; merchant_name: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    setError(null);
    api("/v1/auth/demo-users").then(setUsers).catch((e) => setError(e.message));
  };
  useEffect(load, []);
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">UPI Business Autopilot</h1>
      <p className="mt-1 text-sm text-muted">Bills, part payments, promises and verified cash-in, in one place.</p>
      <div className="mt-6 rounded-xl border border-line bg-white p-4">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-sm font-semibold">Choose a demo user</h2>
          <Badge label="Demo mode" tone="violet" />
        </div>
        {error && <ErrorBox message={error} onRetry={load} />}
        {!users && !error && <Loading label="Loading users" />}
        {users?.length === 0 && (
          <p className="text-sm text-muted">
            No demo data yet. Run <code className="rounded bg-slate-100 px-1">python -m app.seed</code> in <code className="rounded bg-slate-100 px-1">services/api</code>, then reload.
          </p>
        )}
        <ul className="space-y-2">
          {users?.map((u) => (
            <li key={u.user_id}>
              <button
                className="flex w-full items-center justify-between gap-3 rounded-lg border border-line px-3 py-2.5 text-left hover:border-brand hover:bg-brand-soft"
                onClick={() =>
                  post("/v1/auth/demo-login", { user_id: u.user_id })
                    .then((r) => (setToken(r.token), onDone()))
                    .catch((e) => setError(e.message))
                }
              >
                <span>
                  <span className="block text-sm font-medium">{u.name}</span>
                  <span className="block text-xs text-muted">{u.merchant_name}</span>
                </span>
                <Badge label={u.role} tone="gray" />
              </button>
            </li>
          ))}
        </ul>
      </div>
      <p className="mt-3 text-xs text-muted">Passwordless sign-in exists only in demo mode. All payments in this demo are simulated; no real money moves.</p>
    </main>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [state, setState] = useState<"checking" | "anon" | "ready">("checking");
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  function check() {
    if (!getToken()) return setState("anon");
    api<Me>("/v1/me")
      .then((m) => (setMe(m), setError(null), setState("ready")))
      .catch((e) => (getToken() ? setError(e.message) : setState("anon")));
  }
  useEffect(() => {
    check();
    window.addEventListener("auth-changed", check);
    return () => window.removeEventListener("auth-changed", check);
  }, []);

  if (state === "anon") return <Login onDone={check} />;
  if (state === "checking" || !me)
    return <div className="mx-auto max-w-md px-4 py-10">{error ? <ErrorBox message={error} onRetry={check} /> : <Loading />}</div>;

  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  return (
    <MeContext.Provider value={me}>
      {me.demo_mode && (
        <div className="bg-violet-700 px-4 py-1.5 text-center text-xs font-medium text-white">
          Demo mode — payments and customer messages are simulated. No real money moves and nothing is sent to anyone.
        </div>
      )}
      <div className="mx-auto flex max-w-6xl">
        <aside className="sticky top-0 hidden h-screen w-52 shrink-0 flex-col border-r border-line bg-white px-3 py-4 md:flex">
          <p className="px-2 text-sm font-semibold text-brand">UPI Business Autopilot</p>
          <p className="truncate px-2 text-xs text-muted">{me.merchant_name}</p>
          <nav className="mt-4 space-y-0.5">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} aria-current={active(n.href) ? "page" : undefined} className={`flex items-center gap-2.5 rounded-lg px-2 py-2 text-sm ${active(n.href) ? "bg-brand-soft font-semibold text-brand" : "text-ink hover:bg-slate-50"}`}>
                <Icon d={n.icon} />
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="mt-auto px-2 text-xs text-muted">
            <p className="truncate font-medium text-ink">{me.name}</p>
            <button className="mt-1 underline" onClick={() => setToken(null)}>
              Switch user
            </button>
          </div>
        </aside>
        <div className="min-w-0 flex-1">
          <header className="flex items-center justify-between border-b border-line bg-white px-4 py-2.5 md:hidden">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-brand">UPI Business Autopilot</p>
              <p className="truncate text-xs text-muted">{me.merchant_name}</p>
            </div>
            <Button variant="ghost" onClick={() => setToken(null)}>
              Switch user
            </Button>
          </header>
          <main className="px-4 pb-24 pt-5 md:px-6 md:pb-10">{children}</main>
        </div>
      </div>
      <nav className="fixed inset-x-0 bottom-0 z-10 flex border-t border-line bg-white md:hidden" aria-label="Main">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} aria-current={active(n.href) ? "page" : undefined} className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 px-0.5 py-2 text-[10px] ${active(n.href) ? "font-semibold text-brand" : "text-muted"}`}>
            <Icon d={n.icon} />
            <span className="max-w-full truncate">{n.label}</span>
          </Link>
        ))}
      </nav>
    </MeContext.Provider>
  );
}

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}
