"""Portable offline backups: SQLite snapshot, private files and checked restore."""
from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED, BadZipFile

from app.maintenance import data_lease
from app.version import APP_VERSION

MANIFEST = "backup-manifest.json"
MAX_FILES = 100_000
MAX_MANIFEST = 16 * 1024 * 1024
MAX_TOTAL = 128 * 1024**3


class BackupError(ValueError):
    pass


def member_name(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or any(ord(char) < 32 for char in name):
        raise BackupError("Unsafe backup file path.")
    if PurePosixPath(name).is_absolute() or any(part in {"", ".", ".."} for part in name.split("/")):
        raise BackupError("Unsafe backup file path.")
    if name != "library.sqlite3" and not name.startswith("books/"):
        raise BackupError("Unexpected backup file path.")
    return name


def regular_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
        raise BackupError("Backup data must contain ordinary files, without symbolic links or junctions.")


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_snapshot(root):
    database = root / "library.sqlite3"
    regular_file(database)
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA trusted_schema=OFF")
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchone():
            raise BackupError("Backup database integrity or foreign-key validation failed.")
        revision = db.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision is None:
            raise BackupError("Backup has no schema revision.")
        count = 0
        for key, cover, expected in db.execute("SELECT storage_key, cover_key, sha256 FROM books"):
            original = root / member_name(key)
            regular_file(original)
            if digest_file(original) != expected:
                raise BackupError("A book original does not match its catalog hash.")
            if cover is not None:
                regular_file(root / member_name(cover))
            count += 1
        return {"schema_revision": revision[0], "books": count}


def source_files(root):
    allowed = {"books", "staging", "library.sqlite3", "library.sqlite3-wal", "library.sqlite3-shm", "library.sqlite3-journal", ".library.lock"}
    for item in root.iterdir():
        if item.name not in allowed:
            raise BackupError("Unknown files in the data root; review them before backing up.")
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise BackupError("Symbolic links and junctions are not supported in data.")
    staging = root / "staging"
    if staging.exists() and any(staging.iterdir()):
        raise BackupError("Unfinished staging files exist. Run audit-storage and investigate before backing up.")
    books = root / "books"
    files = []
    if books.exists():
        for directory, dirs, names in os.walk(books, followlinks=False):
            for name in dirs:
                child = Path(directory) / name
                if child.is_symlink() or getattr(child, "is_junction", lambda: False)():
                    raise BackupError("Symbolic links and junctions are not supported in data.")
            for name in names:
                path = Path(directory) / name
                regular_file(path)
                files.append(member_name(path.relative_to(root).as_posix()))
                if len(files) >= MAX_FILES:
                    raise BackupError("The backup contains too many files.")
    return sorted(files)


def create_backup(data_dir: Path, output: Path):
    root, output = data_dir.resolve(), output.resolve()
    if output.is_relative_to(root):
        raise BackupError("Store backups outside the live data directory.")
    if output.exists():
        raise BackupError("The backup destination already exists; it will not be overwritten.")
    if not (root / "library.sqlite3").is_file():
        raise BackupError("No library database exists to back up.")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with data_lease(root), tempfile.TemporaryDirectory(prefix=".ebook-backup-", dir=output.parent) as temporary:
        work = Path(temporary)
        os.chmod(work, 0o700)
        snapshot = work / "snapshot"
        snapshot.mkdir()
        for name in source_files(root):
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, target)
        with closing(sqlite3.connect((root / "library.sqlite3").as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(snapshot / "library.sqlite3")) as target:
                source.backup(target)
        summary = inspect_snapshot(snapshot)
        records = []
        for path in sorted(snapshot.rglob("*")):
            if path.is_file():
                records.append({"path": path.relative_to(snapshot).as_posix(), "size": path.stat().st_size, "sha256": digest_file(path)})
        if sum(item["size"] for item in records) > MAX_TOTAL:
            raise BackupError("Backup exceeds the supported expanded-size limit.")
        if len({item["path"].casefold() for item in records}) != len(records):
            raise BackupError("Ambiguous file names cannot be restored portably.")
        manifest = {"format": "ebook-library-backup", "version": 1, "app_version": APP_VERSION, "created_at": datetime.now(timezone.utc).isoformat(), **summary, "files": records}
        serialized = json.dumps(manifest, ensure_ascii=True).encode()
        if len(serialized) > MAX_MANIFEST:
            raise BackupError("Backup manifest exceeds its limit.")
        archive_path = work / "backup.partial"
        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr(MANIFEST, serialized)
            for item in records:
                archive.write(snapshot / item["path"], item["path"])
        # Exclusive creation never replaces an existing backup. A crash while
        # publishing may leave an incomplete archive; verification rejects it.
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream, archive_path.open("rb") as source:
                shutil.copyfileobj(source, stream, 1024 * 1024)
                stream.flush(); os.fsync(stream.fileno())
        except BaseException:
            output.unlink(missing_ok=True)
            raise
        return {**summary, "files": len(records), "sha256": digest_file(output)}


def extract_verified(archive_path: Path, root: Path):
    try:
        with ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES + 1 or len({entry.orig_filename.casefold() for entry in entries}) != len(entries):
                raise BackupError("Backup has too many or duplicate entries.")
            manifest_info = archive.getinfo(MANIFEST)
            if manifest_info.file_size > MAX_MANIFEST:
                raise BackupError("Backup manifest exceeds its limit.")
            manifest = json.loads(archive.read(MANIFEST))
            if not isinstance(manifest, dict) or manifest.get("format") != "ebook-library-backup" or manifest.get("version") != 1:
                raise BackupError("Unsupported backup format/version.")
            records = manifest.get("files")
            if not isinstance(records, list) or not records or len(records) > MAX_FILES:
                raise BackupError("Invalid backup file manifest.")
            expected = {}
            total = 0
            for record in records:
                if not isinstance(record, dict):
                    raise BackupError("Invalid backup file record.")
                name = member_name(record.get("path"))
                size, digest = record.get("size"), record.get("sha256")
                if type(size) is not int or size < 0 or not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) or name in expected:
                    raise BackupError("Invalid backup file record.")
                expected[name] = record
                total += size
            if total > MAX_TOTAL or "library.sqlite3" not in expected:
                raise BackupError("Backup size is unsupported or its database is missing.")
            if {entry.orig_filename for entry in entries} != {MANIFEST, *expected}:
                raise BackupError("Backup entries do not match the manifest.")
            if shutil.disk_usage(root).free < total + 16 * 1024 * 1024:
                raise BackupError("Not enough free space to verify/restore this backup.")
            for entry in entries:
                if entry.flag_bits & 1 or entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED} or stat.S_IFMT(entry.external_attr >> 16) not in {0, stat.S_IFREG}:
                    raise BackupError("Encrypted, special, or unsupported backup entries are not allowed.")
                if entry.orig_filename == MANIFEST:
                    continue
                name = member_name(entry.orig_filename)
                record = expected[name]
                if entry.file_size != record["size"]:
                    raise BackupError("Backup file size does not match the manifest.")
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                digest, size = hashlib.sha256(), 0
                with archive.open(entry) as source, target.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        if size > record["size"]:
                            raise BackupError("Backup expands beyond its declared size.")
                        digest.update(chunk); output.write(chunk)
                if size != record["size"] or digest.hexdigest() != record["sha256"]:
                    raise BackupError("Backup file checksum validation failed.")
            summary = inspect_snapshot(root)
            if summary["schema_revision"] != manifest.get("schema_revision") or summary["books"] != manifest.get("books"):
                raise BackupError("Backup catalog does not match its manifest.")
            return {**summary, "files": len(records), "sha256": digest_file(archive_path)}
    except (BadZipFile, KeyError, json.JSONDecodeError, UnicodeError, RuntimeError, sqlite3.Error, OSError) as error:
        raise BackupError("Backup is incomplete, corrupt, or inaccessible.") from error


def verify_backup(archive: Path, work_dir: Path | None = None):
    with tempfile.TemporaryDirectory(prefix="ebook-verify-", dir=work_dir) as directory:
        return extract_verified(archive.resolve(), Path(directory))


def restore_backup(archive: Path, destination: Path):
    destination = destination.resolve()
    with data_lease(destination):
        if any(path.name != ".library.lock" for path in destination.iterdir()):
            raise BackupError("Restore requires an empty data directory. Existing data will not be overwritten.")
        with tempfile.TemporaryDirectory(prefix=".restore-", dir=destination) as directory:
            staging = Path(directory)
            summary = extract_verified(archive.resolve(), staging)
            # Never resurrect sessions that were revoked after the snapshot.
            with closing(sqlite3.connect(staging / "library.sqlite3")) as db:
                db.execute("DELETE FROM sessions")
                db.commit()
            if (staging / "books").exists():
                if not (staging / "books").resolve().is_relative_to(destination) or (destination / "books").resolve().parent != destination:
                    raise BackupError("Unsafe restore publication path.")
                os.replace(staging / "books", destination / "books")
            # Publish the database last; interruption cannot start a partial library.
            os.replace(staging / "library.sqlite3", destination / "library.sqlite3")
            return {**summary, "sessions_revoked": True}
