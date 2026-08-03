import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import NoReturn

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from donnietts import __version__
from donnietts.api_models import (
    AnnouncementPatch,
    AnnouncementResponse,
    AnnouncementRunResponse,
    ApplicationSettingsPatch,
    ApplicationSettingsResponse,
    DailyAnnouncementCreate,
    OneOffAnnouncementCreate,
    parse_daily_time,
)
from donnietts.database import (
    AnnouncementKindMismatchError,
    AnnouncementNotFoundError,
    AnnouncementRevisionConflictError,
    ApplicationSettingsSnapshot,
    Database,
    DuplicateDailyTimeError,
)
from donnietts.settings import ControllerSettings
from donnietts.speech_status import get_speech_status


logger = logging.getLogger(__name__)


def raise_announcement_http_error(error: Exception) -> NoReturn:
    if isinstance(error, AnnouncementNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, (AnnouncementRevisionConflictError, DuplicateDailyTimeError)):
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(error, AnnouncementKindMismatchError):
        raise HTTPException(status_code=422, detail=str(error)) from error
    logger.warning("Announcement database operation failed: %s", error)
    raise HTTPException(status_code=503, detail="Controller database is not ready") from error


def create_app(settings: ControllerSettings | None = None) -> FastAPI:
    controller_settings = settings or ControllerSettings.from_environment()
    database = Database(controller_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.http_client = httpx.AsyncClient(
            timeout=controller_settings.speech.status_timeout_seconds
        )
        app.state.database = database
        try:
            await database.initialize()
            yield
        finally:
            await app.state.http_client.aclose()
            await database.close()

    app = FastAPI(title="DonnieTTS Controller", version=__version__, lifespan=lifespan)
    app.state.controller_settings = controller_settings

    async def read_application_settings() -> ApplicationSettingsSnapshot:
        try:
            return await database.get_application_settings()
        except Exception as error:
            logger.warning("Controller database is unavailable: %s", error)
            raise HTTPException(status_code=503, detail="Controller database is not ready") from error

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        database_ready, _error = await database.check_ready()
        status_code = 200 if database_ready else 503
        status = "ready" if database_ready else "not_ready"
        return JSONResponse(status_code=status_code, content={"status": status})

    @app.get("/api/v1/status")
    async def status(request: Request) -> dict:
        speech_result, database_result = await asyncio.gather(
            get_speech_status(request.app.state.http_client, controller_settings.speech),
            database.check_ready(),
        )
        database_ready, database_error = database_result

        if database_ready:
            application_settings = await database.get_application_settings()
            announcements_enabled: bool | None = application_settings.announcements_enabled
            mode = application_settings.mode
            timezone: str | None = application_settings.timezone
            database_status = {"status": "ready"}
        else:
            announcements_enabled = None
            mode = "unavailable"
            timezone = None
            database_status = {"status": "unavailable", "error": database_error}

        controller_status = (
            "ok"
            if database_ready and speech_result["status"] == "ready"
            else "degraded"
        )
        return {
            "status": controller_status,
            "version": __version__,
            "announcements_enabled": announcements_enabled,
            "mode": mode,
            "timezone": timezone,
            "database": database_status,
            "speech": speech_result,
        }

    @app.get("/api/v1/announcements", response_model=list[AnnouncementResponse])
    async def list_announcements() -> list[AnnouncementResponse]:
        try:
            announcements = await database.list_announcements()
        except Exception as error:
            logger.warning("Could not list announcements: %s", error)
            raise HTTPException(status_code=503, detail="Controller database is not ready") from error
        return [AnnouncementResponse.from_snapshot(item) for item in announcements]

    @app.get(
        "/api/v1/announcements/{announcement_id}",
        response_model=AnnouncementResponse,
    )
    async def get_announcement(announcement_id: int) -> AnnouncementResponse:
        try:
            snapshot = await database.get_announcement(announcement_id)
        except Exception as error:
            raise_announcement_http_error(error)
        return AnnouncementResponse.from_snapshot(snapshot)

    @app.post(
        "/api/v1/announcements/daily",
        response_model=AnnouncementResponse,
        status_code=201,
    )
    async def create_daily_announcement(
        payload: DailyAnnouncementCreate,
    ) -> AnnouncementResponse:
        try:
            snapshot = await database.create_daily_announcement(
                minute_of_day=parse_daily_time(payload.time),
                template=payload.template,
                enabled=payload.enabled,
                lead_seconds=payload.lead_seconds,
            )
        except Exception as error:
            raise_announcement_http_error(error)
        return AnnouncementResponse.from_snapshot(snapshot)

    @app.post(
        "/api/v1/announcements/one-off",
        response_model=AnnouncementResponse,
        status_code=201,
    )
    async def create_one_off_announcement(
        payload: OneOffAnnouncementCreate,
    ) -> AnnouncementResponse:
        try:
            snapshot = await database.create_one_off_announcement(
                run_at_utc=payload.run_at,
                template=payload.template,
                enabled=payload.enabled,
                lead_seconds=payload.lead_seconds,
            )
        except Exception as error:
            raise_announcement_http_error(error)
        return AnnouncementResponse.from_snapshot(snapshot)

    @app.patch("/api/v1/announcements/{announcement_id}", response_model=AnnouncementResponse)
    async def update_announcement(
        announcement_id: int,
        payload: AnnouncementPatch,
    ) -> AnnouncementResponse:
        try:
            snapshot = await database.update_announcement(
                announcement_id,
                expected_revision=payload.expected_revision,
                enabled=payload.enabled,
                minute_of_day=(
                    parse_daily_time(payload.time) if payload.time is not None else None
                ),
                run_at_utc=payload.run_at,
                template=payload.template,
                lead_seconds=payload.lead_seconds,
            )
        except Exception as error:
            raise_announcement_http_error(error)
        return AnnouncementResponse.from_snapshot(snapshot)

    @app.delete("/api/v1/announcements/{announcement_id}", status_code=204)
    async def delete_announcement(
        announcement_id: int,
        expected_revision: int = Query(ge=1),
    ) -> Response:
        try:
            await database.delete_announcement(announcement_id, expected_revision)
        except Exception as error:
            raise_announcement_http_error(error)
        return Response(status_code=204)

    @app.get("/api/v1/runs", response_model=list[AnnouncementRunResponse])
    async def list_runs() -> list[AnnouncementRunResponse]:
        try:
            runs = await database.runs.list_all()
        except Exception as error:
            logger.warning("Could not list announcement runs: %s", error)
            raise HTTPException(
                status_code=503,
                detail="Controller database is not ready",
            ) from error
        return [AnnouncementRunResponse.from_snapshot(run) for run in runs]

    @app.get("/api/v1/settings", response_model=ApplicationSettingsResponse)
    async def get_settings() -> ApplicationSettingsResponse:
        snapshot = await read_application_settings()
        return ApplicationSettingsResponse.from_snapshot(snapshot)

    @app.patch("/api/v1/settings", response_model=ApplicationSettingsResponse)
    async def update_settings(payload: ApplicationSettingsPatch) -> ApplicationSettingsResponse:
        try:
            snapshot = await database.update_application_settings(
                announcements_enabled=payload.announcements_enabled,
                timezone=payload.timezone,
            )
        except Exception as error:
            logger.warning("Could not update controller settings: %s", error)
            raise HTTPException(status_code=503, detail="Controller database is not ready") from error
        return ApplicationSettingsResponse.from_snapshot(snapshot)

    # The web UI is a static single page served from the package directory.
    # It is mounted last so every API route above takes precedence.
    web_dir = Path(__file__).resolve().parent / "web"
    if web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


app = create_app()
