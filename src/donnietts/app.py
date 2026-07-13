import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from donnietts import __version__
from donnietts.api_models import (
    AnnouncementResponse,
    ApplicationSettingsPatch,
    ApplicationSettingsResponse,
)
from donnietts.database import ApplicationSettingsSnapshot, Database
from donnietts.settings import ControllerSettings
from donnietts.speech_status import get_speech_status


logger = logging.getLogger(__name__)


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

    return app


app = create_app()
