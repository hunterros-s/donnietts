import tomllib
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable


@dataclass(frozen=True)
class VoiceDefinition:
    id: str
    language: str
    reference_text: str
    reference_audio: Traversable


class VoiceRegistry:
    def __init__(self, voices: dict[str, VoiceDefinition]):
        self._voices = voices

    @classmethod
    def from_package(cls, package: str = "qwen_speech.voices") -> "VoiceRegistry":
        directory = resources.files(package)
        voices: dict[str, VoiceDefinition] = {}

        for config_file in directory.iterdir():
            if config_file.suffix != ".toml":
                continue

            config = tomllib.loads(config_file.read_text(encoding="utf-8"))
            voice_id = config["id"]
            if voice_id in voices:
                raise RuntimeError(f"Duplicate voice id: {voice_id}")

            audio = directory.joinpath(config["reference_audio"])
            if not audio.is_file():
                raise RuntimeError(f"Reference audio not found for voice {voice_id}: {audio.name}")

            voices[voice_id] = VoiceDefinition(
                id=voice_id,
                language=config["language"],
                reference_text=config["reference_text"].strip(),
                reference_audio=audio,
            )

        if not voices:
            raise RuntimeError(f"No voice definitions found in {package}")
        return cls(voices)

    def get(self, voice_id: str) -> VoiceDefinition | None:
        return self._voices.get(voice_id)

    def values(self) -> list[VoiceDefinition]:
        return list(self._voices.values())
