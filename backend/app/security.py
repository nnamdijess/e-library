"""Password hashing, token derivation, and single-owner provisioning."""

import hashlib
import re
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.orm import Session

from app.models import User

password_hasher = PasswordHasher()
# Equal-cost verification for an unknown username; never a usable owner password.
dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token: str) -> str:
    # A domain-separated derivation, available only through same-origin JSON.
    # It cannot be recovered from the stored session hash.
    return hashlib.sha256(("ebook-csrf:" + token).encode()).hexdigest()


def verify_password(encoded: str, password: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def provision_owner(db: Session, username: str, password: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", username):
        raise ValueError("Username must be 1-64 ASCII letters, digits, dots, underscores, or hyphens")
    if not 12 <= len(password) <= 1024:
        raise ValueError("Use a password between 12 and 1024 characters")
    if db.get(User, 1) is not None:
        raise ValueError("An owner already exists; provisioning will not replace it")
    db.commit()  # Release the lookup lock; the singleton constraint handles races.
    db.add(User(id=1, username=username.lower(), password_hash=password_hasher.hash(password), created_at=int(time.time())))
    db.commit()
