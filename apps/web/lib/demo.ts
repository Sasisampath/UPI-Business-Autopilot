"use client";
import { useEffect, useState } from "react";
import { post, setToken } from "./api";

/** Things the guided demo waits for. They are emitted only after the real API call succeeded. */
export type DemoEvent = "draft-created" | "invoice-approved" | "promise-saved" | "payment-verified";

export function emitDemo(name: DemoEvent, detail: Record<string, string> = {}) {
  window.dispatchEvent(new CustomEvent("demo-event", { detail: { name, ...detail } }));
}

export interface GuideState {
  active: boolean;
  step: number;
  collapsed: boolean;
  draftId?: string;
  invoiceId?: string;
}

const KEY = "upi-autopilot-guide";
const OFF: GuideState = { active: false, step: 0, collapsed: false };

export function readGuide(): GuideState {
  try {
    return { ...OFF, ...JSON.parse(window.localStorage.getItem(KEY) ?? "{}") };
  } catch {
    return OFF;
  }
}

export function writeGuide(patch: Partial<GuideState>) {
  const next = { ...readGuide(), ...patch };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable: the guide simply will not survive a reload */
  }
  window.dispatchEvent(new Event("guide-changed"));
}

export function useGuide(): GuideState {
  const [state, setState] = useState<GuideState>(OFF);
  useEffect(() => {
    const sync = () => setState(readGuide());
    sync();
    window.addEventListener("guide-changed", sync);
    return () => window.removeEventListener("guide-changed", sync);
  }, []);
  return state;
}

export const DEMO_OWNER = "usr_owner_a";

/** Restore the seeded sample data (owner only), sign back in and reload on Home.
 *  Same starting numbers every time, so the walkthrough is repeatable. */
export async function resetDemo(userId: string, startGuide: boolean) {
  await post("/v1/demo/reset");
  const login = await post<{ token: string }>("/v1/auth/demo-login", { user_id: userId });
  writeGuide(startGuide ? { active: true, step: 0, collapsed: false, draftId: undefined, invoiceId: undefined } : { ...OFF });
  setToken(login.token);
  window.location.assign("/");
}
