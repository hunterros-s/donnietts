from pathlib import Path

ASSETS_DIR = Path("assets")
CHIME_AUDIO = ASSETS_DIR / "startup3.mp3"
SOUND_OFF_AUDIO = ASSETS_DIR / "sound_off.mp3"
REFERENCE_AUDIO = ASSETS_DIR / "voice_sample.wav"
SCHEDULE_FILE = Path("schedule.yaml")

DEFAULT_TEMPLATE = (
    "This is your current briefing for {weekday}, {date}. The time is {time}. "
    "In {location}, conditions are currently {weather_condition}, with a temperature of {current_temp} degrees. "
    "Today's forecast calls for a high near {high_temp} degrees and a low near {low_temp} degrees. "
    "Winds are at {wind}, and the chance of precipitation today is {precip_chance}. "
    "Use this update to stay aware of the day and plan accordingly."
)

USER_AGENT = "chime-announcement/0.1"
