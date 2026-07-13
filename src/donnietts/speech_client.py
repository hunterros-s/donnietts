import httpx

from donnietts.settings import SpeechSettings


class OpenAICompatibleSpeechClient:
    def __init__(self, client: httpx.AsyncClient, settings: SpeechSettings):
        self.client = client
        self.settings = settings

    async def generate_wav(self, text: str) -> bytes:
        request: dict[str, str] = {
            "model": self.settings.model,
            "input": text,
            "voice": self.settings.voice,
            "response_format": "wav",
        }
        if self.settings.instructions:
            request["instructions"] = self.settings.instructions

        headers = (
            {"Authorization": f"Bearer {self.settings.api_key}"}
            if self.settings.api_key
            else {}
        )
        response = await self.client.post(
            f"{self.settings.base_url}/audio/speech",
            headers=headers,
            json=request,
            timeout=self.settings.generation_timeout_seconds,
        )
        response.raise_for_status()
        return response.content
