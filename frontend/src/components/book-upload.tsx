"use client";

import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { LibraryBook } from "./book-grid";

type Props = {
  csrf: string;
  maxBytes: number;
  onUploaded: () => Promise<void>;
  onBusyChange: (busy: boolean) => void;
};

type Result = { book: LibraryBook; duplicate: boolean; warnings: string[] };

export function BookUpload({ csrf, maxBytes, onUploaded, onBusyChange }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    const file = input.current?.files?.[0];
    if (!file) { setError("Choose an EPUB or PDF file first."); return; }
    if (!file.size || file.size > maxBytes) {
      setError(`Choose a nonempty file up to ${(maxBytes / (1024 * 1024)).toFixed(1)} MiB.`);
      return;
    }
    setBusy(true);
    onBusyChange(true);
    const form = new FormData();
    form.append("file", file);
    try {
      // The browser supplies the multipart boundary. Processing can outlast
      // ordinary API requests, so uploads have a separate three-minute timeout.
      const result = await api<Result>("/books", {
        method: "POST", headers: { "X-CSRF-Token": csrf }, body: form,
      }, 180000);
      setNotice(`${result.duplicate ? "Already in your library" : "Added"}: ${result.book.title}. ${result.warnings.join(" ")}`);
      if (input.current) input.current.value = "";
      try { await onUploaded(); }
      catch { setError("The upload was saved, but the library could not refresh. Use Refresh library."); }
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "The upload could not be confirmed. Refresh your library before retrying.");
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }

  return <form className="upload-form" onSubmit={upload} aria-busy={busy}>
    <label htmlFor="book-file">Add a book</label>
    <p id="upload-help">DRM-free EPUB or PDF · up to {(maxBytes / (1024 * 1024)).toFixed(0)} MiB · one file at a time</p>
    <div className="upload-controls">
      <input ref={input} id="book-file" type="file" accept=".epub,.pdf,application/epub+zip,application/pdf" aria-describedby="upload-help" disabled={busy} required />
      <button type="submit" disabled={busy}>{busy ? "Processing…" : "Upload book"}</button>
    </div>
    {busy && <p role="status">Uploading and checking your book. Large files may take a little longer.</p>}
    {notice && <p role="status" className="connected">{notice}</p>}
    {error && <p role="alert" className="unavailable">{error}</p>}
  </form>;
}
