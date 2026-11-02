import { BackendStatus } from "@/components/backend-status";

export default function Home() {
  return (
    <main>
      <p className="eyebrow">Personal ebook library</p>
      <h1>A home for your books.</h1>
      <p className="intro">Milestone 1 establishes the connection between the interface and API.</p>
      <BackendStatus />
      <section aria-labelledby="next-step">
        <h2 id="next-step">What comes next</h2>
        <p>Authentication and a persistent catalog are planned for Milestone 2. Uploads, EPUB and PDF readers, and reading progress are not implemented yet.</p>
      </section>
      <p className="footnote">Windows and Android are the initial testing devices. iPadOS 12.5.8 compatibility requires a separate investigation before reader implementation.</p>
    </main>
  );
}
