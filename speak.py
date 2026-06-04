import sys
from datetime import datetime
from string import Formatter
from zoneinfo import ZoneInfo

from audio import generate_speech, play_audio, prepend_chime
from config import DEFAULT_TEMPLATE
from formatting import date_to_words, number_to_words, percent_to_words, time_to_words, wind_to_words
from location import get_location
from weather import get_weather

LOCATION_FIELDS = {"location", "city", "state", "latitude", "longitude"}
WEATHER_FIELDS = {
    "weather_condition",
    "current_temp",
    "high_temp",
    "low_temp",
    "wind",
    "wind_speed",
    "precip_chance",
}


def template_fields(template):
    fields = set()
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return fields


def normalize_text(text):
    return " ".join(text.split())


def optional_number(value):
    return number_to_words(value) if value is not None else ""


def optional_percent(value):
    return percent_to_words(value) if value is not None else ""


def build_location_context():
    location = get_location()
    return {
        "location": location["location"],
        "city": location["city"],
        "state": location["state"],
        "latitude": location["latitude"],
        "longitude": location["longitude"],
    }


def build_weather_context(location_context):
    weather = get_weather(location_context["latitude"], location_context["longitude"])
    return {
        "weather_condition": weather["weather_condition"],
        "current_temp": number_to_words(weather["current_temp"]),
        "high_temp": optional_number(weather["high_temp"]),
        "low_temp": optional_number(weather["low_temp"]),
        "wind": wind_to_words(weather["wind_speed"]),
        "wind_speed": number_to_words(weather["wind_speed"]),
        "precip_chance": optional_percent(weather["precip_chance"]),
        "timezone": weather.get("timezone"),
    }


def build_template_context(template):
    fields = template_fields(template)
    context = {}
    now = datetime.now()

    needs_location = bool(fields & LOCATION_FIELDS)
    needs_weather = bool(fields & WEATHER_FIELDS)

    if needs_location or needs_weather:
        location_context = build_location_context()
        context.update(location_context)

        if needs_weather:
            weather_context = build_weather_context(location_context)
            context.update(weather_context)
            if weather_context.get("timezone"):
                now = datetime.now(ZoneInfo(weather_context["timezone"]))

    context.update(
        {
            "time": time_to_words(now),
            "weekday": now.strftime("%A"),
            "date": date_to_words(now),
        }
    )
    return context


def render_template(template):
    context = build_template_context(template)
    try:
        return normalize_text(template.format(**context))
    except KeyError as exc:
        available = sorted({"time", "weekday", "date"} | LOCATION_FIELDS | WEATHER_FIELDS)
        raise RuntimeError(f"Unknown template field {{{exc.args[0]}}}. Available fields: {', '.join(available)}") from exc


def main():
    template = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_TEMPLATE
    announcement = render_template(template)
    print(announcement)

    speech, sr = generate_speech(announcement)
    combined = prepend_chime(speech, sr)

    try:
        play_audio(combined, sr)
    except Exception as exc:
        raise SystemExit(f"Playback failed: {exc}") from exc


if __name__ == "__main__":
    main()
