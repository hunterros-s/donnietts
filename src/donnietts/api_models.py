from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from donnietts.announcement_runs import AnnouncementRunSnapshot
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


class AnnouncementRunResponse(BaseModel):
    id: int
    announcement_id: int | None
    announcement_revision: int
    announcement_kind: Literal["daily", "one_off"]
    scheduled_for_utc: datetime
    generation_due_at_utc: datetime
    status: str
    template_snapshot: str
    rendered_text: str | None
    audio_path: str | None
    error: str | None
    outcome_reason: str | None
    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None
    playback_started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_snapshot(cls, snapshot: AnnouncementRunSnapshot) -> "AnnouncementRunResponse":
        return cls(
            id=snapshot.id,
            announcement_id=snapshot.announcement_id,
            announcement_revision=snapshot.announcement_revision,
            announcement_kind=snapshot.announcement_kind,
            scheduled_for_utc=snapshot.scheduled_for_utc,
            generation_due_at_utc=snapshot.generation_due_at_utc,
            status=snapshot.status,
            template_snapshot=snapshot.template_snapshot,
            rendered_text=snapshot.rendered_text,
            audio_path=snapshot.audio_path,
            error=snapshot.error,
            outcome_reason=snapshot.outcome_reason,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
            ready_at=snapshot.ready_at,
            playback_started_at=snapshot.playback_started_at,
            finished_at=snapshot.finished_at,
        )


class ApplicationSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    announcements_enabled: bool


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
