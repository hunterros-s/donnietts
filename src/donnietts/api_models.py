from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from donnietts.database import AnnouncementSnapshot, ApplicationSettingsSnapshot
from donnietts.template_validation import InvalidTemplateError, validate_template


def parse_daily_time(value: str) -> int:
    parts = value.split(":")
    invalid_part = any(
        len(part) != 2 or not part.isascii() or not part.isdigit() for part in parts
    )
    if len(parts) != 2 or invalid_part:
        raise ValueError("time must use HH:MM in 24-hour format")
    hour, minute = (int(part) for part in parts)
    if hour > 23 or minute > 59:
        raise ValueError("time must use HH:MM in 24-hour format")
    return hour * 60 + minute


def normalize_future_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("run_at must include a UTC offset")
    value = value.astimezone(UTC)
    if value <= datetime.now(UTC):
        raise ValueError("run_at must be in the future")
    return value


def normalize_template(value: str) -> str:
    try:
        return validate_template(value)
    except InvalidTemplateError as error:
        raise ValueError(str(error)) from error


class AnnouncementCreateBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: str
    enabled: bool = True
    lead_seconds: int = Field(default=300, ge=0)

    @field_validator("template")
    @classmethod
    def validate_announcement_template(cls, value: str) -> str:
        return normalize_template(value)


class DailyAnnouncementCreate(AnnouncementCreateBase):
    time: str

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parse_daily_time(value)
        return value


class OneOffAnnouncementCreate(AnnouncementCreateBase):
    run_at: datetime

    @field_validator("run_at")
    @classmethod
    def validate_run_at(cls, value: datetime) -> datetime:
        return normalize_future_time(value)


class AnnouncementPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    enabled: bool | None = None
    time: str | None = None
    run_at: datetime | None = None
    template: str | None = None
    lead_seconds: int | None = Field(default=None, ge=0)

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("time may not be null")
        parse_daily_time(value)
        return value

    @field_validator("run_at")
    @classmethod
    def validate_run_at(cls, value: datetime | None) -> datetime:
        if value is None:
            raise ValueError("run_at may not be null")
        return normalize_future_time(value)

    @field_validator("template")
    @classmethod
    def validate_announcement_template(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("template may not be null")
        return normalize_template(value)

    @model_validator(mode="after")
    def require_update(self) -> "AnnouncementPatch":
        update_fields = self.model_fields_set - {"expected_revision"}
        if not update_fields:
            raise ValueError("at least one announcement field must be provided")
        if any(getattr(self, field) is None for field in update_fields):
            raise ValueError("announcement fields may not be null")
        return self


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
