import type { Metadata } from "next";
import "./globals.css";
import { ReaderPreferencesProvider } from "@/readers/preferences";

export const metadata: Metadata = {
  title: "Ebook Library",
  description: "A personal, self-hosted ebook library. Development foundation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><ReaderPreferencesProvider>{children}</ReaderPreferencesProvider></body></html>;
}
