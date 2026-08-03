"""Location and weather context for rendering announcement templates."""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from donnietts.formatting import (
    date_to_words,
    number_to_words,
    percent_to_words,
    time_to_words,
    wind_to_words,
)
from donnietts.template_validation import LOCATION_FIELDS, WEATHER_FIELDS


logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "chime-announcement/0.1"
DEFAULT_DISPLAY_CITY = "edwardsburg"
DEFAULT_DISPLAY_STATE = "michigan"
DEFAULT_FETCH_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class ContextSettings:
    """Settings for external context lookups (location and weather)."""

    user_agent: str
    display_city: str
    display_state: str
    fetch_timeout_seconds: float

    @property
    def display_location(self) -> str:
        return f"{self.display_city}, {self.display_state}"

    @classmethod
    def from_environment(cls) -> "ContextSettings":
        return cls(
            user_agent=os.getenv("DONNIETTS_USER_AGENT", DEFAULT_USER_AGENT),
            display_city=os.getenv("DONNIETTS_DISPLAY_CITY", DEFAULT_DISPLAY_CITY),
            display_state=os.getenv("DONNIETTS_DISPLAY_STATE", DEFAULT_DISPLAY_STATE),
            fetch_timeout_seconds=float(
                os.getenv("DONNIETTS_FETCH_TIMEOUT_SECONDS", DEFAULT_FETCH_TIMEOUT_SECONDS)
            ),
        )


CONTEXT_SETTINGS = ContextSettings.from_environment()

WEATHER_CODES = {
    0: "clear",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "foggy",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorms",
    96: "thunderstorms with hail",
    99: "thunderstorms with hail",
}


async def _fetch_json(client: httpx.AsyncClient, url: str, settings: ContextSettings) -> dict[str, Any]:
    response = await client.get(
        url,
        headers={"User-Agent": settings.user_agent},
        timeout=settings.fetch_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


async def detect_coordinates(
    client: httpx.AsyncClient,
    settings: ContextSettings = CONTEXT_SETTINGS,
) -> tuple[float, float]:
    data = await _fetch_json(client, "https://ipapi.co/json/", settings)
    lat = data.get("latitude")
    lon = data.get("longitude")

    if lat is None or lon is None:
        raise RuntimeError(
            data.get("reason") or data.get("error") or "IP lookup did not return coordinates"
        )

    return float(lat), float(lon)


async def get_location(
    client: httpx.AsyncClient,
    settings: ContextSettings = CONTEXT_SETTINGS,
) -> dict[str, Any]:
    lat, lon = await detect_coordinates(client, settings)
    logger.info("Using display location: %s (%.4f, %.4f)", settings.display_location, lat, lon)
    return {
        "location": settings.display_location,
        "city": settings.display_city,
        "state": settings.display_state,
        "latitude": lat,
        "longitude": lon,
    }


async def get_weather(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    settings: ContextSettings = CONTEXT_SETTINGS,
) -> dict[str, Any]:
    query = urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "auto",
            "forecast_days": 1,
        }
    )
    data = await _fetch_json(client, f"https://api.open-meteo.com/v1/forecast?{query}", settings)
    current = data["current"]
    daily = data.get("daily", {})

    return {
        "weather_condition": WEATHER_CODES[current["weather_code"]],
        "current_temp": round(current["temperature_2m"]),
        "high_temp": round(daily["temperature_2m_max"][0]),
        "low_temp": round(daily["temperature_2m_min"][0]),
        "wind_speed": round(current["wind_speed_10m"]),
        "precip_chance": round(daily["precipitation_probability_max"][0]),
        "timezone": data["timezone"],
    }


async def build_location_context(
    client: httpx.AsyncClient,
    settings: ContextSettings = CONTEXT_SETTINGS,
) -> dict[str, Any]:
    location = await get_location(client, settings)
    return {
        "location": location["location"],
        "city": location["city"],
        "state": location["state"],
        "latitude": location["latitude"],
        "longitude": location["longitude"],
    }


async def build_weather_context(
    client: httpx.AsyncClient,
    location_context: dict[str, Any],
    settings: ContextSettings = CONTEXT_SETTINGS,
) -> dict[str, Any]:
    weather = await get_weather(
        client,
        location_context["latitude"],
        location_context["longitude"],
        settings,
    )
    return {
        "weather_condition": weather["weather_condition"],
        "current_temp": number_to_words(weather["current_temp"]),
        "high_temp": number_to_words(weather["high_temp"]),
        "low_temp": number_to_words(weather["low_temp"]),
        "wind": wind_to_words(weather["wind_speed"]),
        "wind_speed": number_to_words(weather["wind_speed"]),
        "precip_chance": percent_to_words(weather["precip_chance"]),
        "timezone": weather["timezone"],
    }


async def build_template_context(
    client: httpx.AsyncClient,
    fields: set[str],
    now: datetime,
    settings: ContextSettings = CONTEXT_SETTINGS,
) -> dict[str, Any]:
    context: dict[str, Any] = {}

    needs_location = bool(fields & LOCATION_FIELDS)
    needs_weather = bool(fields & WEATHER_FIELDS)

    if needs_location or needs_weather:
        location_context = await build_location_context(client, settings)
        context.update(location_context)

        if needs_weather:
            weather_context = await build_weather_context(client, location_context, settings)
            context.update(weather_context)

    context.update(
        {
            "time": time_to_words(now),
            "weekday": now.strftime("%A"),
            "date": date_to_words(now),
        }
    )
    return context
