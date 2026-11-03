"""Application assembly, explicit schema checks, and safe response defaults."""

from contextlib import asynccontextmanager
from typing import Literal

import anyio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api import router
from app.body_limits import BodyLimits
from app.config import Settings
from app.database import make_engine, require_current_schema


class HealthResponse(BaseModel):
    status: Literal["ok"]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Use an application factory so tests can supply isolated settings."""
    settings = settings if settings is not None else Settings()
    engine = make_engine(settings)

    @asynccontextmanager
    async def lifespan(_application):
        try:
            if not (settings.data_dir / "library.sqlite3").is_file():
                raise RuntimeError("Database missing. From backend run: python -m app.cli migrate")
            require_current_schema(engine)
            yield
        finally:
            engine.dispose()

    application = FastAPI(title=settings.app_name, version="0.8.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.engine = engine
    application.state.upload_lock = anyio.Semaphore(1)
    application.include_router(router)
    application.add_middleware(BodyLimits, max_upload_bytes=settings.max_upload_bytes)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError):
        # FastAPI's default validation detail can echo submitted passwords.
        return JSONResponse(status_code=422, content={"detail": {"code": "invalid_request", "message": "Check the request fields and try again."}})

    @application.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @application.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Report process liveness, not database or storage readiness."""
        return HealthResponse(status="ok")

    return application
