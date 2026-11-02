import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ebook Library",
  description: "A personal, self-hosted ebook library. Development foundation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
