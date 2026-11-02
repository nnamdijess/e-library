"""Load validated backend settings without creating directories or files."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EBOOK_",
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="forbid",
    )

    app_name: str = Field(default="Ebook Library API", min_length=1)
