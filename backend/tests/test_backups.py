import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4
from zipfile import ZipFile

import pytest
import httpx

from app.backups import BackupError, MANIFEST, create_backup, restore_backup, verify_backup
from app.config import Settings
from app.maintenance import DataBusy, data_lease
from book_fixtures import epub_bytes, pdf_bytes
from conftest import ORIGIN
from test_auth_catalog import client_for, login
from test_ingestion import upload


def test_complete_backup_restore_and_sign_in(settings, tmp_path):
    async def prepare():
        async with client_for(settings) as client:
            token = (await login(client)).json()["csrf_token"]
            headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
            epub = (await upload(client, epub_bytes())).json()["book"]
            pdf = (await upload(client, pdf_bytes(), name="book.pdf")).json()["book"]
            info = (await client.get(f"/api/v1/books/{epub['id']}/epub")).json()
            reading = (await client.get(info["content_url"])).content
            for book in (epub, pdf):
                location = {"version": 1, "format": "epub", "artifact_version": 2, "cfi": "epubcfi(/6/2!/4/2/1:0)", "href": "text/chapter-0000.xhtml"} if book["format"] == "epub" else {"version": 1, "format": "pdf", "page": 2, "offset": .5}
                response = await client.put(f"/api/v1/books/{book['id']}/progress", headers=headers, json={"base_revision": 0, "update_id": str(uuid4()), "location": location, "percentage": .25})
                assert response.status_code == 200
            assert (await client.patch("/api/v1/preferences", headers=headers, json={"theme": "dark", "font_size": 24})).status_code == 200
            assert (await client.patch(f"/api/v1/books/{epub['id']}", headers=headers, json={"title": "Restored display title"})).status_code == 200
            return epub, pdf, reading, httpx.Cookies(client.cookies)
    epub, pdf, reading, cookies = asyncio.run(prepare())
    archive = tmp_path.parent / (tmp_path.name + ".elbackup.zip")
    result = create_backup(settings.data_dir, archive)
    assert result["books"] == 2 and result["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert verify_backup(archive)["files"] == result["files"]
    destination = tmp_path / "restored"
    assert restore_backup(archive, destination)["sessions_revoked"]
    recovered = Settings(_env_file=None, data_dir=destination, trusted_origins=[ORIGIN])

    async def check():
        async with client_for(recovered, cookies=cookies) as client:
            assert (await client.get("/api/v1/books")).status_code == 401
            assert (await login(client)).status_code == 200
            assert (await client.get("/api/v1/books")).json()["total"] == 2
            assert (await client.get("/api/v1/preferences")).json()["theme"] == "dark"
            assert (await client.get(f"/api/v1/books/{epub['id']}")).json()["title"] == "Restored display title"
            assert (await client.get(f"/api/v1/books/{pdf['id']}/progress")).json()["location"]["offset"] == .5
            assert (await client.get(f"/api/v1/books/{epub['id']}/progress")).json()["revision"] == 1
            info = (await client.get(f"/api/v1/books/{epub['id']}/epub")).json()
            assert (await client.get(info["content_url"])).content == reading
    asyncio.run(check())
    with pytest.raises(BackupError, match="empty"):
        restore_backup(archive, destination)
    with pytest.raises(BackupError, match="not be overwritten"):
        create_backup(settings.data_dir, archive)


def test_live_api_blocks_maintenance(settings, tmp_path):
    async def scenario():
        async with client_for(settings):
            with pytest.raises(DataBusy):
                create_backup(settings.data_dir, tmp_path.parent / "busy.elbackup.zip")
    asyncio.run(scenario())


def test_data_lease_excludes_other_processes(tmp_path):
    code = "from pathlib import Path\nfrom app.maintenance import data_lease\nwith data_lease(Path(" + repr(str(tmp_path)) + ")):\n print('acquired')"
    with data_lease(tmp_path):
        child = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert child.returncode != 0 and "Data is in use" in child.stderr
    child = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert child.returncode == 0


@pytest.mark.parametrize("attack", ["hash", "path", "duplicate", "truncated"])
def test_corrupt_backups_do_not_publish_database(settings, tmp_path, attack):
    archive = tmp_path.parent / (tmp_path.name + ".elbackup.zip")
    create_backup(settings.data_dir, archive)
    with ZipFile(archive) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    manifest = json.loads(entries[MANIFEST])
    if attack == "hash":
        manifest["files"][0]["sha256"] = "0" * 64
    if attack == "path":
        manifest["files"][0]["path"] = "../escaped.sqlite3"
    entries[MANIFEST] = json.dumps(manifest).encode()
    damaged = tmp_path.parent / (tmp_path.name + "-bad.elbackup.zip")
    with ZipFile(damaged, "w") as output:
        for name, content in entries.items():
            output.writestr(name, content)
        if attack == "duplicate":
            with pytest.warns(UserWarning):
                output.writestr("library.sqlite3", entries["library.sqlite3"])
    if attack == "truncated":
        damaged.write_bytes(damaged.read_bytes()[:100])
    destination = tmp_path / "rejected"
    with pytest.raises(BackupError):
        restore_backup(damaged, destination)
    assert not (destination / "library.sqlite3").exists()
    assert not (tmp_path / "escaped.sqlite3").exists()


def test_backup_refuses_staging_and_bad_original(settings, tmp_path):
    staging = settings.data_dir / "staging"
    staging.mkdir()
    (staging / "unfinished").write_text("keep for investigation")
    with pytest.raises(BackupError, match="staging"):
        create_backup(settings.data_dir, tmp_path.parent / "staging.elbackup.zip")
    with pytest.raises(BackupError, match="outside"):
        create_backup(settings.data_dir, settings.data_dir / "backup.elbackup.zip")
