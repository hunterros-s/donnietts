from typing import Any

import httpx

from donnietts.settings import SpeechSettings


def status_payload(settings: SpeechSettings, status: str, *, error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "base_url": settings.base_url,
        "model": settings.model,
        "voice": settings.voice,
    }
    if error:
        payload["error"] = error
    return payload


async def get_speech_status(client: httpx.AsyncClient, settings: SpeechSettings) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}

    if settings.health_url:
        try:
            response = await client.get(settings.health_url)
        except httpx.RequestError as error:
            return status_payload(settings, "unavailable", error=str(error))

        if response.status_code == 503:
            return status_payload(settings, "warming")
        if response.status_code not in {200, 404, 405}:
            return status_payload(
                settings,
                "unavailable",
                error=f"Health check returned HTTP {response.status_code}",
            )

    try:
        response = await client.get(f"{settings.base_url}/models", headers=headers)
    except httpx.RequestError as error:
        return status_payload(settings, "unavailable", error=str(error))

    if response.status_code != 200:
        return status_payload(
            settings,
            "unavailable",
            error=f"Model discovery returned HTTP {response.status_code}",
        )

    try:
        data = response.json()["data"]
        model_ids = {item["id"] for item in data}
    except (KeyError, TypeError, ValueError):
        return status_payload(settings, "unavailable", error="Model discovery returned an invalid response")

    if settings.model not in model_ids:
        return status_payload(
            settings,
            "misconfigured",
            error=f"Configured model is not available: {settings.model}",
        )

    return status_payload(settings, "ready")
