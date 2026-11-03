"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { ProgressSession, type SyncState } from "@/readers/progress";
import type { PdfLocation } from "@/readers/types";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { useReaderPreferences } from "@/readers/preferences";
import { ReaderSettings } from "./reader-settings";

export function PdfReader({ bookId }: { bookId: string }) {
  const preferences = useReaderPreferences();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const progress = useRef<ProgressSession | null>(null);
  const latest = useRef<PdfLocation>({ version: 1, format: "pdf", page: 1, offset: 0 });
  const restoreOffset = useRef(0);
  const programmaticTop = useRef<number | null>(null);
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [title, setTitle] = useState("Opening PDF");
  const [page, setPage] = useState(1);
  const zoom = preferences.value.pdf_zoom;
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [rendered, setRendered] = useState(false);
  const [sync, setSync] = useState<SyncState>({ message: "Loading saved position…", conflict: false });
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const ready = useRef(false);
  const enabled = useRef(false);
  const [restoreRevision, setRestoreRevision] = useState(0);
  const navigationPending = useRef(false);
  const gesture = useRef<{ x: number; y: number; time: number } | null>(null);

  useEffect(() => {
    if (!preferences.ready) return;
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
  }, [bookId, attempt, preferences.ready]);

  useEffect(() => {
    if (!viewport.current) return;
    const observer = new ResizeObserver(([entry]) => {
      restoreOffset.current = latest.current.offset;
      const width = Math.floor(entry.contentRect.width), height = Math.floor(entry.contentRect.height);
      setSize((current) => current.width === width && current.height === height ? current : { width, height });
    });
    observer.observe(viewport.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!document || !canvas.current || !viewport.current || !size.width || !size.height) return;
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
      // Both dimensions exclude padding. Fit-page keeps the entire page
      // visible on a wide monitor; percentages use PDF's natural page size.
      const scale = zoom === "fit-page" ? Math.min(size.width / base.width, size.height / base.height) * .995 : zoom === "fit-width" ? size.width / base.width : Number(zoom) / 100;
      const view = pdfPage.getViewport({ scale });
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(6_000_000 / (view.width * view.height)));
      target.width = Math.max(1, Math.floor(view.width * pixelRatio));
      target.height = Math.max(1, Math.floor(view.height * pixelRatio));
      target.style.width = `${view.width}px`; target.style.height = `${view.height}px`;
      rendering = pdfPage.render({ canvas: target, viewport: view, transform: [pixelRatio, 0, 0, pixelRatio, 0, 0] });
      await rendering.promise;
      if (!active) return;
      host.scrollTop = restoreOffset.current * target.offsetHeight;
      programmaticTop.current = host.scrollTop;
      latest.current = { version: 1, format: "pdf", page, offset: restoreOffset.current };
      restoreOffset.current = 0;
      setRendered(true);
      navigationPending.current = false;
      if (!ready.current) { ready.current = true; progress.current?.enable(); }
      // Scroll events from restoring/clamping a zoomed page are presentation
      // changes, not evidence the reader moved to a different passage.
      enabled.current = true;
    }
    void render().catch((reason) => { if (active && reason?.name !== "RenderingCancelledException") setError(`PDF page ${page} could not be rendered. Try reopening the book.`); });
    return () => { active = false; rendering?.cancel(); };
  }, [document, page, zoom, size, restoreRevision]);

  function navigate(next: number) {
    if (!document || !rendered || navigationPending.current) return;
    const destination = Math.max(1, Math.min(document.numPages, next));
    if (destination === page) return;
    navigationPending.current = true;
    latest.current = { version: 1, format: "pdf", page: destination, offset: 0 };
    restoreOffset.current = 0;
    progress.current?.record(latest.current, (destination - 1) / document.numPages);
    setPage(destination);
  }

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setSettingsOpen(false); return; }
      if (settingsOpen || sync.conflict || !rendered || event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input,textarea,select,a,[contenteditable]:not([contenteditable=false]),.reader-settings,.reader-conflict")) return;
      if (["ArrowRight", "PageDown", "ArrowLeft", "PageUp"].includes(event.key)) {
        event.preventDefault();
        navigate(page + (["ArrowRight", "PageDown"].includes(event.key) ? 1 : -1));
      }
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [page, document, rendered, settingsOpen, sync.conflict]);

  const swipeEnabled = rendered && !settingsOpen && !sync.conflict && Boolean(canvas.current && canvas.current.offsetWidth <= size.width + 2);

  return <main className="reader-page" data-theme={preferences.value.theme}>
    <header className="reader-toolbar pdf-toolbar"><Link href="/" className="reader-back">← Library</Link><div className="reader-heading"><h1>{title}</h1></div><label>Zoom <select disabled={!preferences.ready || !rendered} value={zoom} onChange={(event) => { restoreOffset.current = latest.current.offset; preferences.update({ pdf_zoom: event.target.value as typeof zoom }); }}><option value="fit-page">Fit page</option><option value="fit-width">Fit width</option>{[50, 75, 100, 125, 150, 175, 200, 250, 300].map((percent) => <option key={percent} value={String(percent)}>{percent}%</option>)}</select></label><button className="secondary" disabled={!preferences.ready} aria-expanded={settingsOpen} onClick={() => setSettingsOpen((value) => !value)}>Settings</button></header>
    <div className="reader-messages"><p className="reader-save-note" role="status">{sync.message}</p>{sync.conflict && <div className="reader-conflict"><button onClick={() => void progress.current?.resolve(true)}>Load saved position</button><button onClick={() => void progress.current?.resolve(false, latest.current, document ? (page - 1 + latest.current.offset) / document.numPages : 0)}>Keep this position</button></div>}{error && <div className="reader-error" role="alert">{error}<button onClick={() => setAttempt((value) => value + 1)}>Reopen book</button></div>}</div>
    {!preferences.ready && <p>{preferences.status} <button onClick={preferences.retry}>Retry preferences</button></p>}
    <div className="pdf-reading-area">
    {settingsOpen && <ReaderSettings value={preferences.value} update={preferences.update} status={preferences.status} onClose={() => setSettingsOpen(false)} />}
    <div className="pdf-viewport" ref={viewport} tabIndex={0} aria-label="PDF reading area" aria-busy={!rendered}
      style={{ touchAction: swipeEnabled ? "pan-y pinch-zoom" : "auto" }}
      onTouchStart={(event) => {
        gesture.current = null;
        if (!swipeEnabled || event.touches.length !== 1 || (window.visualViewport?.scale ?? 1) > 1.05) return;
        const touch = event.touches[0], bounds = event.currentTarget.getBoundingClientRect();
        if (touch.clientX - bounds.left < 24 || bounds.right - touch.clientX < 24) return;
        gesture.current = { x: touch.clientX, y: touch.clientY, time: Date.now() };
      }}
      onTouchMove={(event) => {
        if (!gesture.current) return;
        if (event.touches.length !== 1) { gesture.current = null; return; }
        const dx = Math.abs(event.touches[0].clientX - gesture.current.x), dy = Math.abs(event.touches[0].clientY - gesture.current.y);
        if (dy > 30 && dy > dx) gesture.current = null;
      }}
      onTouchCancel={() => { gesture.current = null; }}
      onTouchEnd={(event) => {
        const start = gesture.current; gesture.current = null;
        if (!start || !swipeEnabled || event.touches.length || event.changedTouches.length !== 1) return;
        const dx = event.changedTouches[0].clientX - start.x, dy = event.changedTouches[0].clientY - start.y;
        if (Date.now() - start.time <= 700 && Math.abs(dx) >= 64 && Math.abs(dx) > Math.abs(dy) * 1.7) navigate(page + (dx < 0 ? 1 : -1));
      }}
      onScroll={() => {
      if (!enabled.current || !rendered || !viewport.current || !canvas.current || !document) return;
      if (programmaticTop.current !== null && Math.abs(viewport.current.scrollTop - programmaticTop.current) < 1) return;
      programmaticTop.current = null;
      const offset = Math.max(0, Math.min(1, viewport.current.scrollTop / canvas.current.offsetHeight));
      latest.current = { version: 1, format: "pdf", page, offset };
      progress.current?.record(latest.current, (page - 1 + offset) / document.numPages);
    }}><canvas ref={canvas} role="img" aria-label={`PDF page ${page}`} />{!rendered && !error && <p className="pdf-loading" role="status">Rendering PDF page…</p>}</div>
    </div>
    <footer className="reader-footer"><button disabled={!rendered || page <= 1} onClick={() => navigate(page - 1)}>Previous</button><p role="status">Page {page} / {document?.numPages ?? "…"} · {document ? Math.round((page - 1 + latest.current.offset) / document.numPages * 100) : 0}%</p><button disabled={!rendered || !document || page >= document.numPages} onClick={() => navigate(page + 1)}>Next</button></footer>
  </main>;
}
