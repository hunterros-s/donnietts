import hmac
import os
import uuid
from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from qwen_speech.backend import FakeSpeechBackend, SpeechBackend, SpeechBackendError
from qwen_speech.schemas import CreateSpeechRequest, ModelList


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        error_type: str,
        param: str | None = None,
        code: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.error_type = error_type
        self.param = param
        self.code = code


def error_response(error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "message": error.message,
                "type": error.error_type,
                "param": error.param,
                "code": error.code,
            }
        },
    )


def create_app(*, backend: SpeechBackend | None = None, api_key: str | None = None) -> FastAPI:
    speech_backend = backend or FakeSpeechBackend()
    configured_api_key = api_key if api_key is not None else os.getenv("QWEN_SPEECH_API_KEY")

    app = FastAPI(title="Qwen Speech Service", version="0.1.0")
    app.state.speech_backend = speech_backend

    async def authorize(authorization: str | None = Header(default=None)) -> None:
        if not configured_api_key:
            return
        scheme, _, supplied_key = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(supplied_key, configured_api_key):
            raise ApiError(
                401,
                "Invalid authentication credentials",
                error_type="authentication_error",
                code="invalid_api_key",
            )

    protected = [Depends(authorize)]

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
        return error_response(error)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
        detail = error.errors()[0]
        location = detail.get("loc", ())
        param = str(location[-1]) if location else None
        return error_response(
            ApiError(
                400,
                detail.get("msg", "Invalid request"),
                error_type="invalid_request_error",
                param=param,
                code="invalid_request",
            )
        )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        status_code = 200 if speech_backend.ready else 503
        status = "ready" if speech_backend.ready else "not_ready"
        return JSONResponse(status_code=status_code, content={"status": status})

    @app.get("/v1/models", response_model=ModelList, dependencies=protected)
    async def list_models() -> ModelList:
        return ModelList(data=speech_backend.models())

    @app.post("/v1/audio/speech", dependencies=protected)
    async def create_speech(payload: CreateSpeechRequest) -> Response:
        try:
            audio = await speech_backend.synthesize(payload)
        except SpeechBackendError as error:
            raise ApiError(
                400,
                error.message,
                error_type="invalid_request_error",
                param=error.param,
                code=error.code,
            ) from error

        return Response(
            content=audio.content,
            media_type=audio.media_type,
            headers={"x-request-id": f"req_{uuid.uuid4().hex}"},
        )

    return app


app = create_app()
