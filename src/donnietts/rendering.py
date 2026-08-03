"""Render announcement templates with location, weather, and time context."""

from datetime import datetime
from string import Formatter

import httpx

from donnietts.context import CONTEXT_SETTINGS, ContextSettings, build_template_context
from donnietts.template_validation import AVAILABLE_FIELDS


DEFAULT_TEMPLATE = (
    "Hi Donnie. This is your current briefing for {weekday}, {date}. The time is {time}. "
    "In {location}, conditions are currently {weather_condition}, with a temperature of {current_temp} degrees. "
    "Today's forecast calls for a high near {high_temp} degrees and a low near {low_temp} degrees. "
    "Winds are at {wind}, and the chance of precipitation today is {precip_chance}. "
    "Use this update to stay aware of the day and plan accordingly."
)


def template_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return fields


def normalize_text(text: str) -> str:
    return " ".join(text.split())


async def render_template(
    client: httpx.AsyncClient,
    template: str,
    now: datetime,
    settings: ContextSettings = CONTEXT_SETTINGS,
) -> str:
    fields = template_fields(template)
    context = await build_template_context(client, fields, now, settings)
    try:
        return normalize_text(template.format(**context))
    except KeyError as exc:
        available = ", ".join(sorted(AVAILABLE_FIELDS))
        raise RuntimeError(
            f"Unknown template field {{{exc.args[0]}}}. Available fields: {available}"
        ) from exc
