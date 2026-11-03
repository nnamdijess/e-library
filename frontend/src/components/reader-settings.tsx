"use client";
import type { ReaderPreferences } from "@/readers/preferences";

export function ReaderSettings({ value, update, status, onClose, epub = false }: {
  value: ReaderPreferences; update: (patch: Partial<ReaderPreferences>) => void; status: string; onClose: () => void; epub?: boolean;
}) {
  return <aside className="reader-settings" aria-label="Reading settings">
    <div className="account"><h2>Reading settings</h2><button className="secondary" onClick={onClose}>Close settings</button></div>
    <label>Theme<select aria-label="Theme" value={value.theme} onChange={(event) => update({ theme: event.target.value as ReaderPreferences["theme"] })}><option value="light">Light</option><option value="sepia">Sepia</option><option value="dark">Dark</option></select></label>
    {epub && <>
      <label>Font family<select aria-label="Font family" value={value.font_family} onChange={(event) => update({ font_family: event.target.value as ReaderPreferences["font_family"] })}><option value="georgia">Georgia</option><option value="palatino">Palatino</option><option value="sans">Sans serif</option></select></label>
      <label>Font size ({value.font_size}px)<input aria-label="Font size" type="range" min="14" max="36" step="1" value={value.font_size} onChange={(event) => update({ font_size: Number(event.target.value) })} /></label>
      <label>Line spacing<select aria-label="Line spacing" value={value.line_height} onChange={(event) => update({ line_height: Number(event.target.value) })}>{[1.2, 1.5, 1.65, 1.8, 2, 2.2].map((height) => <option key={height} value={height}>{height}</option>)}</select></label>
      <label>Margins<select aria-label="Margins" value={value.margin} onChange={(event) => update({ margin: Number(event.target.value) })}><option value={8}>Narrow</option><option value={32}>Comfortable</option><option value={64}>Wide</option><option value={80}>Extra wide</option></select></label>
    </>}
    <p role="status" className="preferences-status">{status}</p>
    <p className="settings-note">Applies to your account across devices.{!epub && " PDF pages keep their original colors and formatting."}</p>
  </aside>;
}
