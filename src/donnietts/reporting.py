"""Plain-text reporting used by the donnietts CLI."""

from donnietts.announcement_runs import AnnouncementRunSnapshot
from donnietts.database import (
    AnnouncementSnapshot,
    ApplicationSettingsSnapshot,
    Database,
)
from donnietts.settings import ControllerSettings


def _one_line(text: str, width: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= width:
        return normalized
    return normalized[: width - 1] + "…"


def _schedule_header(settings: ApplicationSettingsSnapshot) -> list[str]:
    return [
        f"Announcements are {settings.mode} (timezone: {settings.timezone})",
        "",
        " ID  KIND      WHEN                 LEAD   REV  ENABLED  TEMPLATE",
        "---  --------  -------------------  -----  ---  -------  --------",
    ]


def _schedule_row(announcement: AnnouncementSnapshot) -> str:
    when = announcement.time
    if when is None and announcement.run_at_utc is not None:
        when = announcement.run_at_utc.strftime("%Y-%m-%d %H:%M %Z")
    return (
        f"{announcement.id:>3}  {announcement.kind:<8} {when:<19} "
        f"{announcement.lead_seconds:>4}s {announcement.revision:>2}  "
        f"{'yes' if announcement.enabled else 'no':<5} "
        f"{_one_line(announcement.template, 64)}"
    )


async def schedule_text(settings: ControllerSettings) -> str:
    database = Database(settings)
    try:
        await database.initialize()
        application_settings = await database.get_application_settings()
        announcements = await database.list_announcements()
    finally:
        await database.close()

    lines = _schedule_header(application_settings)
    if not announcements:
        lines.append("No announcements configured.")
        return "\n".join(lines)

    lines.extend(_schedule_row(item) for item in announcements)
    return "\n".join(lines)


def _runs_row(run: AnnouncementRunSnapshot) -> str:
    scheduled = run.scheduled_for_utc.strftime("%Y-%m-%d %H:%M UTC")
    announcement = str(run.announcement_id) if run.announcement_id is not None else "-"
    row = (
        f"{run.id:>3}  {run.status:<11} {scheduled:<20} "
        f"{announcement:>4}"
    )
    detail = _one_line(run.outcome_reason or run.error or "", 40)
    if detail:
        row += f"  {detail}"
    return row


async def runs_text(settings: ControllerSettings, *, limit: int = 20) -> str:
    database = Database(settings)
    try:
        await database.initialize()
        runs = await database.runs.list_all()
    finally:
        await database.close()

    runs = sorted(runs, key=lambda run: run.scheduled_for_utc, reverse=True)[:limit]
    if not runs:
        return "No announcement runs yet."

    lines = [
        " ID  STATUS       SCHEDULED (UTC)      ANN  DETAIL",
        "---  -----------  -------------------  ---  ------",
        *(_runs_row(run) for run in runs),
    ]
    return "\n".join(lines)
