"""Persistent catalog and authentication records. Times are UTC epoch seconds."""

import time
import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("id = 1", name="single_owner"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[int] = mapped_column(default=lambda: int(time.time()))



class LoginSession(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Anonymous sessions provide login CSRF protection and expire in 10 minutes.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[int] = mapped_column()
    expires_at: Mapped[int] = mapped_column(index=True)


class LoginThrottle(Base):
    __tablename__ = "login_throttle"
    __table_args__ = (CheckConstraint("id = 1", name="single_throttle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window_start: Mapped[int] = mapped_column()
    attempts: Mapped[int] = mapped_column()


class Book(Base):
    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint("format IN ('epub', 'pdf')", name="book_format"),
        CheckConstraint("byte_size >= 0", name="book_size"),
        CheckConstraint("page_count IS NULL OR page_count > 0", name="book_pages"),
        CheckConstraint("artifact_version >= 1", name="book_artifact_version"),
        UniqueConstraint("owner_id", "sha256", name="owner_book_hash"),
        Index("ix_books_owner_created", "owner_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    format: Mapped[str] = mapped_column(String(4))
    title: Mapped[str] = mapped_column(String(500))
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    publisher: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(64))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    cover_key: Mapped[str | None] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column()
    page_count: Mapped[int | None] = mapped_column()
    artifact_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[int] = mapped_column(default=lambda: int(time.time()))

    @property
    def has_cover(self) -> bool:
        return self.cover_key is not None


class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    __table_args__ = (
        CheckConstraint("revision > 0", name="progress_revision"),
        CheckConstraint("percentage >= 0 AND percentage <= 1", name="progress_percentage"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    location: Mapped[dict] = mapped_column(JSON)
    percentage: Mapped[float] = mapped_column(Float)
    revision: Mapped[int] = mapped_column()
    update_id: Mapped[str] = mapped_column(String(36))
    updated_at: Mapped[int] = mapped_column()


class ReaderPreferences(Base):
    __tablename__ = "reader_preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    font_family: Mapped[str] = mapped_column(String(20))
    font_size: Mapped[int] = mapped_column()
    line_height: Mapped[float] = mapped_column(Float)
    margin: Mapped[int] = mapped_column()
    theme: Mapped[str] = mapped_column(String(10))
    pdf_zoom: Mapped[str] = mapped_column(String(12))
