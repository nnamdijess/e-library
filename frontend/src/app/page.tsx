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
        <p>Milestone 3 adds EPUB and PDF uploads, metadata, and covers. Reading engines and reading progress come in the next milestones.</p>
      </section>
      <p className="footnote">Windows and Android are the initial testing devices. iPadOS 12.5.8 compatibility requires a separate investigation before reader implementation.</p>
    </main>
  );
}
