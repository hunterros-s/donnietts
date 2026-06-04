import sys
from datetime import datetime

from audio import play_audio, prepend_chime
from config import DEFAULT_TEMPLATE
from template import render_template
from tts import QwenTTSProvider


def main():
    template = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_TEMPLATE
    announcement = render_template(template, datetime.now())
    print(announcement)

    tts = QwenTTSProvider()
    speech, sr = tts.generate_speech(announcement)
    combined = prepend_chime(speech, sr)

    try:
        play_audio(combined, sr)
    except Exception as exc:
        raise SystemExit(f"Playback failed: {exc}") from exc


if __name__ == "__main__":
    main()
