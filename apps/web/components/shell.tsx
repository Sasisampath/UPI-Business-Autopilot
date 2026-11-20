"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, post, setToken } from "@/lib/api";
import { Avatar, Badge, ErrorBox, Loading } from "./ui";

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

const TABS = [
  { href: "/", label: "Home", match: ["/"], icon: "M3 11.5l9-7.5 9 7.5M5.5 10v10h13V10M10 20v-5h4v5" },
  { href: "/bills", label: "Bills", match: ["/bills", "/invoices"], icon: "M6 3h12v18l-3-2-3 2-3-2-3 2V3zm3.5 5h5M9.5 12h5" },
  { href: "/conversations", label: "Promises", match: ["/conversations"], icon: "M4 5h16v11H10l-5 4v-4H4V5zm4.5 5.5l2.5 2.5 4.5-5" },
  { href: "/payments", label: "Payments", match: ["/payments"], icon: "M3 7h18v10H3V7zm0 4h18M7 15h3" },
  { href: "/more", label: "More", match: ["/more", "/customers", "/assistant", "/settings"], icon: "M5 12h.01M12 12h.01M19 12h.01" },
];

/** Screens that sit on the chat wallpaper instead of the plain canvas. */
const CHAT_SCREENS = ["/conversations", "/assistant"];

function Login({ onDone }: { onDone: () => void }) {
  const [users, setUsers] = useState<{ user_id: string; name: string; role: string; merchant_name: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    setError(null);
    api("/v1/auth/demo-users").then(setUsers).catch((e) => setError(e.message));
  };
  useEffect(load, []);
  return (
    <div className="scroll-area flex flex-1 flex-col overflow-y-auto">
      <div className="bg-brand px-6 pb-10 pt-14 text-white">
        <p className="text-sm font-semibold text-white/80">Vanakkam</p>
        <h1 className="mt-1 text-[28px] font-bold leading-tight">UPI Business Autopilot</h1>
        <p className="mt-2 text-[15px] leading-snug text-white/85">Know who owes, who promised, and who has really paid.</p>
      </div>
      <div className="-mt-5 flex-1 rounded-t-3xl bg-canvas px-4 pt-5">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-[13px] font-bold uppercase tracking-wide text-muted">Open the demo as</h2>
          <Badge label="Demo" tone="violet" />
        </div>
        {error && <ErrorBox message={error} onRetry={load} />}
        {!users && !error && <Loading label="Loading users" />}
        {users?.length === 0 && (
          <p className="text-sm text-muted">
            No demo data yet. Run <code className="rounded bg-stone-200 px-1">python -m app.seed</code> in <code className="rounded bg-stone-200 px-1">services/api</code>, then reload.
          </p>
        )}
        <ul className="space-y-2">
          {users?.map((u) => (
            <li key={u.user_id}>
              <button
                className="flex w-full items-center gap-3 rounded-2xl border border-line bg-white px-3 py-3 text-left active:bg-brand-soft"
                onClick={() =>
                  post("/v1/auth/demo-login", { user_id: u.user_id })
                    .then((r) => (setToken(r.token), onDone()))
                    .catch((e) => setError(e.message))
                }
              >
                <Avatar name={u.name} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-semibold">{u.name}</span>
                  <span className="block truncate text-xs text-muted">{u.merchant_name}</span>
                </span>
                <Badge label={u.role} tone="gray" />
              </button>
            </li>
          ))}
        </ul>
        <p className="mt-4 pb-6 text-xs leading-snug text-muted">Sign-in without a password exists only in demo mode. All payments here are simulated; no real money moves and nothing is sent to anyone.</p>
      </div>
    </div>
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

  const active = (t: (typeof TABS)[number]) => (t.href === "/" ? pathname === "/" : t.match.some((m) => pathname.startsWith(m)));
  const chat = CHAT_SCREENS.some((p) => pathname.startsWith(p));

  let body: React.ReactNode;
  if (state === "anon") body = <Login onDone={check} />;
  else if (state === "checking" || !me) body = <div className="flex-1 px-4 py-10">{error ? <ErrorBox message={error} onRetry={check} /> : <Loading />}</div>;
  else
    body = (
      <MeContext.Provider value={me}>
        <header className="flex items-center gap-3 bg-brand px-4 pb-2.5 pt-3 text-white">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/15 text-base font-bold" aria-hidden>₹</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[15px] font-bold leading-tight">{me.merchant_name}</p>
            <p className="truncate text-[11px] leading-tight text-white/80">{me.demo_mode ? "Demo · simulated money, nothing is sent" : me.name}</p>
          </div>
          <Link href="/more" aria-label={`Signed in as ${me.name}`} className="rounded-full bg-white/15 px-2.5 py-1 text-[11px] font-semibold capitalize">
            {me.role}
          </Link>
        </header>
        <main key={pathname} className={`scroll-area flex-1 overflow-y-auto ${chat ? "wallpaper" : ""}`}>
          <div className="page-in flex min-h-full flex-col px-4 pb-6 pt-4">{children}</div>
        </main>
        <nav className="flex border-t border-line bg-white pb-[env(safe-area-inset-bottom)]" aria-label="Main">
          {TABS.map((t) => (
            <Link key={t.href} href={t.href} aria-current={active(t) ? "page" : undefined} className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 pb-2 pt-2 text-[11px] ${active(t) ? "font-bold text-brand" : "font-medium text-muted"}`}>
              <span className={`flex h-7 w-14 items-center justify-center rounded-full ${active(t) ? "bg-brand-soft" : ""}`}>
                <svg viewBox="0 0 24 24" className="h-[22px] w-[22px]" fill="none" stroke="currentColor" strokeWidth={active(t) ? 2.1 : 1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d={t.icon} />
                </svg>
              </span>
              {t.label}
            </Link>
          ))}
        </nav>
      </MeContext.Provider>
    );

  return (
    <div className="stage">
      <div className="phone">{body}</div>
    </div>
  );
}
