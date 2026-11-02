"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Chapter, EpubLocation, PageState, ReaderController } from "@/readers/types";

type BookInfo = { title: string; format: "epub" | "pdf"; authors: string[] };
type ReadingCopy = { artifact_version: number; content_url: string; warnings: string[] };

export function EpubReader({ bookId }: { bookId: string }) {
  const host = useRef<HTMLDivElement>(null);
  const engine = useRef<ReaderController | null>(null);
  const pending = useRef(false);
  const latestLocation = useRef<EpubLocation | null>(null);
  const [book, setBook] = useState<BookInfo | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [page, setPage] = useState<PageState | null>(null);
  const [ready, setReady] = useState(false);
  const [moving, setMoving] = useState(false);
  const [tocOpen, setTocOpen] = useState(false);
  const [error, setError] = useState("");
  const [notices, setNotices] = useState<string[]>([]);
  const [attempt, setAttempt] = useState(0);

  async function navigate(target: "next" | "previous" | { href: string }) {
    const current = engine.current;
    if (!current || pending.current) return;
    pending.current = true;
    setMoving(true);
    setError("");
    try {
      if (target === "next") await current.next();
      else if (target === "previous") await current.previous();
      else { await current.display(target.href); setTocOpen(false); }
    } catch {
      if (engine.current === current) setError("That reading location could not be opened. Try another chapter or reopen the book.");
    } finally {
      if (engine.current === current) { pending.current = false; setMoving(false); }
    }
  }

  useEffect(() => {
    let active = true;
    let owned: ReaderController | null = null;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90000);
    pending.current = false;
    latestLocation.current = null;
    setReady(false);
    setMoving(false);
    setError("");
    setPage(null);
    setChapters([]);
    setNotices([]);

    async function open() {
      const info = await api<BookInfo>(`/books/${encodeURIComponent(bookId)}`, { signal: controller.signal });
      if (!active) return;
      setBook(info);
      if (info.format !== "epub") throw new Error("PDF reading will be available in the next milestone.");
      const copy = await api<ReadingCopy>(`/books/${encodeURIComponent(bookId)}/epub`, { signal: controller.signal });
      if (copy.artifact_version !== 1 || copy.content_url !== `/api/v1/books/${encodeURIComponent(bookId)}/epub/1/content`) {
        throw new Error("This reading copy requires a newer reader.");
      }
      const response = await fetch(copy.content_url, { credentials: "same-origin", cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("The reading copy could not be downloaded. Return to the library and sign in again if needed.");
      const data = await response.arrayBuffer();
      const { EpubAdapter } = await import("@/readers/epub/adapter");
      if (!active || !host.current) return;
      owned = new EpubAdapter(host.current, copy.artifact_version, {
        onChapters: (items) => { if (active) setChapters(items); },
        onLocation: (location, state) => {
          if (!active) return;
          latestLocation.current = location;
          setPage(state);
        },
        onKeyboard: (direction) => { if (active) void navigate(direction); },
        onLink: (href) => { if (active) void navigate({ href }); },
        onError: () => { if (active) setError("This chapter could not be displayed. Try another chapter."); },
      });
      engine.current = owned;
      await owned.open(data);
      if (active) { setReady(true); setNotices(copy.warnings); }
    }
    void open().catch((reason) => {
      if (active) setError(reason instanceof ApiError && reason.status === 401 ? "Sign in from the library to open this book." : reason instanceof Error && reason.name !== "AbortError" ? reason.message : "Opening the book took too long. Please try again.");
    }).finally(() => clearTimeout(timeout));

    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setTocOpen(false); return; }
      if (!active || pending.current || !engine.current || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.target instanceof HTMLElement && event.target.closest("input,textarea,select,button,a")) return;
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        void navigate(event.key === "ArrowRight" ? "next" : "previous");
      }
    };
    window.addEventListener("keydown", keydown);
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timeout);
      window.removeEventListener("keydown", keydown);
      owned?.destroy();
      if (engine.current === owned) engine.current = null;
    };
  }, [bookId, attempt]);

  const currentChapter = chapters.find((chapter) => chapter.href.split("#")[0] === latestLocation.current?.href.split("#")[0]);

  return <main className="reader-page">
    <header className="reader-toolbar">
      <Link href="/" className="reader-back">← Library</Link>
      <div className="reader-heading"><h1>{book?.title ?? "Opening book"}</h1><p>{book?.authors.join(", ") || ""}</p></div>
      <button className="secondary" disabled={!ready || !chapters.length} aria-expanded={tocOpen} aria-controls="reader-toc" onClick={() => setTocOpen((value) => !value)}>Contents</button>
    </header>
    <div className="reader-messages">
      <p className="reader-save-note">Reading progress is not saved yet.</p>
      {notices.length > 0 && <details><summary>Book notices</summary><ul>{notices.map((notice, index) => <li key={index}>{notice}</li>)}</ul></details>}
      {error && <div role="alert" className="reader-error"><span>{error}</span><button className="secondary" onClick={() => setAttempt((value) => value + 1)}>Reopen book</button></div>}
    </div>
    <div className="reader-content">
      {!ready && !error && <p className="reader-loading" role="status">Preparing your book…</p>}
      <div ref={host} className="epub-host" aria-label="Book content" />
      {tocOpen && <aside id="reader-toc" className="reader-toc" aria-label="Table of contents">
        <div className="account"><h2>Contents</h2><button className="secondary" onClick={() => setTocOpen(false)}>Close</button></div>
        <ol>{chapters.map((chapter, index) => <li key={`${chapter.href}-${index}`} style={{ paddingInlineStart: `${Math.min(chapter.depth, 4) * 12}px` }}><button disabled={moving} onClick={() => void navigate({ href: chapter.href })}>{chapter.label}</button></li>)}</ol>
      </aside>}
    </div>
    <footer className="reader-footer">
      <button disabled={!ready || moving || page?.atStart} onClick={() => void navigate("previous")}>Previous</button>
      <p role="status">{page ? `${currentChapter?.label ?? `Section ${page.section}`} · ${page.page} / ${page.pages}` : ""}</p>
      <button disabled={!ready || moving || page?.atEnd} onClick={() => void navigate("next")}>Next</button>
    </footer>
  </main>;
}
