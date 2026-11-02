export type EpubLocation = {
  version: 1;
  format: "epub";
  artifact_version: number;
  cfi: string;
  href: string;
};

export type Chapter = { label: string; href: string; depth: number };
export type PageState = { atStart: boolean; atEnd: boolean; section: number; page: number; pages: number };

export interface ReaderController {
  open(data: ArrayBuffer): Promise<void>;
  next(): Promise<void>;
  previous(): Promise<void>;
  display(location: string): Promise<void>;
  destroy(): void;
}
