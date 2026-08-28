#!/usr/bin/env python3
"""One-time export of the SQLite announcement schedule to YAML.

Run this before enabling the YAML-backed scheduler if the database contains the
schedule you want to keep. The script only reads SQLite and refuses to replace
an existing output file unless --force is supplied.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import yaml


class BlockStringDumper(yaml.SafeDumper):
    pass


def represent_string(dumper: yaml.SafeDumper, value: str):
    style = ">" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


BlockStringDumper.add_representer(str, represent_string)


def default_database_path() -> Path:
    configured = os.getenv("DONNIETTS_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    state_home = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "donnietts" / "donnietts.sqlite3"


def default_schedule_path() -> Path:
    configured = os.getenv("DONNIETTS_SCHEDULE_PATH")
    return Path(configured).expanduser() if configured else Path("schedule.yaml")


def utc_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def export(database_path: Path) -> dict:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        settings = connection.execute(
            "SELECT timezone FROM application_settings WHERE id = 1"
        ).fetchone()
        if settings is None:
            raise SystemExit("database has no application settings row")
        rows = connection.execute(
            """
            SELECT kind, enabled, minute_of_day, run_at_utc, template, lead_seconds
            FROM announcements
            ORDER BY kind, minute_of_day, run_at_utc, id
            """
        ).fetchall()

    announcements = []
    for row in rows:
        item = {
            "enabled": bool(row["enabled"]),
            "lead_seconds": row["lead_seconds"],
        }
        if row["kind"] == "daily":
            hour, minute = divmod(row["minute_of_day"], 60)
            item["time"] = f"{hour:02d}:{minute:02d}"
        else:
            item["run_at"] = utc_timestamp(row["run_at_utc"])
        item["template"] = row["template"]
        announcements.append(item)

    return {
        "version": 1,
        "timezone": settings["timezone"],
        "defaults": {"lead_seconds": 300},
        "announcements": announcements,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument("--output", type=Path, default=default_schedule_path())
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.database.exists():
        raise SystemExit(f"database does not exist: {args.database}")
    if args.output.exists() and not args.force:
        raise SystemExit(f"output already exists: {args.output} (use --force to replace it)")

    document = export(args.database)
    text = yaml.dump(
        document,
        Dumper=BlockStringDumper,
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"Exported {len(document['announcements'])} announcements to {args.output}")


if __name__ == "__main__":
    main()
