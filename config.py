from pathlib import Path

from donnietts.settings import SpeechSettings

ASSETS_DIR = Path("assets")
CHIME_AUDIO = ASSETS_DIR / "startup3.mp3"
SOUND_OFF_AUDIO = ASSETS_DIR / "sound_off.mp3"
SCHEDULE_FILE = Path("schedule.yaml")

SPEECH_SETTINGS = SpeechSettings.from_environment()
TTS_BASE_URL = SPEECH_SETTINGS.base_url
TTS_API_KEY = SPEECH_SETTINGS.api_key
TTS_MODEL = SPEECH_SETTINGS.model
TTS_VOICE = SPEECH_SETTINGS.voice
TTS_INSTRUCTIONS = SPEECH_SETTINGS.instructions
TTS_TIMEOUT_SECONDS = SPEECH_SETTINGS.generation_timeout_seconds

DEFAULT_TEMPLATE = (
    "Hi Donnie. This is your current briefing for {weekday}, {date}. The time is {time}. "
    "In {location}, conditions are currently {weather_condition}, with a temperature of {current_temp} degrees. "
    "Today's forecast calls for a high near {high_temp} degrees and a low near {low_temp} degrees. "
    "Winds are at {wind}, and the chance of precipitation today is {precip_chance}. "
    "Use this update to stay aware of the day and plan accordingly."
)

USER_AGENT = "chime-announcement/0.1"
