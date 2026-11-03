import { BackendStatus } from "@/components/backend-status";
import { LibraryAccess } from "@/components/library-access";

export default function Home() {
  return (
    <main className="home-shell">
      <p className="eyebrow">Personal ebook library</p>
      <h1>A home for your books.</h1>
      <p className="intro">A private catalog for your personal collection.</p>
      <LibraryAccess />
      <BackendStatus />
      <section aria-labelledby="next-step">
        <h2 id="next-step">What comes next</h2>
        <p>Open an EPUB or PDF with Read book. Your position is saved when the server confirms it.</p>
      </section>
      <p className="footnote">Built for Windows, Android, and modern iPhone browsers. Older iPad compatibility remains planned; device verification is ongoing.</p>
    </main>
  );
}
