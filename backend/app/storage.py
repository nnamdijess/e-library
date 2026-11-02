"""Private filesystem operations and crash-aware book ingestion."""

from dataclasses import dataclass
import hashlib
import json
import logging
import multiprocessing
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import BinaryIO, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.documents import InvalidDocument, clean_text, process_document
from app.models import Book

logger = logging.getLogger(__name__)


class StorageFailure(Exception):
    pass


class Inspection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["epub", "pdf"]
    title: str = Field(min_length=1, max_length=500)
    authors: list[str] = Field(max_length=100)
    publisher: str | None
    description: str | None
    language: str | None
    page_count: int | None
    has_cover: bool


@dataclass
class IngestedBook:
    book: Book
    duplicate: bool
    warnings: list[str]


def storage_path(settings: Settings, key: str) -> Path:
    relative = PurePosixPath(key)
    parts = relative.parts
    if not parts or relative.is_absolute() or "\\" in key or ":" in key or any(part in {"..", "."} for part in parts):
        raise StorageFailure("Invalid storage key")
    result = (settings.data_dir / key).resolve()
    if not result.is_relative_to(settings.data_dir) or result == settings.data_dir:
        raise StorageFailure("Storage path escapes the data directory")
    return result


def remove_generated_directory(settings: Settings, directory: Path) -> None:
    # Every recursive deletion is limited to this operation's generated directory.
    resolved = directory.resolve()
    if not resolved.is_relative_to(settings.data_dir) or resolved == settings.data_dir:
        raise StorageFailure("Refusing cleanup outside the data directory")
    if directory.exists():
        shutil.rmtree(directory)


def cleanup_uncommitted_directory(settings: Settings, engine: Engine, directory: Path) -> None:
    if not directory.exists():
        return
    # A commit can succeed even if its acknowledgement fails. Never remove a
    # published directory until a fresh connection confirms it is unreferenced.
    try:
        with Session(engine) as db:
            referenced = db.scalar(select(Book.id).where(Book.storage_key.like(f"books/{directory.name}/%")))
    except SQLAlchemyError:
        logger.error("Storage cleanup deferred because the database is unavailable; run audit-storage later")
        return
    if referenced is None:
        remove_generated_directory(settings, directory)


def inspect_in_process(source: Path, directory: Path, fallback: str, timeout: int) -> Inspection:
    # multiprocessing handles the Windows virtualenv launcher correctly and gives
    # us an owned process handle, unlike killing an intermediate shell/launcher.
    process = multiprocessing.get_context("spawn").Process(
        target=process_document, args=(str(source), str(directory), fallback), daemon=True,
    )
    process.start()
    try:
        process.join(timeout)
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join()
            raise InvalidDocument("Document processing timed out. Try a smaller or simpler book.", "processing_timeout")
        result_path = directory / "result.json"
        if process.exitcode != 0 or not result_path.is_file() or result_path.stat().st_size > 256 * 1024:
            raise InvalidDocument("The document processor could not finish safely.")
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if not result["ok"]:
                raise InvalidDocument(result["message"], result["code"])
            return Inspection.model_validate(result["metadata"])
        except (KeyError, ValueError, TypeError, ValidationError) as error:
            raise InvalidDocument("The document processor returned an invalid result.") from error
    finally:
        if process.is_alive():
            process.kill()
            process.join()
        process.close()


def existing_book(engine: Engine, owner_id: int, digest: str) -> Book | None:
    with Session(engine) as db:
        return db.scalar(select(Book).where(Book.owner_id == owner_id, Book.sha256 == digest))


def ingest_book(stream: BinaryIO, filename: str, owner_id: int, settings: Settings, engine: Engine) -> IngestedBook:
    staging_root = storage_path(settings, "staging")
    staging_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="upload-", dir=staging_root))
    destination: Path | None = None
    committed = False
    try:
        filename = clean_text(filename.replace("\\", "/").split("/")[-1], 255) or "Untitled book"
        fallback = clean_text(PurePosixPath(filename).stem) or "Untitled book"
        source = staging / "source.bin"
        size = 0
        digest = hashlib.sha256()
        stream.seek(0)
        with source.open("xb") as target:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise InvalidDocument("The file exceeds the configured upload limit.", "file_too_large")
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if size == 0:
            raise InvalidDocument("The uploaded file is empty.")
        sha256 = digest.hexdigest()
        existing = existing_book(engine, owner_id, sha256)
        if existing is not None:
            return IngestedBook(existing, True, [])

        metadata = inspect_in_process(source, staging, fallback, settings.processing_timeout_seconds)
        identifier = str(uuid.uuid4())
        book_key = f"books/{identifier}"
        destination = storage_path(settings, book_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(staging / f"original.{metadata.format}")
        (staging / "result.json").unlink()
        cover = staging / "cover.jpg"
        if metadata.has_cover:
            if not cover.is_file() or cover.stat().st_size > 1024 * 1024:
                raise StorageFailure("Invalid generated cover")
            with cover.open("rb+") as cover_file:
                os.fsync(cover_file.fileno())
        elif cover.exists():
            cover.unlink()
        os.replace(staging, destination)
        book = Book(
            id=identifier, owner_id=owner_id, format=metadata.format,
            title=metadata.title, authors=metadata.authors, publisher=metadata.publisher,
            description=metadata.description, language=metadata.language,
            original_filename=filename, storage_key=f"{book_key}/original.{metadata.format}",
            cover_key=f"{book_key}/cover.jpg" if metadata.has_cover else None,
            sha256=sha256, byte_size=size, page_count=metadata.page_count,
        )
        try:
            with Session(engine, expire_on_commit=False) as db:
                db.add(book)
                db.commit()
                committed = True
        except IntegrityError:
            # Different server workers may race to ingest identical bytes.
            existing = existing_book(engine, owner_id, sha256)
            if existing is None:
                raise
            return IngestedBook(existing, True, [])
        warnings = [] if metadata.has_cover else ["No usable cover was available; a placeholder is shown."]
        return IngestedBook(book, False, warnings)
    except (OSError, SQLAlchemyError) as error:
        logger.error("Book storage failed (%s)", type(error).__name__)
        raise StorageFailure("The book could not be stored. Please try again.") from error
    finally:
        remove_generated_directory(settings, staging)
        if destination is not None and not committed:
            cleanup_uncommitted_directory(settings, engine, destination)


def audit_storage(settings: Settings, engine: Engine) -> list[str]:
    """Report crash leftovers without deleting anything. Run with the API stopped."""
    issues = []
    with Session(engine) as db:
        books = list(db.scalars(select(Book)))
    expected_directories = set()
    for book in books:
        expected_directories.add(PurePosixPath(book.storage_key).parent.as_posix())
        for key in (book.storage_key, book.cover_key):
            if key is not None:
                try:
                    if not storage_path(settings, key).is_file():
                        issues.append(f"Missing file for book {book.id}")
                except StorageFailure:
                    issues.append(f"Unsafe storage key for book {book.id}")
    root = storage_path(settings, "books")
    if root.exists():
        for directory in root.iterdir():
            if f"books/{directory.name}" not in expected_directories:
                issues.append(f"Unreferenced book directory: {directory.name}")
    staging = storage_path(settings, "staging")
    if staging.exists():
        for directory in staging.iterdir():
            issues.append(f"Unfinished staging entry: {directory.name}")
    return issues
