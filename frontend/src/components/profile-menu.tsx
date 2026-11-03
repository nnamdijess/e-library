"use client";

import { useEffect, useRef, useState } from "react";
import { useReaderPreferences } from "@/readers/preferences";

export function ProfileMenu({ username, loading, busy, onSignOut }: {
  username: string | null; loading: boolean; busy: boolean; onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const area = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const preferences = useReaderPreferences();
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!area.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { setOpen(false); button.current?.focus(); } };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);

  return <div className="profile-area" ref={area}>
    <button className="profile-circle" ref={button} aria-label="Account" aria-expanded={open} aria-controls="account-panel" onClick={() => setOpen((value) => !value)}>
      {username ? <span aria-hidden="true">{username.slice(0, 1).toUpperCase()}</span> : <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></svg>}
    </button>
    {open && <div className="profile-panel" id="account-panel" role="region" aria-label="Account details">
      <h2>Your account</h2>
      {loading ? <p role="status">Checking sign-in…</p> : username ? <><p>Signed in as <strong>{username}</strong></p><p className="profile-role">Library owner</p></> : <p>Signed out. Sign in below to access your library.</p>}
      <label>Application theme<select aria-label="Application theme" disabled={!preferences.ready} value={preferences.value.theme} onChange={(event) => preferences.update({ theme: event.target.value as "light" | "sepia" | "dark" })}><option value="light">Light</option><option value="sepia">Sepia</option><option value="dark">Dark</option></select></label>
      <p role="status" className="preferences-status">{preferences.status}</p>
      {!preferences.ready && <button className="secondary" onClick={preferences.retry}>Retry preferences</button>}
      {username && <button disabled={busy} onClick={onSignOut}>{busy ? "Please wait…" : "Sign out"}</button>}
    </div>}
  </div>;
}
