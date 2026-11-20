"use client";
import { useCallback, useEffect, useState } from "react";

const TOKEN_KEY = "upi-autopilot-token";

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session lasts until reload */
  }
  window.dispatchEvent(new Event("auth-changed"));
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public issues: Issue[] = []) {
    super(message);
  }
}

export interface Issue {
  code: string;
  field: string;
  severity: "blocking" | "warning";
  message: string;
}

function describe(detail: unknown, status: number): { message: string; issues: Issue[] } {
  if (typeof detail === "string") return { message: detail, issues: [] };
  if (Array.isArray(detail)) {
    return { message: detail.map((d) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; "), issues: [] };
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; issues?: Issue[] };
    return { message: d.message ?? "Request failed", issues: d.issues ?? [] };
  }
  return { message: status >= 500 ? "The server could not be reached or failed. Is the API running?" : `Request failed (${status})`, issues: [] };
}

export async function api<T = any>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { ...init, headers, body });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check that the API is running.");
  }
  if (res.status === 401 && token) setToken(null);
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const { message, issues } = describe(data?.detail, res.status);
    throw new ApiError(res.status, message, issues);
  }
  return (res.headers.get("content-type") ?? "").includes("json") ? res.json() : (res.blob() as Promise<T>);
}

export const post = <T = any>(path: string, json: unknown = {}) => api<T>(path, { method: "POST", json });

/** GET with loading/error state and a reload handle. */
export function useApi<T = any>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (path === null) return;
    let live = true;
    setLoading(true);
    api<T>(path)
      .then((d) => live && (setData(d), setError(null)))
      .catch((e: Error) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [path, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

/** Indian-format rupees from integer paise, using integer arithmetic only. */
export function inr(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return "—";
  const sign = paise < 0 ? "−" : "";
  const abs = Math.abs(paise);
  const rupees = Math.floor(abs / 100);
  const rem = abs % 100;
  const s = String(rupees);
  const tail = s.slice(-3);
  const head = s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${sign}₹${head ? `${head},` : ""}${tail}${rem ? `.${String(rem).padStart(2, "0")}` : ""}`;
}

/** "1,200.50" -> 120050. Returns null for anything that is not a plain rupee amount. */
export function parseRupees(text: string): number | null {
  const t = text.replace(/[₹,\s]/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  const [r, f = ""] = t.split(".");
  return Number(r) * 100 + Number((f + "00").slice(0, 2));
}

export function rupeesText(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return "";
  const rem = paise % 100;
  return `${Math.floor(paise / 100)}${rem ? `.${String(rem).padStart(2, "0")}` : ""}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00+05:30` : iso);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata", weekday: iso.length === 10 ? "short" : undefined });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" });
}
