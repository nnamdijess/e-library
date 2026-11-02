"""Prepare and cache only versioned, sanitized EPUBs; originals stay private."""

from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import tempfile

from app.config import Settings
from app.documents import InvalidDocument
from app.epub_artifact import ARTIFACT_VERSION, prepare_reading_copy
from app.storage import StorageFailure, remove_generated_directory, storage_path
from app.workers import run_document_worker


@dataclass
class ReadingCopy:
    path: Path
    warnings: list[str]


def cached_copy(settings: Settings, original_key: str, expected_hash: str) -> ReadingCopy | None:
    parent = PurePosixPath(original_key).parent.as_posix()
    path = storage_path(settings, f"{parent}/reader-v{ARTIFACT_VERSION}.epub")
    info = storage_path(settings, f"{parent}/reader-v{ARTIFACT_VERSION}.json")
    if not path.is_file() or not info.is_file():
        return None
    try:
        if info.stat().st_size > 8192:
            return None
        metadata = json.loads(info.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return None
        if metadata.get("source_hash") == expected_hash and metadata.get("artifact_version") == ARTIFACT_VERSION:
            notices = metadata.get("warnings", [])
            if isinstance(notices, list) and all(isinstance(item, str) for item in notices):
                return ReadingCopy(path, notices)
    except (OSError, ValueError):
        pass
    return None


def ensure_reading_copy(settings: Settings, original_key: str, expected_hash: str) -> ReadingCopy:
    existing = cached_copy(settings, original_key, expected_hash)
    if existing:
        return existing
    source = storage_path(settings, original_key)
    if not source.is_file():
        raise StorageFailure("The stored original is missing.")
    staging_root = storage_path(settings, "staging")
    staging_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="reader-", dir=staging_root))
    try:
        run_document_worker(prepare_reading_copy, (str(source), str(staging), expected_hash), settings.processing_timeout_seconds)
        result_file = staging / "result.json"
        if not result_file.is_file() or result_file.stat().st_size > 8192:
            raise InvalidDocument("The reading copy could not be prepared safely.")
        metadata = json.loads(result_file.read_text(encoding="utf-8"))
        if not metadata.get("ok"):
            raise InvalidDocument(metadata.get("message", "The reading copy could not be prepared."), metadata.get("code", "reader_preparation_failed"))
        parent = PurePosixPath(original_key).parent.as_posix()
        destination = storage_path(settings, f"{parent}/reader-v{ARTIFACT_VERSION}.epub")
        info_destination = storage_path(settings, f"{parent}/reader-v{ARTIFACT_VERSION}.json")
        with (staging / "reader.epub").open("rb+") as stream:
            os.fsync(stream.fileno())
        os.replace(staging / "reader.epub", destination)
        os.replace(result_file, info_destination)
        return ReadingCopy(destination, metadata["warnings"])
    finally:
        remove_generated_directory(settings, staging)
