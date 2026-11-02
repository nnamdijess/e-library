"""Assemble the API; persistence and authentication come in Milestone 2."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import Settings


class HealthResponse(BaseModel):
    status: Literal["ok"]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Use an application factory so tests can supply isolated settings."""
    settings = settings if settings is not None else Settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")

    @application.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Report process liveness, not database or storage readiness."""
        return HealthResponse(status="ok")

    return application
