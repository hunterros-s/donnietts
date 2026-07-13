from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

    announcements_enabled: bool | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        return value

    @model_validator(mode="after")
    def require_update(self) -> "ApplicationSettingsPatch":
        if self.announcements_enabled is None and self.timezone is None:
            raise ValueError("at least one setting must be provided")
        return self


class ApplicationSettingsResponse(BaseModel):
    announcements_enabled: bool
    mode: Literal["active", "paused"]
    timezone: str
    updated_at: datetime

    @classmethod
    def from_snapshot(cls, snapshot: ApplicationSettingsSnapshot) -> "ApplicationSettingsResponse":
        return cls(
            announcements_enabled=snapshot.announcements_enabled,
            mode=snapshot.mode,
            timezone=snapshot.timezone,
            updated_at=snapshot.updated_at,
        )
