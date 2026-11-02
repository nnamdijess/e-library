import { BackendStatus } from "@/components/backend-status";
import { LibraryAccess } from "@/components/library-access";

export default function Home() {
  return (
    <main>
      <p className="eyebrow">Personal ebook library</p>
      <h1>A home for your books.</h1>
      <p className="intro">A private catalog for your personal collection.</p>
      <LibraryAccess />
      <BackendStatus />
      <section aria-labelledby="next-step">
        <h2 id="next-step">What comes next</h2>
        <p>Milestone 2 adds owner login and a persistent SQLite catalog. Uploads, EPUB and PDF readers, and reading progress are not implemented yet.</p>
      </section>
      <p className="footnote">Windows and Android are the initial testing devices. iPadOS 12.5.8 compatibility requires a separate investigation before reader implementation.</p>
    </main>
  );
}
