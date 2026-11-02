"""Owner-scoped catalog and cookie-session endpoints."""

import secrets
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.orm import Session

from app.models import Book, LoginSession, LoginThrottle, User
from app.security import csrf_token, dummy_hash, password_hasher, token_hash, verify_password

router = APIRouter(prefix="/api/v1")
COOKIE = "ebook_session"
COOKIE_PATH = "/api"
LOGIN_WINDOW = 300
LOGIN_LIMIT = 10


def fail(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def get_db(request: Request):
    with Session(request.app.state.engine, expire_on_commit=False) as db:
        yield db


Database = Annotated[Session, Depends(get_db)]


def session_record(request: Request, db: Session) -> LoginSession | None:
    token = request.cookies.get(COOKIE, "")
    if not token or len(token) > 128:
        return None
    record = db.get(LoginSession, token_hash(token))
    if record is None or record.expires_at <= int(time.time()):
        return None
    return record


def require_user(request: Request, db: Database) -> User:
    record = session_record(request, db)
    user = db.get(User, record.user_id) if record and record.user_id else None
    if user is None:
        fail(401, "authentication_required", "Sign in to access your library.")
    return user


Owner = Annotated[User, Depends(require_user)]


def require_origin(request: Request) -> None:
    if request.headers.get("origin") not in request.app.state.settings.trusted_origins:
        fail(403, "untrusted_origin", "Request origin is not allowed.")


def require_csrf(request: Request, db: Database) -> LoginSession:
    require_origin(request)
    record = session_record(request, db)
    supplied = request.headers.get("x-csrf-token", "")
    expected = csrf_token(request.cookies.get(COOKIE, ""))
    if record is None or len(supplied) != 64 or not secrets.compare_digest(supplied.encode(), expected.encode()):
        fail(403, "csrf_failed", "Refresh the page and try again.")
    return record


CsrfSession = Annotated[LoginSession, Depends(require_csrf)]


def issue_session(request: Request, response: Response, db: Session, user_id: int | None) -> str:
    now = int(time.time())
    lifetime = request.app.state.settings.session_days * 86400 if user_id else 600
    token = secrets.token_urlsafe(32)
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now))
    db.add(LoginSession(token_hash=token_hash(token), user_id=user_id, created_at=now, expires_at=now + lifetime))
    db.commit()
    response.set_cookie(
        COOKIE, token, max_age=lifetime, httponly=True,
        secure=request.app.state.settings.session_cookie_secure,
        samesite="strict", path=COOKIE_PATH,
    )
    return token


@router.get("/auth/csrf")
def get_csrf(request: Request, response: Response, db: Database):
    # A custom header prevents cross-origin forms/navigation from minting cookies.
    # Cross-origin JavaScript cannot pass preflight because CORS is not enabled.
    if (request.headers.get("x-ebook-request") != "1"
            or request.headers.get("sec-fetch-site") == "cross-site"):
        fail(403, "csrf_bootstrap_failed", "Use the library interface to sign in.")
    if "origin" in request.headers:
        require_origin(request)
    record = session_record(request, db)
    if record:
        token = request.cookies[COOKIE]
    else:
        db.commit()  # Release the read transaction before acquiring a write lock.
        token = issue_session(request, response, db, None)
    return {"csrf_token": csrf_token(token)}


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: SecretStr = Field(min_length=1, max_length=1024)


@router.post("/auth/login")
def login(body: LoginRequest, request: Request, response: Response, db: Database, previous: CsrfSession):
    db.commit()  # CSRF lookup opened a read transaction; don't upgrade its lock.
    now = int(time.time())
    reset = LoginThrottle.window_start <= now - LOGIN_WINDOW
    # One atomic claim per password verification, shared across workers/restarts.
    claimed = db.execute(
        update(LoginThrottle)
        .where(LoginThrottle.id == 1, reset | (LoginThrottle.attempts < LOGIN_LIMIT))
        .values(
            window_start=case((reset, now), else_=LoginThrottle.window_start),
            attempts=case((reset, 1), else_=LoginThrottle.attempts + 1),
        )
        .returning(LoginThrottle.id)
    ).scalar_one_or_none()
    db.commit()
    if claimed is None:
        raise HTTPException(429, detail={"code": "login_throttled", "message": "Too many sign-in attempts. Try again in five minutes."}, headers={"Retry-After": str(LOGIN_WINDOW)})
    user = db.scalar(select(User).where(User.username == body.username.lower()))
    db.commit()  # Do not hold a SQLite read lock during expensive password hashing.
    password = body.password.get_secret_value()
    valid = verify_password(user.password_hash if user else dummy_hash, password)
    if not valid or user is None:
        fail(401, "invalid_credentials", "Incorrect username or password.")
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hasher.hash(password)
    db.delete(previous)  # Rotate the pre-login session to prevent session fixation.
    token = issue_session(request, response, db, user.id)
    return {"user": {"username": user.username}, "csrf_token": csrf_token(token)}


@router.get("/auth/me")
def me(request: Request, user: Owner):
    return {"user": {"username": user.username}, "csrf_token": csrf_token(request.cookies[COOKIE])}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Database, record: CsrfSession, _user: Owner):
    digest = record.token_hash
    db.commit()
    db.execute(delete(LoginSession).where(LoginSession.token_hash == digest))
    db.commit()
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, samesite="strict", secure=request.app.state.settings.session_cookie_secure)


class BookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    format: Literal["epub", "pdf"]
    title: str
    authors: list[str]
    publisher: str | None
    description: str | None
    language: str | None
    byte_size: int
    page_count: int | None
    created_at: int


class CatalogResponse(BaseModel):
    items: list[BookResponse]
    total: int
    limit: int
    offset: int


@router.get("/books", response_model=CatalogResponse)
def books(db: Database, user: Owner, limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    items = db.scalars(select(Book).where(Book.owner_id == user.id).order_by(Book.created_at.desc(), Book.id).limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(Book).where(Book.owner_id == user.id))
    return CatalogResponse(items=[BookResponse.model_validate(book) for book in items], total=total or 0, limit=limit, offset=offset)


@router.get("/books/{book_id}", response_model=BookResponse)
def book(book_id: str, db: Database, user: Owner):
    item = db.scalar(select(Book).where(Book.id == book_id, Book.owner_id == user.id))
    if item is None:
        fail(404, "book_not_found", "Book not found.")
    return item
