"use client";

import { createContext, createElement, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";

export type ReaderPreferences = {
  font_family: "georgia" | "palatino" | "sans";
  font_size: number;
  line_height: number;
  margin: number;
  theme: "light" | "sepia" | "dark";
  pdf_zoom: "fit-page" | "fit-width" | "50" | "75" | "100" | "125" | "150" | "175" | "200" | "250" | "300";
};
export const DEFAULT_PREFERENCES: ReaderPreferences = { font_family: "georgia", font_size: 19, line_height: 1.65, margin: 32, theme: "light", pdf_zoom: "fit-page" };
export const PALETTES = { light: { background: "#faf8f2", foreground: "#282b26", link: "#315d43" }, sepia: { background: "#f2e4cb", foreground: "#493823", link: "#694218" }, dark: { background: "#1e2421", foreground: "#e5e7de", link: "#a4d6b1" } };
export const FONTS = { georgia: "Georgia, 'Times New Roman', serif", palatino: "Palatino, 'Palatino Linotype', 'Book Antiqua', serif", sans: "Arial, Helvetica, sans-serif" };

function usePreferencesState() {
  const [value, setValue] = useState(DEFAULT_PREFERENCES);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState("Loading preferences…");
  const [attempt, setAttempt] = useState(0);
  const pending = useRef<Partial<ReaderPreferences>>({});
  const guest = useRef(false);
  const flush = useRef<(keepalive?: boolean) => Promise<void>>(async () => {});
  const schedule = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    let active = true;
    guest.current = false;
    let busy = false;
    let loading = false;
    let generation = 0;
    let csrf = "";
    let controller: AbortController | null = null;
    async function load() {
      if (loading) return;
      loading = true;
      const startedAt = generation;
      const request = new AbortController();
      controller = request;
      const timeout = setTimeout(() => request.abort(), 10000);
      try {
        const identity = await api<{ csrf_token: string }>("/auth/me", { signal: request.signal });
        const saved = await api<ReaderPreferences>("/preferences", { signal: request.signal });
        if (active) {
          guest.current = false;
          csrf = identity.csrf_token;
          if (startedAt === generation) { setValue({ ...saved, ...pending.current }); setStatus(Object.keys(pending.current).length ? "Unsaved preferences" : "Preferences saved"); }
          setReady(true);
        }
      } catch (error) {
        if (active && error instanceof ApiError && error.status === 401) {
          guest.current = true;
          pending.current = {};
          let theme: ReaderPreferences["theme"] = "light";
          try { const cached = localStorage.getItem("ebook-theme"); if (cached === "light" || cached === "sepia" || cached === "dark") theme = cached; } catch { /* Storage is optional. */ }
          setValue({ ...DEFAULT_PREFERENCES, theme }); setReady(true); setStatus("Theme saved on this device. Sign in to sync.");
        } else if (active) setStatus("Preferences unavailable. Retry to change settings.");
      } finally { loading = false; clearTimeout(timeout); }
    }
    async function save(keepalive = false) {
      if (busy || !csrf || !Object.keys(pending.current).length) return;
      busy = true;
      generation += 1;
      const sending = { ...pending.current };
      if (active) setStatus("Saving preferences…");
      try {
        const saved = await api<ReaderPreferences>("/preferences", { method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(sending), keepalive });
        for (const key of Object.keys(sending) as (keyof ReaderPreferences)[]) if (pending.current[key] === sending[key]) delete pending.current[key];
        if (active) { setValue({ ...saved, ...pending.current }); setStatus(Object.keys(pending.current).length ? "Unsaved preferences" : "Preferences saved"); }
      } catch {
        if (active) setStatus("Preferences not saved. Keep this tab open; retrying.");
      } finally {
        busy = false;
        if (active && Object.keys(pending.current).length) schedule.current = setTimeout(() => { void save(); }, 3000);
      }
    }
    flush.current = save;
    void load();
    const focus = () => { if (Object.keys(pending.current).length) void save(); else if (!busy) void load(); };
    const hidden = () => { if (document.visibilityState === "hidden") void save(true); };
    const authChanged = () => { pending.current = {}; setReady(false); setAttempt((value) => value + 1); };
    window.addEventListener("ebook-auth-changed", authChanged);
    window.addEventListener("focus", focus);
    window.addEventListener("online", focus);
    document.addEventListener("visibilitychange", hidden);
    return () => {
      void save(true); active = false; controller?.abort(); clearTimeout(schedule.current);
      window.removeEventListener("ebook-auth-changed", authChanged);
      window.removeEventListener("focus", focus); window.removeEventListener("online", focus); document.removeEventListener("visibilitychange", hidden);
    };
  }, [attempt]);

  const update = useCallback((patch: Partial<ReaderPreferences>) => {
    if (guest.current) {
      if (patch.theme) {
        const theme = patch.theme;
        setValue((current) => ({ ...current, theme }));
        try { localStorage.setItem("ebook-theme", theme); setStatus("Theme saved on this device. Sign in to sync."); }
        catch { setStatus("Theme applies to this tab; browser storage is unavailable."); }
      }
      return;
    }
    pending.current = { ...pending.current, ...patch };
    setValue((current) => ({ ...current, ...patch }));
    setStatus("Unsaved preferences");
    clearTimeout(schedule.current);
    schedule.current = setTimeout(() => { void flush.current(); }, 500);
  }, []);
  return { value, ready, status, update, retry: () => setAttempt((value) => value + 1) };
}


const PreferencesContext = createContext<ReturnType<typeof usePreferencesState> | null>(null);

export function ReaderPreferencesProvider({ children }: { children: ReactNode }) {
  const preferences = usePreferencesState();
  useEffect(() => {
    if (!preferences.ready) return;
    document.documentElement.dataset.theme = preferences.value.theme;
    try { localStorage.setItem("ebook-theme", preferences.value.theme); } catch { /* Theme still applies without storage. */ }
  }, [preferences.ready, preferences.value.theme]);
  return createElement(PreferencesContext.Provider, { value: preferences }, children);
}

export function useReaderPreferences() {
  const preferences = useContext(PreferencesContext);
  if (!preferences) throw new Error("ReaderPreferencesProvider is required");
  return preferences;
}
