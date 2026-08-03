from pathlib import Path

from donnietts.rendering import DEFAULT_TEMPLATE
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

USER_AGENT = "chime-announcement/0.1"
