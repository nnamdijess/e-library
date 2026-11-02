"""Owned document-worker lifecycle, shared by ingestion and reader preparation."""

import multiprocessing

from app.documents import InvalidDocument


def run_document_worker(target, args: tuple, timeout: int) -> None:
    process = multiprocessing.get_context("spawn").Process(target=target, args=args, daemon=True)
    process.start()
    try:
        process.join(timeout)
        if process.is_alive():
            raise InvalidDocument("Document processing timed out. Try a smaller or simpler book.", "processing_timeout")
        if process.exitcode != 0:
            raise InvalidDocument("The document processor could not finish safely.")
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join()
        process.close()
