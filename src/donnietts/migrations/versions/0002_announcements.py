"""Create announcements and migrate the legacy daily schedule.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_DAILY_SCHEDULE = [
    (
        480,
        "Hi Donnie. Good morning. It is {time} on {weekday}, {date}. In {location}, the morning is "
        "{weather_condition} and {current_temp} degrees. The forecast high is {high_temp} degrees, the low is "
        "{low_temp} degrees, wind is {wind}, and precipitation chance is {precip_chance}.",
    ),
    (
        540,
        "Hi Donnie. Nine o'clock update for {weekday}, {date}. {location} is currently {current_temp} degrees "
        "with {weather_condition} conditions. Today's range is {low_temp} to {high_temp} degrees, with wind at "
        "{wind}.",
    ),
    (
        600,
        "Hi Donnie. It is {time}. Current weather in {location}: {weather_condition}, {current_temp} degrees, "
        "wind {wind}. The chance of precipitation today is {precip_chance}, with a high near {high_temp} degrees.",
    ),
    (
        660,
        "Hi Donnie. Late morning briefing for {weekday}, {date}. In {location}, it is {current_temp} degrees and "
        "{weather_condition}. The forecast still shows a high of {high_temp} degrees and a low of {low_temp} degrees.",
    ),
    (
        720,
        "Hi Donnie. Good afternoon. It is noon on {weekday}, {date}. Conditions in {location} are "
        "{weather_condition}, with the temperature at {current_temp} degrees. Wind is {wind}, and precipitation "
        "chance is {precip_chance}.",
    ),
    (
        780,
        "Hi Donnie. One o'clock report. {location} is at {current_temp} degrees under {weather_condition} skies. "
        "Today is expected to top out near {high_temp} degrees and fall to {low_temp} degrees.",
    ),
    (
        840,
        "Hi Donnie. It is {time} on {weekday}, {date}. The afternoon reading in {location} is {current_temp} "
        "degrees with {weather_condition} conditions. Wind is {wind}; precipitation chance remains {precip_chance}.",
    ),
    (
        900,
        "Hi Donnie. Three o'clock update. In {location}, the temperature is {current_temp} degrees and the "
        "weather is {weather_condition}. The daily high is {high_temp} degrees, with tonight's low near "
        "{low_temp} degrees.",
    ),
    (
        960,
        "Hi Donnie. Four o'clock briefing for {weekday}, {date}. Current conditions in {location}: "
        "{weather_condition}, {current_temp} degrees. Wind is {wind}, and the chance of precipitation is "
        "{precip_chance}.",
    ),
    (
        1020,
        "Hi Donnie. It is {time}. In {location}, evening conditions are beginning at {current_temp} degrees with "
        "{weather_condition} weather. Today's high is {high_temp} degrees, and the low tonight is expected to be "
        "{low_temp} degrees.",
    ),
    (
        1080,
        "Hi Donnie. Good evening. Six o'clock weather for {location}. It is currently {current_temp} degrees and "
        "{weather_condition}. Wind is {wind}, with precipitation chance at {precip_chance}.",
    ),
    (
        1140,
        "Hi Donnie. Seven o'clock check-in on {weekday}, {date}. {location} is reporting {weather_condition} "
        "conditions and {current_temp} degrees. The overnight low is expected to be {low_temp} degrees.",
    ),
    (
        1200,
        "Hi Donnie. It is {time}. The evening forecast in {location} is {weather_condition}, currently "
        "{current_temp} degrees. Wind is {wind}, and precipitation chance is {precip_chance}.",
    ),
    (
        1260,
        "Hi Donnie. Good night. Final briefing for {weekday}, {date}. In {location}, it is {current_temp} "
        "degrees with {weather_condition} conditions. Tonight's low is expected to be {low_temp} degrees.",
    ),
]


def upgrade() -> None:
    announcements = op.create_table(
        "announcements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("minute_of_day", sa.Integer(), nullable=True),
        sa.Column("run_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("lead_seconds", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.CheckConstraint("kind IN ('daily', 'one_off')", name="ck_announcements_kind"),
        sa.CheckConstraint("lead_seconds >= 0", name="ck_announcements_lead_seconds"),
        sa.CheckConstraint("revision >= 1", name="ck_announcements_revision"),
        sa.CheckConstraint(
            "(kind = 'daily' AND minute_of_day BETWEEN 0 AND 1439 AND run_at_utc IS NULL) "
            "OR (kind = 'one_off' AND minute_of_day IS NULL AND run_at_utc IS NOT NULL)",
            name="ck_announcements_schedule_shape",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_announcements_kind_enabled",
        "announcements",
        ["kind", "enabled"],
        unique=False,
    )
    op.bulk_insert(
        announcements,
        [
            {
                "kind": "daily",
                "enabled": True,
                "minute_of_day": minute_of_day,
                "run_at_utc": None,
                "template": template,
                "lead_seconds": 300,
                "revision": 1,
            }
            for minute_of_day, template in LEGACY_DAILY_SCHEDULE
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_announcements_kind_enabled", table_name="announcements")
    op.drop_table("announcements")
