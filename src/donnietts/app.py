import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import NoReturn

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from donnietts import __version__
from donnietts.api_models import (
    AnnouncementResponse,
    AnnouncementRunResponse,
    ApplicationSettingsPatch,
    ApplicationSettingsResponse,
)
from donnietts.database import (
    AnnouncementNotFoundError,
    ApplicationSettingsSnapshot,
    Database,
)
from donnietts.schedule import (
    ScheduleConflictError,
    ScheduleError,
    ScheduleStore,
    parse_schedule,
)
from donnietts.settings import ControllerSettings
from donnietts.speech_status import get_speech_status


logger = logging.getLogger(__name__)


def raise_announcement_http_error(error: Exception) -> NoReturn:
    if isinstance(error, AnnouncementNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    logger.warning("Announcement database operation failed: %s", error)
    raise HTTPException(status_code=503, detail="Controller database is not ready") from error


def create_app(settings: ControllerSettings | None = None) -> FastAPI:
    controller_settings = settings or ControllerSettings.from_environment()
    database = Database(controller_settings)
    schedule_store = ScheduleStore(controller_settings.resolved_schedule_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.http_client = httpx.AsyncClient(
            timeout=controller_settings.speech.status_timeout_seconds
        )
        app.state.database = database
        try:
            await database.initialize()
            try:
                schedule = await asyncio.to_thread(schedule_store.load)
                await database.sync_schedule(schedule)
            except ScheduleError as error:
                logger.warning("Schedule is not ready at startup: %s", error)
            yield
        finally:
            await app.state.http_client.aclose()
            await database.close()

    app = FastAPI(title="DonnieTTS Controller", version=__version__, lifespan=lifespan)
    app.state.controller_settings = controller_settings
    app.state.schedule_store = schedule_store

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
        database_ready, database_error = await database.check_ready()
        try:
            await asyncio.to_thread(schedule_store.load)
            schedule_error = None
        except ScheduleError as error:
            schedule_error = str(error)
        is_ready = database_ready and schedule_error is None
        content: dict[str, str] = {"status": "ready" if is_ready else "not_ready"}
        if database_error:
            content["database_error"] = database_error
        if schedule_error:
            content["schedule_error"] = schedule_error
        return JSONResponse(status_code=200 if is_ready else 503, content=content)

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

        try:
            schedule_text = await asyncio.to_thread(schedule_store.read_text)
            parse_schedule(schedule_text.text)
            schedule_status = {
                "status": "ready" if schedule_text.exists else "missing",
                "path": str(schedule_store.path),
                "revision": schedule_text.etag,
            }
        except ScheduleError as error:
            schedule_status = {
                "status": "invalid",
                "path": str(schedule_store.path),
                "error": str(error),
            }

        controller_status = (
            "ok"
            if database_ready
            and speech_result["status"] == "ready"
            and schedule_status["status"] == "ready"
            else "degraded"
        )
        return {
            "status": controller_status,
            "version": __version__,
            "announcements_enabled": announcements_enabled,
            "mode": mode,
            "timezone": timezone,
            "database": database_status,
            "schedule": schedule_status,
            "speech": speech_result,
        }

    @app.get("/api/v1/schedule")
    async def get_schedule() -> Response:
        try:
            current = await asyncio.to_thread(schedule_store.read_text)
        except ScheduleError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return Response(
            content=current.text,
            media_type="application/yaml",
            headers={
                "ETag": current.etag,
                "X-Schedule-Path": str(schedule_store.path),
            },
        )

    @app.put("/api/v1/schedule")
    async def put_schedule(request: Request) -> Response:
        try:
            text = (await request.body()).decode("utf-8")
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=422, detail="schedule must be UTF-8 text") from error
        try:
            saved = await asyncio.to_thread(
                schedule_store.save,
                text,
                request.headers.get("if-match"),
            )
        except ScheduleConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ScheduleError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except OSError as error:
            raise HTTPException(
                status_code=503,
                detail=f"could not write schedule: {error}",
            ) from error

        try:
            await database.sync_schedule(parse_schedule(saved.text))
        except Exception as error:
            logger.exception("Saved schedule could not be projected into the database")
            raise HTTPException(
                status_code=503,
                detail="schedule was saved but could not be activated yet",
            ) from error
        return Response(
            content=saved.text,
            media_type="application/yaml",
            headers={"ETag": saved.etag, "X-Schedule-Path": str(schedule_store.path)},
        )

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
