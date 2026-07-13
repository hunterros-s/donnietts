from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from donnietts.database import ApplicationSettingsSnapshot


class ApplicationSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    announcements_enabled: bool


class ApplicationSettingsResponse(BaseModel):
    announcements_enabled: bool
    mode: Literal["active", "paused"]
    updated_at: datetime

    @classmethod
    def from_snapshot(cls, snapshot: ApplicationSettingsSnapshot) -> "ApplicationSettingsResponse":
        return cls(
            announcements_enabled=snapshot.announcements_enabled,
            mode=snapshot.mode,
            updated_at=snapshot.updated_at,
        )
