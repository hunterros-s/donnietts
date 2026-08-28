"""Read, validate, and atomically update the YAML announcement schedule."""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from donnietts.template_validation import InvalidTemplateError, validate_template


EMPTY_SCHEDULE = """version: 1
timezone: America/Detroit

defaults:
  lead_seconds: 300

announcements: []
"""
MISSING_ETAG = '"missing"'


class ScheduleError(ValueError):
    """The schedule cannot be read or validated."""


class ScheduleConflictError(RuntimeError):
    """The schedule changed after an editor loaded it."""


class ScheduleDefaultsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_seconds: int | None = Field(default=None, ge=0)
    lead_minutes: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_lead(self) -> "ScheduleDefaultsModel":
        if self.lead_seconds is not None and self.lead_minutes is not None:
            raise ValueError("defaults may specify lead_seconds or lead_minutes, not both")
        return self

    @property
    def resolved_lead_seconds(self) -> int:
        if self.lead_seconds is not None:
            return self.lead_seconds
        if self.lead_minutes is not None:
            return self.lead_minutes * 60
        return 300


class ScheduleAnnouncementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: str | None = None
    run_at: datetime | None = None
    template: str
    enabled: bool = True
    lead_seconds: int | None = Field(default=None, ge=0)
    lead_minutes: int | None = Field(default=None, ge=0)

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parse_daily_time(value)
        return value

    @field_validator("run_at", mode="before")
    @classmethod
    def require_timestamp_text(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("run_at must be an RFC 3339 timestamp")
        return value

    @field_validator("run_at")
    @classmethod
    def validate_run_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("run_at must include a UTC offset")
        return value.astimezone(UTC)

    @field_validator("template")
    @classmethod
    def validate_announcement_template(cls, value: str) -> str:
        try:
            return validate_template(value)
        except InvalidTemplateError as error:
            raise ValueError(str(error)) from error

    @model_validator(mode="after")
    def validate_shape(self) -> "ScheduleAnnouncementModel":
        if (self.time is None) == (self.run_at is None):
            raise ValueError("each announcement must specify exactly one of time or run_at")
        if self.lead_seconds is not None and self.lead_minutes is not None:
            raise ValueError("an announcement may specify lead_seconds or lead_minutes, not both")
        return self

    @property
    def kind(self) -> Literal["daily", "one_off"]:
        return "daily" if self.time is not None else "one_off"

    @property
    def minute_of_day(self) -> int | None:
        return parse_daily_time(self.time) if self.time is not None else None

    def resolved_lead_seconds(self, defaults: ScheduleDefaultsModel) -> int:
        if self.lead_seconds is not None:
            return self.lead_seconds
        if self.lead_minutes is not None:
            return self.lead_minutes * 60
        return defaults.resolved_lead_seconds


class ScheduleDocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    timezone: str = "America/Detroit"
    defaults: ScheduleDefaultsModel = Field(default_factory=ScheduleDefaultsModel)
    announcements: list[ScheduleAnnouncementModel]

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        return value

    @model_validator(mode="after")
    def validate_unique_occurrences(self) -> "ScheduleDocumentModel":
        daily: set[str] = set()
        one_off: set[datetime] = set()
        for announcement in self.announcements:
            if announcement.time is not None:
                if announcement.time in daily:
                    raise ValueError(f"daily time {announcement.time} is duplicated")
                daily.add(announcement.time)
            else:
                assert announcement.run_at is not None
                if announcement.run_at in one_off:
                    raise ValueError(
                        f"one-off time {announcement.run_at.isoformat()} is duplicated"
                    )
                one_off.add(announcement.run_at)
        return self


@dataclass(frozen=True)
class ScheduleAnnouncement:
    kind: Literal["daily", "one_off"]
    enabled: bool
    minute_of_day: int | None
    run_at_utc: datetime | None
    template: str
    lead_seconds: int

    @property
    def time(self) -> str | None:
        if self.minute_of_day is None:
            return None
        hour, minute = divmod(self.minute_of_day, 60)
        return f"{hour:02d}:{minute:02d}"

    @property
    def identity(self) -> tuple[str, int | datetime]:
        if self.kind == "daily":
            assert self.minute_of_day is not None
            return self.kind, self.minute_of_day
        assert self.run_at_utc is not None
        return self.kind, self.run_at_utc


@dataclass(frozen=True)
class Schedule:
    timezone: str
    announcements: tuple[ScheduleAnnouncement, ...]


@dataclass(frozen=True)
class ScheduleText:
    text: str
    etag: str
    exists: bool


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


def schedule_etag(text: str) -> str:
    return f'"{hashlib.sha256(text.encode("utf-8")).hexdigest()}"'


def _format_validation_error(error: ValidationError) -> str:
    first = error.errors(include_url=False)[0]
    location = ".".join(str(part) for part in first["loc"])
    message = first["msg"]
    return f"{location}: {message}" if location else message


def parse_schedule(text: str) -> Schedule:
    try:
        raw: Any = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = f"line {mark.line + 1}, column {mark.column + 1}: " if mark else ""
        problem = getattr(error, "problem", None) or str(error)
        raise ScheduleError(f"{location}{problem}") from error

    if raw is None:
        raise ScheduleError("schedule file is empty; use announcements: [] for an empty schedule")
    if not isinstance(raw, dict):
        raise ScheduleError("the top-level YAML value must be a mapping")

    try:
        document = ScheduleDocumentModel.model_validate(raw)
    except ValidationError as error:
        raise ScheduleError(_format_validation_error(error)) from error

    announcements = tuple(
        ScheduleAnnouncement(
            kind=item.kind,
            enabled=item.enabled,
            minute_of_day=item.minute_of_day,
            run_at_utc=item.run_at,
            template=item.template,
            lead_seconds=item.resolved_lead_seconds(document.defaults),
        )
        for item in document.announcements
    )
    return Schedule(timezone=document.timezone, announcements=announcements)


class ScheduleStore:
    """File-backed schedule with validation and compare-and-swap writes."""

    def __init__(self, path: Path):
        self.path = path
        self._write_lock = threading.Lock()

    def read_text(self) -> ScheduleText:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ScheduleText(EMPTY_SCHEDULE, MISSING_ETAG, False)
        except (OSError, UnicodeError) as error:
            raise ScheduleError(f"could not read {self.path}: {error}") from error
        return ScheduleText(text, schedule_etag(text), True)

    def load(self) -> Schedule:
        current = self.read_text()
        if not current.exists:
            raise ScheduleError(f"schedule file does not exist: {self.path}")
        return parse_schedule(current.text)

    def save(self, text: str, expected_etag: str | None) -> ScheduleText:
        schedule = parse_schedule(text)
        del schedule  # Validation is the point; preserve the submitted text exactly.

        with self._write_lock:
            current = self.read_text()
            if expected_etag is not None and expected_etag != current.etag:
                raise ScheduleConflictError(
                    "schedule changed after it was loaded; reload before saving"
                )

            self.path.parent.mkdir(parents=True, exist_ok=True)
            mode = self.path.stat().st_mode & 0o777 if current.exists else 0o644
            temporary_name: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary:
                    temporary_name = temporary.name
                    temporary.write(text)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.chmod(temporary_name, mode)
                os.replace(temporary_name, self.path)
                temporary_name = None
            finally:
                if temporary_name is not None:
                    Path(temporary_name).unlink(missing_ok=True)

            return ScheduleText(text, schedule_etag(text), True)
