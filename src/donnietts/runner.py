"""Run the controller API and announcement worker in a single process."""

import asyncio
import logging

import httpx
import uvicorn

from donnietts.database import Database
from donnietts.settings import ControllerSettings
from donnietts.worker import AnnouncementWorker


def configure_logging() -> None:
    """Route application and uvicorn logs to stderr at INFO level."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.INFO)
    # httpx logs every request at INFO; keep daemon logs focused.
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def run_controller(
    settings: ControllerSettings,
    *,
    host: str,
    port: int,
    poll_interval_seconds: float,
) -> None:
    """Serve the controller API and run the announcement worker together.

    The API and the worker share one event loop and one SQLite database. A
    shutdown signal stops the API first (uvicorn handles SIGINT/SIGTERM);
    the worker is then cancelled and the database closed before exit. If
    either half fails fatally, the other is stopped and the error re-raised
    so the supervisor can restart the whole service.
    """
    database = Database(settings)
    await database.initialize()

    config = uvicorn.Config(
        "donnietts.app:app",
        host=host,
        port=port,
        workers=1,
        log_config=None,
    )
    server = uvicorn.Server(config)

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http_client:
        worker = AnnouncementWorker(
            database,
            speech_settings=settings.speech,
            http_client=http_client,
            audio_dir=settings.audio_dir,
            poll_interval_seconds=poll_interval_seconds,
        )
        api_task = asyncio.create_task(server.serve())
        worker_task = asyncio.create_task(worker.run())
        try:
            await asyncio.wait(
                {api_task, worker_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (worker_task, api_task):
                if not task.done():
                    task.cancel()
            results = await asyncio.gather(api_task, worker_task, return_exceptions=True)
            await database.close()

    for result in results:
        if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
            raise result
