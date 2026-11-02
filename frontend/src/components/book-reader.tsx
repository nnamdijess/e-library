"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { EpubReader } from "./epub-reader";
import { PdfReader } from "./pdf-reader";

export function BookReader({ bookId }: { bookId: string }) {
  const [format, setFormat] = useState<"epub" | "pdf" | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void api<{ format: "epub" | "pdf" }>(`/books/${encodeURIComponent(bookId)}`, { signal: controller.signal }).then((book) => setFormat(book.format)).catch((reason) => { if (!controller.signal.aborted) setError(reason.status === 401 ? "Sign in from the library to open this book." : reason.message); });
    return () => controller.abort();
  }, [bookId]);
  if (format === "epub") return <EpubReader bookId={bookId} />;
  if (format === "pdf") return <PdfReader bookId={bookId} />;
  return <main className="shell"><Link href="/">← Library</Link><p className={error ? "reader-error" : ""}>{error || "Opening book…"}</p></main>;
}
