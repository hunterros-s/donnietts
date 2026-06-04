from pathlib import Path

ASSETS_DIR = Path("assets")
CHIME_AUDIO = ASSETS_DIR / "startup3.mp3"
REFERENCE_AUDIO = ASSETS_DIR / "reference.wav"
OUTPUT_AUDIO = Path("announcement.wav")

DEFAULT_TEMPLATE = "It is {time} on {weekday}, {date}. In {location}, it is {weather_condition} and {current_temp} degrees."

QWEN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
REFERENCE_TEXT = "Attention. The time is ten fifteen A M. Current conditions are overcast. The temperature is sixty eight degrees."

USER_AGENT = "qwentts-chime-announcement/0.1"
