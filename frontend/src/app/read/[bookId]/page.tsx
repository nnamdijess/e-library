import { BookReader } from "@/components/book-reader";

export default async function ReaderPage({ params }: { params: Promise<{ bookId: string }> }) {
  const { bookId } = await params;
  return <BookReader bookId={bookId} />;
}
