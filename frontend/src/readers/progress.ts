import { api, ApiError } from "@/lib/api";
import type { ReadingLocation } from "./types";

export type ProgressSnapshot = { revision: number; location: ReadingLocation | null; percentage: number; update_id: string | null };
type Pending = { base_revision: number; update_id: string; location: ReadingLocation; percentage: number };
export type SyncState = { message: string; conflict: boolean };

/** One serial save queue. Revisions, not clocks or furthest page, decide conflicts. */
export class ProgressSession {
  private revision = 0;
  private pending: Pending | null = null;
  private remote: ProgressSnapshot | null = null;
  private busy = false;
  private active = true;
  private enabled = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private pollTimer: ReturnType<typeof setInterval> | undefined;
  private storageKey = "";
  private csrf = "";
  private durable = true;
  private path: string;
  private firstQueuedAt = 0;
  private journalId: string | null = null;

  constructor(bookId: string, private notify: (state: SyncState) => void, private restore: (location: ReadingLocation) => Promise<void>) {
    this.path = `/books/${encodeURIComponent(bookId)}/progress`;
  }

  private status(message: string) {
    if (!this.durable) message = message.replace("Position saved locally", "Position remains in this tab");
    if (this.active) this.notify({ message: message + (this.durable ? "" : " Browser storage unavailable; keep this tab open until saved."), conflict: this.remote !== null });
  }

  private journal() {
    try {
      if (this.pending) {
        localStorage.setItem(this.storageKey, JSON.stringify(this.pending));
        this.journalId = this.pending.update_id;
      } else {
        const existing = JSON.parse(localStorage.getItem(this.storageKey) ?? "null") as Pending | null;
        // A late acknowledgement from another tab must not delete a newer
        // journal entry written while its request was in flight.
        if (existing?.update_id === this.journalId) localStorage.removeItem(this.storageKey);
      }
    } catch { this.durable = false; }
  }

  async start(format: "epub" | "pdf", artifactVersion?: number): Promise<ReadingLocation | null> {
    const identity = await api<{ user: { username: string }; csrf_token: string }>("/auth/me");
    if (!this.active) return null;
    this.csrf = identity.csrf_token;
    this.storageKey = `ebook-pending-v1:${identity.user.username}:${this.path}`;
    const saved = await api<ProgressSnapshot>(this.path);
    if (!this.active) return null;
    this.revision = saved.revision;
    try {
      const pending = JSON.parse(localStorage.getItem(this.storageKey) ?? "null") as Pending | null;
      if (pending && Number.isSafeInteger(pending.base_revision) && pending.base_revision >= 0 && typeof pending.update_id === "string" && pending.location?.format === format && Number.isFinite(pending.percentage) && pending.percentage >= 0 && pending.percentage <= 1) { this.pending = pending; this.journalId = pending.update_id; }
    } catch { /* A malformed/expired local journal cannot replace server data. */ }
    const compatible = (location: ReadingLocation | null) => location === null || (location.format === format && (location.format !== "epub" || location.artifact_version === artifactVersion));
    if (!compatible(saved.location) || !compatible(this.pending?.location ?? null)) throw new Error("Saved position uses a different reading-copy version. Position migration is required; it has not been overwritten.");
    if (this.pending?.update_id === saved.update_id) { this.pending = null; this.journal(); }
    if (this.pending && this.pending.base_revision !== saved.revision) {
      this.remote = saved;
      this.status("Another session has a newer saved position. Choose a position below.");
    } else this.status(this.pending ? "Unsaved position restored locally; waiting to sync." : saved.revision ? "Synced" : "Ready to save progress");
    this.pollTimer = setInterval(() => { void this.checkRemote(); }, 15000);
    window.addEventListener("online", this.reconnect);
    window.addEventListener("focus", this.reconnect);
    document.addEventListener("visibilitychange", this.visibility);
    window.addEventListener("pagehide", this.pagehide);
    return this.pending?.location ?? saved.location;
  }

  enable() { this.enabled = true; if (this.pending && !this.remote) void this.flush(); }

  record(location: ReadingLocation, percentage: number) {
    if (!this.active || !this.enabled) return;
    this.pending = { base_revision: this.revision, update_id: crypto.randomUUID(), location, percentage };
    this.firstQueuedAt ||= Date.now();
    this.journal();
    this.status(this.remote ? "Conflicting positions: choose which to keep." : "Unsaved changes");
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { void this.flush(); }, Math.min(1200, Math.max(0, 5000 - (Date.now() - this.firstQueuedAt))));
  }

  async flush(keepalive = false) {
    if (!this.pending || this.busy || this.remote || !this.enabled) return;
    const sending = this.pending;
    this.busy = true;
    this.status("Saving…");
    try {
      const saved = await api<ProgressSnapshot>(this.path, { method: "PUT", headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf }, body: JSON.stringify(sending), keepalive });
      this.revision = saved.revision;
      if (this.pending?.update_id === sending.update_id) this.pending = null;
      else if (this.pending) this.pending.base_revision = saved.revision;
      this.firstQueuedAt = 0;
      this.journal();
      this.status(this.pending ? "Unsaved changes" : "Synced");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        this.remote = (error.detail as { current: ProgressSnapshot }).current;
        this.status("Another session saved a newer position. Choose which to keep.");
      } else this.status(error instanceof ApiError && [401, 403].includes(error.status) ? "Position saved locally. Sign in again to synchronize." : "Position saved locally; server unavailable. Will retry.");
    } finally {
      this.busy = false;
      if (this.active && this.pending && !this.remote) {
        clearTimeout(this.timer);
        this.timer = setTimeout(() => { void this.flush(); }, 5000);
      }
    }
  }

  async checkRemote() {
    if (!this.active || this.busy || this.remote || document.visibilityState === "hidden") return;
    if (this.pending) { await this.flush(); return; }
    try {
      const saved = await api<ProgressSnapshot>(this.path);
      if (!this.active || this.busy || this.pending || this.remote) return;
      if (saved.revision !== this.revision) {
        this.remote = saved;
        this.status("A newer saved position is available from another session.");
      }
    } catch { this.status("Server unavailable; saved position will be checked when connected."); }
  }

  async resolve(useRemote: boolean, currentLocation?: ReadingLocation, percentage = 0) {
    if (!this.remote || this.busy) return;
    const remote = this.remote;
    this.enabled = false;
    try {
      if (useRemote && remote.location) await this.restore(remote.location);
      this.revision = remote.revision;
      this.remote = null;
      if (useRemote) this.pending = null;
      else {
        const location = this.pending?.location ?? currentLocation;
        if (location) this.pending = { base_revision: this.revision, update_id: crypto.randomUUID(), location, percentage: this.pending?.percentage ?? percentage };
      }
      this.journal();
      this.status(this.pending ? "Unsaved changes" : "Synced");
    } catch { this.status("The saved location could not be opened. Your local position is preserved."); }
    finally { this.enabled = true; }
    if (this.pending && !this.remote) await this.flush();
  }

  private reconnect = () => { void this.checkRemote(); };
  private visibility = () => { if (document.visibilityState === "hidden") void this.flush(true); else this.reconnect(); };
  private pagehide = () => { void this.flush(true); };

  destroy() {
    // Journal is already durable before navigation. Keepalive is best effort;
    // it never replaces the journal or counts as confirmation by itself.
    void this.flush(true);
    this.active = false;
    clearTimeout(this.timer);
    clearInterval(this.pollTimer);
    window.removeEventListener("online", this.reconnect);
    window.removeEventListener("focus", this.reconnect);
    document.removeEventListener("visibilitychange", this.visibility);
    window.removeEventListener("pagehide", this.pagehide);
  }
}
