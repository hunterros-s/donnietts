import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
import yaml

from audio import play_audio, prepend_chime
from config import SCHEDULE_FILE
from template import render_template
from tts import TTSProvider, create_tts_provider


@dataclass
class ScheduledAnnouncement:
    time: str
    template: str


def load_schedule():
    with open(SCHEDULE_FILE) as file:
        config = yaml.safe_load(file)

    lead_minutes = config["defaults"]["lead_minutes"]
    announcements = [
        ScheduledAnnouncement(time=item["time"], template=item["template"])
        for item in config["announcements"]
    ]
    return lead_minutes, announcements


def parse_time_for_day(time_string, day):
    hour, minute = map(int, time_string.split(":"))
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def next_occurrence(announcement, now):
    today = parse_time_for_day(announcement.time, now)
    if today > now:
        return today
    return today + timedelta(days=1)


def next_job(announcements, lead_minutes):
    now = datetime.now()
    lead = timedelta(minutes=lead_minutes)

    jobs = []
    for announcement in announcements:
        speak_at = next_occurrence(announcement, now)
        generate_at = speak_at - lead
        jobs.append((max(generate_at, now), speak_at, announcement))

    return min(jobs, key=lambda job: (job[0], job[1]))


async def sleep_until(target):
    seconds = (target - datetime.now()).total_seconds()
    if seconds > 0:
        await asyncio.sleep(seconds)


async def generate_announcement(
    client: httpx.AsyncClient,
    tts: TTSProvider,
    announcement: ScheduledAnnouncement,
    speak_at: datetime,
):
    text = await render_template(client, announcement.template, speak_at)
    print(text)

    speech, sample_rate = await tts.generate_speech(text)
    combined = await asyncio.to_thread(prepend_chime, speech, sample_rate)
    return combined, sample_rate


async def run_daemon() -> None:
    lead_minutes, announcements = load_schedule()
    async with httpx.AsyncClient() as client:
        tts = create_tts_provider(client)

        while True:
            generate_at, speak_at, announcement = next_job(announcements, lead_minutes)
            print(
                f"Next announcement: {announcement.time}; "
                f"generating at {generate_at}; speaking at {speak_at}"
            )

            await sleep_until(generate_at)
            audio, sample_rate = await generate_announcement(
                client,
                tts,
                announcement,
                speak_at,
            )

            await sleep_until(speak_at)
            try:
                await asyncio.to_thread(play_audio, audio, sample_rate)
            except Exception as error:
                raise RuntimeError(f"Playback failed: {error}") from error


def main() -> None:
    try:
        asyncio.run(run_daemon())
    except Exception as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
