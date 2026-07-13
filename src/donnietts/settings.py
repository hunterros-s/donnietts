import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


DEFAULT_TTS_BASE_URL = "http://127.0.0.1:8101/v1"


def default_database_path() -> Path:
    state_home = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "donnietts" / "donnietts.sqlite3"


def derive_local_health_url(base_url: str) -> str | None:
    parsed = urlsplit(base_url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return None

    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        return None

    health_path = f"{path[:-3]}/health/ready"
    return urlunsplit((parsed.scheme, parsed.netloc, health_path, "", ""))


@dataclass(frozen=True)
class SpeechSettings:
    base_url: str
    api_key: str
    model: str
    voice: str
    instructions: str | None
    generation_timeout_seconds: float
    health_url: str | None
    status_timeout_seconds: float

    @classmethod
    def from_environment(cls) -> "SpeechSettings":
        base_url = os.getenv("TTS_BASE_URL", DEFAULT_TTS_BASE_URL).rstrip("/")
        configured_health_url = os.getenv("TTS_HEALTH_URL")
        if configured_health_url is None:
            health_url = derive_local_health_url(base_url)
        else:
            health_url = configured_health_url.strip() or None

        return cls(
            base_url=base_url,
            api_key=os.getenv("TTS_API_KEY", "local"),
            model=os.getenv("TTS_MODEL", "qwen3-tts-0.6b"),
            voice=os.getenv("TTS_VOICE", "announcer"),
            instructions=os.getenv("TTS_INSTRUCTIONS"),
            generation_timeout_seconds=float(os.getenv("TTS_TIMEOUT_SECONDS", "300")),
            health_url=health_url,
            status_timeout_seconds=float(os.getenv("TTS_STATUS_TIMEOUT_SECONDS", "2")),
        )


@dataclass(frozen=True)
class ControllerSettings:
    speech: SpeechSettings
    database_path: Path

    @classmethod
    def from_environment(cls) -> "ControllerSettings":
        configured_path = os.getenv("DONNIETTS_DB_PATH")
        database_path = Path(configured_path).expanduser() if configured_path else default_database_path()
        return cls(
            speech=SpeechSettings.from_environment(),
            database_path=database_path,
        )

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path}"
