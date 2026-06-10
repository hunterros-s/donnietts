from pathlib import Path

ASSETS_DIR = Path("assets")
CHIME_AUDIO = ASSETS_DIR / "startup3.mp3"
REFERENCE_AUDIO = ASSETS_DIR / "voice_sample.wav"
SCHEDULE_FILE = Path("schedule.yaml")

DEFAULT_TEMPLATE = "It is {time} on {weekday}, {date}. In {location}, it is {weather_condition} and {current_temp} degrees."

USER_AGENT = "chime-announcement/0.1"
