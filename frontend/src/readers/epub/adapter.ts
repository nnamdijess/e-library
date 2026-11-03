import { Book, type Contents, type Location, type Rendition, type NavItem } from "epubjs";
import type { Chapter, EpubLocation, PageState, ReaderController } from "../types";
import { DEFAULT_PREFERENCES, FONTS, PALETTES, type ReaderPreferences } from "../preferences";

type Callbacks = {
  onLocation: (location: EpubLocation, page: PageState) => void;
  onChapters: (chapters: Chapter[]) => void;
  onKeyboard: (direction: "next" | "previous") => void;
  onLink: (href: string) => void;
  onError: () => void;
};

function flatten(items: NavItem[], depth = 0): Chapter[] {
  return items.flatMap((item) => [
    { label: item.label.trim() || "Chapter", href: item.href, depth },
    ...flatten(item.subitems ?? [], depth + 1),
  ]);
}

export class EpubAdapter implements ReaderController {
  private book = new Book({ replacements: "blobUrl" });
  private rendition: Rendition | null = null;
  private observer: ResizeObserver | null = null;
  private disposed = false;
  private opened = false;
  private destroyed = false;
  private observing = false;
  private preferences: ReaderPreferences;
  private retainedCfi: string | undefined;
  private currentCfi: string | undefined;
  private applying = false;
  private linkCleanups = new Map<number, () => void>();

  constructor(private host: HTMLElement, private artifactVersion: number, private callbacks: Callbacks, preferences = DEFAULT_PREFERENCES) { this.preferences = preferences; }

  async open(data: ArrayBuffer, initialLocation?: string): Promise<void> {
    // A restored passage may begin inside a newly reflowed page. Keep its
    // exact anchor until deliberate navigation, rather than saving the earlier
    // page boundary when the initial ResizeObserver notification arrives.
    this.retainedCfi = initialLocation;
    try {
      await this.book.open(data, "binary");
      await this.book.ready;
      this.opened = true;
      if (this.disposed) return;
      await this.book.locations.generate(1600);
      if (this.disposed) return;
      const navigation = await this.book.loaded.navigation;
      if (this.disposed) return;
      this.callbacks.onChapters(flatten(navigation.toc));
      this.rendition = this.book.renderTo(this.host, {
        width: "100%", height: "100%", flow: "paginated", spread: "none",
        // Only our sanitized reading copy may enter this adapter. WebKit needs
        // this flag for parent-owned DOM input handlers; the generated document
        // separately enforces script-src 'none' and contains no publisher code.
        allowScriptedContent: true, resizeOnOrientationChange: true,
      });
      this.rendition.on("relocated", (location: Location) => {
        if (this.disposed || !location?.start?.cfi) return;
        const cfi = this.retainedCfi ?? location.start.cfi;
        this.currentCfi = cfi;
        this.callbacks.onLocation({
          version: 1, format: "epub", artifact_version: this.artifactVersion,
          cfi, href: location.start.href,
        }, {
          atStart: location.atStart, atEnd: location.atEnd,
          section: location.start.index + 1,
          page: location.start.displayed.page, pages: location.start.displayed.total,
          percentage: location.atEnd ? 1 : Math.max(0, Math.min(1, this.book.locations.percentageFromCfi(cfi) || 0)),
        });
        // EPUB.js can only restore a view after resizing once its first CFI
        // has been reported. A resize before then clears the view permanently.
        if (!this.observing && this.observer) {
          this.observing = true;
          this.observer.observe(this.host);
        }
      });
      this.rendition.on("keydown", (event: KeyboardEvent) => this.keydown(event));
      this.rendition.on("displayError", () => { if (!this.disposed) this.callbacks.onError(); });
      this.rendition.hooks.content.register((contents: Contents) => this.handleLinks(contents));
      this.applyTheme();
      this.rendition.hooks.unloaded.register((view: { section: { index: number } }) => {
        const index = view.section.index;
        this.linkCleanups.get(index)?.();
        this.linkCleanups.delete(index);
      });
      this.observer = new ResizeObserver(() => {
        const { width, height } = this.host.getBoundingClientRect();
        if (!this.disposed && !this.applying && width > 0 && height > 0) this.rendition?.resize(Math.floor(width), Math.floor(height));
      });
      await this.move(() => this.rendition!.display(initialLocation));
    } finally {
      if (this.disposed && this.opened) this.release();
    }
  }

  keydown(event: KeyboardEvent) {
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      this.callbacks.onKeyboard(event.key === "ArrowRight" ? "next" : "previous");
    }
  }

  private handleLinks(contents: Contents) {
    const index = contents.sectionIndex;
    this.linkCleanups.get(index)?.();
    // Parent-owned delegated handlers work under the reading copy's strict CSP
    // without permitting inline publisher event handlers or external navigation.
    for (const anchor of contents.document.querySelectorAll("a[href]")) (anchor as HTMLAnchorElement).onclick = null;
    const click = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const anchor = target?.closest?.("a[href]");
      if (!anchor) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const section = this.book.spine.get(index);
      const url = new URL(anchor.getAttribute("href") ?? "", `https://epub.invalid/${section.href}`);
      const path = url.pathname.slice(1);
      if (url.origin === "https://epub.invalid" && !url.search && this.book.spine.get(path)) {
        this.callbacks.onLink(path + url.hash);
      }
    };
    contents.document.addEventListener("click", click, true);
    this.linkCleanups.set(index, () => contents.document.removeEventListener("click", click, true));
  }

  private async move(operation: () => Promise<unknown>) {
    if (this.disposed || !this.rendition) return;
    const rendition = this.rendition;
    let finish: () => void = () => {};
    let fail: (error: Error) => void = () => {};
    const located = new Promise<void>((resolve, reject) => { finish = resolve; fail = reject; });
    const timer = setTimeout(() => fail(new Error("The reading location could not be resolved.")), 15000);
    rendition.on("relocated", finish);
    try {
      // display/next resolve before the RAF that updates rendition.location.
      // Wait for that location before UI changes can trigger another resize.
      await Promise.all([operation(), located]);
    } finally { clearTimeout(timer); rendition.off("relocated", finish); }
  }

  async next() { this.retainedCfi = undefined; await this.move(() => this.rendition!.next()); }
  async previous() { this.retainedCfi = undefined; await this.move(() => this.rendition!.prev()); }
  async display(location: string) { this.retainedCfi = undefined; await this.move(() => this.rendition!.display(location)); }

  private applyTheme() {
    const { font_family, font_size, line_height, theme } = this.preferences;
    const palette = PALETTES[theme];
    this.rendition!.themes.default({
      "html, body": { background: `${palette.background} !important`, color: `${palette.foreground} !important` },
      "body": { "font-family": `${FONTS[font_family]} !important`, "font-size": `${font_size}px !important`, "line-height": `${line_height} !important` },
      "body *": { "font-family": `${FONTS[font_family]} !important`, color: "inherit !important", "background-color": "transparent !important" },
      "p, li, div, span, td, th": { "font-size": "inherit !important", "line-height": `${line_height} !important` },
      "a": { color: `${palette.link} !important` },
    });
  }

  async setPreferences(preferences: ReaderPreferences) {
    const changed = JSON.stringify(this.preferences) !== JSON.stringify(preferences);
    this.preferences = preferences;
    if (!changed || !this.rendition || this.disposed) return;
    this.applying = true;
    this.retainedCfi = this.currentCfi;
    try {
      const { width, height } = this.host.getBoundingClientRect();
      this.rendition.resize(Math.floor(width), Math.floor(height));
      this.applyTheme();
      this.rendition.clear();
      await this.move(() => this.rendition!.display(this.retainedCfi));
    } finally { this.applying = false; }
  }

  private release() {
    if (this.destroyed) return;
    this.destroyed = true;
    for (const cleanup of this.linkCleanups.values()) cleanup();
    this.linkCleanups.clear();
    this.book.destroy(); // Also destroys its rendition and revokes resource blobs.
  }

  destroy() {
    this.disposed = true;
    this.observer?.disconnect();
    if (this.opened) this.release();
  }
}
