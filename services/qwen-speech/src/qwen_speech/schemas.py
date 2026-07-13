from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


AudioFormat = Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]
StreamFormat = Literal["audio", "sse"]


class CustomVoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)


class CreateSpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    input: str = Field(min_length=1, max_length=4096)
    voice: Annotated[str, Field(min_length=1)] | CustomVoice
    instructions: str | None = Field(default=None, max_length=4096)
    response_format: AudioFormat = "mp3"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    stream_format: StreamFormat = "audio"

    @property
    def voice_id(self) -> str:
        return self.voice if isinstance(self.voice, str) else self.voice.id


class ModelObject(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str = "qwen-speech"


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelObject]
