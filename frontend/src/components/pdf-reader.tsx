"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { ProgressSession, type SyncState } from "@/readers/progress";
import type { PdfLocation } from "@/readers/types";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

export function PdfReader({ bookId }: { bookId: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const progress = useRef<ProgressSession | null>(null);
  const latest = useRef<PdfLocation>({ version: 1, format: "pdf", page: 1, offset: 0 });
  const restoreOffset = useRef(0);
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [title, setTitle] = useState("Opening PDF");
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [size, setSize] = useState(0);
  const [rendered, setRendered] = useState(false);
  const [sync, setSync] = useState<SyncState>({ message: "Loading saved position…", conflict: false });
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const ready = useRef(false);
  const enabled = useRef(false);
  const [restoreRevision, setRestoreRevision] = useState(0);

  useEffect(() => {
    let active = true;
    let owned: PDFDocumentProxy | null = null;
    let task: ReturnType<typeof import("pdfjs-dist").getDocument> | null = null;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90000);
    ready.current = false;
    enabled.current = false;
    setDocument(null); setError(""); setRendered(false);
    const session = new ProgressSession(bookId, (state) => { if (active) setSync(state); }, async (location) => {
      if (location.format !== "pdf") throw new Error("Incompatible position");
      enabled.current = false;
      latest.current = location;
      restoreOffset.current = location.offset;
      setPage(location.page);
      setRestoreRevision((value) => value + 1);
    });
    progress.current = session;
    async function open() {
      const info = await api<{ title: string; format: string }>(`/books/${encodeURIComponent(bookId)}`, { signal: controller.signal });
      if (info.format !== "pdf") throw new Error("This reader opens PDF books only.");
      const saved = await session.start("pdf");
      const response = await fetch(`/api/v1/books/${encodeURIComponent(bookId)}/pdf/content`, { signal: controller.signal, credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error("The PDF could not be downloaded. Return to the library and sign in again if needed.");
      const data = await response.arrayBuffer();
      const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
      if (!active) return;
      const assets = `/pdfjs/${pdfjs.version}/`;
      pdfjs.GlobalWorkerOptions.workerSrc = assets + "pdf.worker.min.mjs";
      // PDF.js 6 removed eval support. Canvas only: no scripting manager,
      // annotation actions, external links, forms, or embedded attachments.
      task = pdfjs.getDocument({ data, enableXfa: false, maxImageSize: 20_000_000, cMapUrl: assets + "cmaps/", cMapPacked: true, standardFontDataUrl: assets + "standard_fonts/", wasmUrl: assets + "wasm/" });
      owned = await task.promise;
      if (!active) { await task.destroy(); return; }
      const location: PdfLocation = saved?.format === "pdf" ? saved : { version: 1, format: "pdf", page: 1, offset: 0 };
      if (location.page > owned.numPages) throw new Error("Saved PDF page is outside this document.");
      latest.current = location; restoreOffset.current = location.offset;
      setTitle(info.title); setPage(location.page); setDocument(owned);
    }
    void open().catch((reason) => { if (active) setError(reason instanceof ApiError && reason.status === 401 ? "Sign in from the library to open this book." : reason instanceof Error ? reason.message : "The PDF could not be opened."); }).finally(() => clearTimeout(timer));
    return () => {
      active = false; controller.abort(); clearTimeout(timer); session.destroy();
      progress.current = null;
      void task?.destroy();
    };
  }, [bookId, attempt]);

  useEffect(() => {
    if (!viewport.current) return;
    const observer = new ResizeObserver(([entry]) => { restoreOffset.current = latest.current.offset; setSize(Math.floor(entry.contentRect.width)); });
    observer.observe(viewport.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!document || !canvas.current || !viewport.current || !size) return;
    let active = true;
    let rendering: RenderTask | undefined;
    const host = viewport.current;
    const target = canvas.current;
    enabled.current = false;
    setRendered(false);
    async function render() {
      const pdfPage = await document!.getPage(page);
      if (!active) return;
      const base = pdfPage.getViewport({ scale: 1 });
      // ResizeObserver's content width already excludes the viewport padding.
      const scale = Math.max(.1, size / base.width) * zoom;
      const view = pdfPage.getViewport({ scale });
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(6_000_000 / (view.width * view.height)));
      target.width = Math.max(1, Math.floor(view.width * pixelRatio));
      target.height = Math.max(1, Math.floor(view.height * pixelRatio));
      target.style.width = `${view.width}px`; target.style.height = `${view.height}px`;
      rendering = pdfPage.render({ canvas: target, viewport: view, transform: [pixelRatio, 0, 0, pixelRatio, 0, 0] });
      await rendering.promise;
      if (!active) return;
      host.scrollTop = restoreOffset.current * target.offsetHeight;
      latest.current = { version: 1, format: "pdf", page, offset: restoreOffset.current };
      restoreOffset.current = 0;
      setRendered(true);
      if (!ready.current) { ready.current = true; progress.current?.enable(); }
      enabled.current = true;
    }
    void render().catch((reason) => { if (active && reason?.name !== "RenderingCancelledException") setError(`PDF page ${page} could not be rendered. Try reopening the book.`); });
    return () => { active = false; rendering?.cancel(); };
  }, [document, page, zoom, size, restoreRevision]);

  function navigate(next: number) {
    if (!document || !rendered) return;
    const destination = Math.max(1, Math.min(document.numPages, next));
    if (destination === page) return;
    latest.current = { version: 1, format: "pdf", page: destination, offset: 0 };
    restoreOffset.current = 0;
    progress.current?.record(latest.current, (destination - 1) / document.numPages);
    setPage(destination);
  }

  return <main className="reader-page">
    <header className="reader-toolbar"><Link href="/" className="reader-back">← Library</Link><div className="reader-heading"><h1>{title}</h1></div><label>Zoom <select value={zoom} onChange={(event) => { restoreOffset.current = latest.current.offset; setZoom(Number(event.target.value)); }}><option value={1}>Fit width</option><option value={1.25}>125%</option><option value={1.5}>150%</option></select></label></header>
    <div className="reader-messages"><p className="reader-save-note" role="status">{sync.message}</p>{sync.conflict && <div className="reader-conflict"><button onClick={() => void progress.current?.resolve(true)}>Load saved position</button><button onClick={() => void progress.current?.resolve(false, latest.current, document ? (page - 1 + latest.current.offset) / document.numPages : 0)}>Keep this position</button></div>}{error && <div className="reader-error" role="alert">{error}<button onClick={() => setAttempt((value) => value + 1)}>Reopen book</button></div>}</div>
    <div className="pdf-viewport" ref={viewport} aria-busy={!rendered} onScroll={() => {
      if (!enabled.current || !rendered || !viewport.current || !canvas.current || !document) return;
      const offset = Math.max(0, Math.min(1, viewport.current.scrollTop / canvas.current.offsetHeight));
      latest.current = { version: 1, format: "pdf", page, offset };
      progress.current?.record(latest.current, (page - 1 + offset) / document.numPages);
    }}><canvas ref={canvas} role="img" aria-label={`PDF page ${page}`} />{!rendered && !error && <p role="status">Rendering PDF page…</p>}</div>
    <footer className="reader-footer"><button disabled={!rendered || page <= 1} onClick={() => navigate(page - 1)}>Previous</button><p role="status">Page {page} / {document?.numPages ?? "…"} · {document ? Math.round((page - 1 + latest.current.offset) / document.numPages * 100) : 0}%</p><button disabled={!rendered || !document || page >= document.numPages} onClick={() => navigate(page + 1)}>Next</button></footer>
  </main>;
}
