import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import yaml

from audio import play_audio, prepend_chime
from config import SCHEDULE_FILE
from template import render_template
from tts import QwenTTSProvider


@dataclass
class ScheduledAnnouncement:
    time: str
    template: str


def load_schedule():
    with open(SCHEDULE_FILE) as f:
        config = yaml.safe_load(f)

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


def sleep_until(target):
    seconds = (target - datetime.now()).total_seconds()
    if seconds > 0:
        time.sleep(seconds)


def generate_announcement(tts, announcement, speak_at):
    text = render_template(announcement.template, speak_at)
    print(text)

    speech, sr = tts.generate_speech(text)
    return prepend_chime(speech, sr), sr


def main():
    lead_minutes, announcements = load_schedule()
    tts = QwenTTSProvider()

    while True:
        generate_at, speak_at, announcement = next_job(announcements, lead_minutes)
        print(f"Next announcement: {announcement.time}; generating at {generate_at}; speaking at {speak_at}")

        sleep_until(generate_at)
        audio, sr = generate_announcement(tts, announcement, speak_at)

        sleep_until(speak_at)
        try:
            play_audio(audio, sr)
        except Exception as exc:
            raise SystemExit(f"Playback failed: {exc}") from exc


if __name__ == "__main__":
    main()
