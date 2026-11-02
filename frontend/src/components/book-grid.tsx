"use client";

import { useState } from "react";
import Link from "next/link";

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

export function BookGrid({ books }: { books: LibraryBook[] }) {
  return <ul className="book-grid">{books.map((book) => (
    <li key={book.id} className="book-card">
      <Cover book={book} />
      <div className="book-details">
        <h3>{book.title}</h3>
        <p className="book-author">{book.authors.join(", ") || "Unknown author"}</p>
        <p className="book-facts"><span>{book.format.toUpperCase()}</span> · {(book.byte_size / (1024 * 1024)).toFixed(1)} MiB{book.page_count ? ` · ${book.page_count} pages` : ""}</p>
        {book.format === "epub" ? <Link className="read-book" href={`/read/${book.id}`}>Read book<span className="sr-only">: {book.title}</span></Link> : <p className="book-facts">PDF reading coming next</p>}
      </div>
    </li>
  ))}</ul>;
}
