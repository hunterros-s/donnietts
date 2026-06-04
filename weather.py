from urllib.parse import urlencode

from utils import fetch_json

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


def get_weather(lat, lon):
    query = urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "auto",
        }
    )
    data = fetch_json(f"https://api.open-meteo.com/v1/forecast?{query}")
    current = data["current"]

    return {
        "temperature": round(current["temperature_2m"]),
        "condition": WEATHER_CODES.get(current["weather_code"], "unknown conditions"),
        "wind_speed": current["wind_speed_10m"],
        "timezone": data.get("timezone"),
    }
