import asyncio
import sys
from datetime import datetime

import httpx

from audio import play_audio, prepend_chime
from config import DEFAULT_TEMPLATE
from template import render_template
from tts import create_tts_provider


async def speak(template: str) -> None:
    async with httpx.AsyncClient() as client:
        announcement = await render_template(client, template, datetime.now())
        print(announcement)

        tts = create_tts_provider(client)
        speech, sample_rate = await tts.generate_speech(announcement)
        combined = await asyncio.to_thread(prepend_chime, speech, sample_rate)

        try:
            await asyncio.to_thread(play_audio, combined, sample_rate)
        except Exception as error:
            raise RuntimeError(f"Playback failed: {error}") from error


def main() -> None:
    template = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_TEMPLATE
    try:
        asyncio.run(speak(template))
    except Exception as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
