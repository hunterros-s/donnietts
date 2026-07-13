from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from donnietts.database import AnnouncementSnapshot, ApplicationSettingsSnapshot


class AnnouncementResponse(BaseModel):
    id: int
    kind: Literal["daily", "one_off"]
    enabled: bool
    time: str | None
    run_at_utc: datetime | None
    template: str
    lead_seconds: int
    revision: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_snapshot(cls, snapshot: AnnouncementSnapshot) -> "AnnouncementResponse":
        return cls(
            id=snapshot.id,
            kind=snapshot.kind,
            enabled=snapshot.enabled,
            time=snapshot.time,
            run_at_utc=snapshot.run_at_utc,
            template=snapshot.template,
            lead_seconds=snapshot.lead_seconds,
            revision=snapshot.revision,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
        )


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
