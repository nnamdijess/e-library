"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";

export type LibraryBook = {
  id: string;
  title: string;
  authors: string[];
  format: "epub" | "pdf";
  byte_size: number;
  page_count: number | null;
  has_cover: boolean;
};

export type Catalog = { items: LibraryBook[]; total: number; limit: number; offset: number };

function Cover({ book }: { book: LibraryBook }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className={`book-cover ${book.format}`}>
      {book.has_cover && !failed ? (
        // Authenticated same-origin JPEGs; no external image service or optimizer.
        <img src={`/api/v1/books/${book.id}/cover`} alt={`Cover of ${book.title}`} loading="lazy" onError={() => setFailed(true)} />
      ) : <div className="cover-placeholder" aria-label="No cover available"><span>{book.format.toUpperCase()}</span><strong>{book.title}</strong></div>}
    </div>
  );
}

export function BookGrid({ books, csrf, onRenamed }: { books: LibraryBook[]; csrf: string; onRenamed: (book: LibraryBook) => void }) {
  const [editing, setEditing] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function rename(event: React.FormEvent, book: LibraryBook) {
    event.preventDefault(); setSaving(true); setError("");
    try {
      const renamed = await api<LibraryBook>(`/books/${encodeURIComponent(book.id)}`, { method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ title: title.trim() }) });
      onRenamed(renamed); setEditing(null);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Could not rename this book. Try again."); }
    finally { setSaving(false); }
  }
  return <ul className="book-grid">{books.map((book) => (
    <li key={book.id} className="book-card">
      <Cover book={book} />
      <div className="book-details">
        <h3>{book.title}</h3>
        {editing === book.id ? <form className="rename-book" onSubmit={(event) => void rename(event, book)}>
          <label htmlFor={`title-${book.id}`}>Book title</label><input id={`title-${book.id}`} autoFocus maxLength={500} required value={title} disabled={saving} onChange={(event) => setTitle(event.target.value)} />
          <div className="rename-actions"><button disabled={saving || !title.trim()} type="submit">{saving ? "Saving…" : "Save title"}</button><button className="secondary" type="button" disabled={saving} onClick={() => setEditing(null)}>Cancel</button></div>
          {error && <p role="alert" className="unavailable">{error}</p>}
        </form> : <button className="rename-link" aria-label={`Rename ${book.title}`} disabled={saving} onClick={() => { setEditing(book.id); setTitle(book.title); setError(""); }}>Rename</button>}
        <p className="book-author">{book.authors.join(", ") || "Unknown author"}</p>
        <p className="book-facts"><span>{book.format.toUpperCase()}</span> · {(book.byte_size / (1024 * 1024)).toFixed(1)} MiB{book.page_count ? ` · ${book.page_count} pages` : ""}</p>
        <Link className="read-book" href={`/read/${book.id}`}>Read book<span className="sr-only">: {book.title}</span></Link>
      </div>
    </li>
  ))}</ul>;
}
