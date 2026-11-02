"""Server-authoritative positions. Revision checks prevent stale-device writes."""
import time
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.documents import InvalidDocument
from app.epub_artifact import ARTIFACT_VERSION
from app.models import Book, ReadingProgress


class EpubPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[1]
    format: Literal["epub"]
    artifact_version: int = Field(ge=1)
    cfi: str = Field(max_length=2048, pattern=r"^epubcfi\([^\s<>]+\)$")
    href: str = Field(max_length=100, pattern=r"^text/chapter-[0-9]{4}\.xhtml$")


class PdfPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[1]
    format: Literal["pdf"]
    page: int = Field(ge=1, le=20000)
    offset: float = Field(ge=0, le=1, allow_inf_nan=False)


class ProgressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0, strict=True)
    update_id: UUID
    location: Annotated[EpubPosition | PdfPosition, Field(discriminator="format")]
    percentage: float = Field(ge=0, le=1, allow_inf_nan=False)


def snapshot(record: ReadingProgress | None):
    if record is None:
        return {"revision": 0, "location": None, "percentage": 0, "update_id": None, "updated_at": None}
    return {key: getattr(record, key) for key in ("revision", "location", "percentage", "update_id", "updated_at")}


def get_progress(db: Session, user_id: int, book_id: str):
    return db.get(ReadingProgress, (user_id, book_id))


def save_progress(db: Session, book: Book, user_id: int, body: ProgressUpdate):
    location = body.location
    if location.format != book.format:
        raise InvalidDocument("The position format does not match this book.", "position_format")
    if isinstance(location, EpubPosition) and location.artifact_version != ARTIFACT_VERSION:
        raise InvalidDocument("This position uses a different reading-copy version. Reopen the book.", "position_version")
    if isinstance(location, PdfPosition) and (book.page_count is None or location.page > book.page_count):
        raise InvalidDocument("The PDF page is outside this book.", "position_page")
    percentage = ((location.page - 1 + location.offset) / book.page_count) if isinstance(location, PdfPosition) else body.percentage
    book_id = book.id
    db.commit()  # Release the authorization read before atomic compare-and-set.
    values = dict(location=location.model_dump(), percentage=percentage, update_id=str(body.update_id), updated_at=int(time.time()))
    if body.base_revision == 0:
        changed = db.execute(insert(ReadingProgress).values(user_id=user_id, book_id=book_id, revision=1, **values).on_conflict_do_nothing(index_elements=["user_id", "book_id"]).returning(ReadingProgress.revision)).scalar_one_or_none()
    else:
        changed = db.execute(update(ReadingProgress).where(ReadingProgress.user_id == user_id, ReadingProgress.book_id == book_id, ReadingProgress.revision == body.base_revision).values(revision=ReadingProgress.revision + 1, **values).returning(ReadingProgress.revision)).scalar_one_or_none()
    db.commit()
    db.expire_all()
    current = get_progress(db, user_id, book_id)
    # A retry after a lost response is successful only for the same operation
    # and payload. Older operations cannot undo later confirmed revisions.
    replay = current is not None and current.update_id == str(body.update_id) and current.location == values["location"] and current.percentage == percentage
    return changed is not None or replay, snapshot(current)
