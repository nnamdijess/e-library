import type { ReaderPreferences } from "./preferences";

export type EpubLocation = {
  version: 1;
  format: "epub";
  artifact_version: number;
  cfi: string;
  href: string;
};
export type PdfLocation = { version: 1; format: "pdf"; page: number; offset: number };
export type ReadingLocation = EpubLocation | PdfLocation;

export type Chapter = { label: string; href: string; depth: number };
export type PageState = { atStart: boolean; atEnd: boolean; section: number; page: number; pages: number; percentage: number };

export interface ReaderController {
  open(data: ArrayBuffer, initialLocation?: string): Promise<void>;
  next(): Promise<void>;
  previous(): Promise<void>;
  display(location: string): Promise<void>;
  setPreferences(preferences: ReaderPreferences): Promise<void>;
  destroy(): void;
}
