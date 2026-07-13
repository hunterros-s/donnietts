from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request

from donnietts import __version__
from donnietts.settings import SpeechSettings
from donnietts.speech_status import get_speech_status


def create_app(settings: SpeechSettings | None = None) -> FastAPI:
    speech_settings = settings or SpeechSettings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.http_client = httpx.AsyncClient(timeout=speech_settings.status_timeout_seconds)
        try:
            yield
        finally:
            await app.state.http_client.aclose()

    app = FastAPI(title="DonnieTTS Controller", version=__version__, lifespan=lifespan)
    app.state.speech_settings = speech_settings

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/v1/status")
    async def status(request: Request) -> dict:
        speech = await get_speech_status(request.app.state.http_client, speech_settings)
        controller_status = "ok" if speech["status"] == "ready" else "degraded"
        return {
            "status": controller_status,
            "version": __version__,
            "speech": speech,
        }

    return app


app = create_app()
