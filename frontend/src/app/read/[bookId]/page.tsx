import { EpubReader } from "@/components/epub-reader";

export default async function ReaderPage({ params }: { params: Promise<{ bookId: string }> }) {
  const { bookId } = await params;
  return <EpubReader bookId={bookId} />;
}
