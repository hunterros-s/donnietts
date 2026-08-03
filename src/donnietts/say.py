"""Render and speak a single announcement template immediately."""

import asyncio
from datetime import datetime

import httpx

from donnietts.audio import play_wav_bytes
from donnietts.context import CONTEXT_SETTINGS
from donnietts.rendering import render_template
from donnietts.settings import ControllerSettings
from donnietts.speech_client import OpenAICompatibleSpeechClient


async def say(settings: ControllerSettings, template: str) -> str:
    """Render the template, generate speech, play it, and return the text."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        rendered = await render_template(client, template, datetime.now(), CONTEXT_SETTINGS)
        speech_client = OpenAICompatibleSpeechClient(client, settings.speech)
        wav = await speech_client.generate_wav(rendered)
        await asyncio.to_thread(play_wav_bytes, wav)
    return rendered
