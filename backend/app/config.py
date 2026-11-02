"""Load validated backend settings without creating directories or files."""

from pathlib import Path

from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EBOOK_",
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="forbid",
    )

    app_name: str = Field(default="Ebook Library API", min_length=1)
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    trusted_origins: list[str] = ["http://127.0.0.1:3000"]
    session_cookie_secure: bool = False
    session_days: int = Field(default=7, ge=1, le=30)

    @model_validator(mode="after")
    def validate_security(self):
        if not self.trusted_origins:
            raise ValueError("At least one trusted browser origin is required")
        for origin in self.trusted_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username or parsed.password or parsed.path
                    or parsed.query or parsed.fragment):
                raise ValueError("Trusted origins must be exact HTTP(S) origins")
            _ = parsed.port  # Reject malformed ports at startup.
            if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("Non-loopback origins require HTTPS")
            if not self.session_cookie_secure and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("Non-loopback origins require secure cookies")
        if not self.data_dir.is_absolute():
            self.data_dir = Path(__file__).resolve().parents[2] / self.data_dir
        self.data_dir = self.data_dir.resolve()
        return self
