"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { BookGrid, type Catalog } from "./book-grid";
import { BookUpload } from "./book-upload";

type Identity = { user: { username: string }; csrf_token: string };
type Phase = "loading" | "signed-out" | "signed-in" | "error";

export function LibraryAccess() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [csrf, setCsrf] = useState("");
  const [catalog, setCatalog] = useState<Catalog>({ items: [], total: 0, limit: 20, offset: 0 });
  const [maxUploadBytes, setMaxUploadBytes] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = setTimeout(() => controller.abort(), 10000);
    setPhase("loading");
    setError("");
    setIdentity(null);
    setCatalog({ items: [], total: 0, limit: 20, offset: 0 });

    async function load() {
      const options = { signal: controller.signal };
      let current: Identity;
      try {
        current = await api<Identity>("/auth/me", options);
      } catch (reason) {
        if (!(reason instanceof ApiError) || reason.status !== 401) throw reason;
        const initial = await api<{ csrf_token: string }>("/auth/csrf", {
          ...options, headers: { "X-Ebook-Request": "1" },
        });
        if (active) { setCsrf(initial.csrf_token); setPhase("signed-out"); }
        return;
      }
      const [books, policy] = await Promise.all([
        api<Catalog>("/books", options),
        api<{ max_bytes: number }>("/upload-policy", options),
      ]);
      if (active) {
        setIdentity(current);
        setCsrf(current.csrf_token);
        setCatalog(books);
        setMaxUploadBytes(policy.max_bytes);
        setPhase("signed-in");
      }
    }

    void load().catch((reason) => {
      if (active) {
        setError(reason instanceof ApiError ? reason.message : "Could not connect. Check that the backend is running.");
        setPhase("error");
      }
    }).finally(() => clearTimeout(timeout));
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [attempt]);

  async function signIn(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setBusy(true);
    setError("");
    try {
      await api<Identity>("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ username: fields.get("username"), password: fields.get("password") }),
      });
      form.reset();
      // Retrieve the rotated session's identity and protected catalog together.
      setAttempt((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Could not sign in. Check the connection and try again.");
    } finally {
      const password = form.elements.namedItem("password");
      if (password instanceof HTMLInputElement) password.value = "";
      setBusy(false);
    }
  }

  async function signOut() {
    setBusy(true);
    setError("");
    try {
      await api<void>("/auth/logout", {
        method: "POST", headers: { "X-CSRF-Token": csrf },
      });
      setIdentity(null);
      setCatalog({ items: [], total: 0, limit: 20, offset: 0 });
      setAttempt((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Could not sign out. Check the connection and try again.");
    } finally { setBusy(false); }
  }

  async function refreshCatalog(offset: number) {
    setRefreshing(true);
    setError("");
    try {
      setCatalog(await api<Catalog>(`/books?offset=${offset}`));
    } finally { setRefreshing(false); }
  }

  function navigate(offset: number) {
    void refreshCatalog(offset).catch((reason) => {
      setError(reason instanceof ApiError ? reason.message : "Could not refresh the library. Try again.");
    });
  }

  return (
    <section className="connection" aria-labelledby="library-title">
      <h2 id="library-title">Your library</h2>
      {phase === "loading" && <p role="status">Opening your library…</p>}
      {error && <p role="alert" className="unavailable">{error}</p>}
      {phase === "error" && <button onClick={() => setAttempt((value) => value + 1)}>Try again</button>}
      {phase === "signed-out" && (
        <>
          <p>Sign in with the owner account you created locally.</p>
          <form onSubmit={signIn}>
            <label htmlFor="username">Username</label>
            <input id="username" name="username" autoComplete="username" required maxLength={64} disabled={busy} />
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" autoComplete="current-password" required maxLength={1024} disabled={busy} />
            <button disabled={busy || !csrf} type="submit">{busy ? "Signing in…" : "Sign in"}</button>
          </form>
        </>
      )}
      {phase === "signed-in" && identity && (
        <>
          <div className="account"><p>Signed in as <strong>{identity.user.username}</strong></p><button onClick={signOut} disabled={busy || uploading || refreshing}>{busy ? "Signing out…" : "Sign out"}</button></div>
          <BookUpload csrf={csrf} maxBytes={maxUploadBytes} onUploaded={() => refreshCatalog(0)} onBusyChange={setUploading} />
          <div className="library-tools"><p>{catalog.total} {catalog.total === 1 ? "book" : "books"}</p><button className="secondary" disabled={refreshing || uploading || busy} onClick={() => navigate(catalog.offset)}>{refreshing ? "Refreshing…" : "Refresh library"}</button></div>
          {catalog.total === 0 ? <p className="empty-library">Your library starts here. Add an EPUB or PDF above.</p> : <BookGrid books={catalog.items} />}
          {catalog.total > catalog.limit && <nav className="pagination" aria-label="Library pages">
            <button disabled={refreshing || uploading || catalog.offset === 0} onClick={() => navigate(Math.max(0, catalog.offset - catalog.limit))}>Previous</button>
            <span>{catalog.offset + 1}–{Math.min(catalog.offset + catalog.limit, catalog.total)} of {catalog.total}</span>
            <button disabled={refreshing || uploading || catalog.offset + catalog.limit >= catalog.total} onClick={() => navigate(catalog.offset + catalog.limit)}>Next</button>
          </nav>}
          <p className="footnote">Books are stored in your library. Opening and reading them comes in the next milestones.</p>
        </>
      )}
    </section>
  );
}
