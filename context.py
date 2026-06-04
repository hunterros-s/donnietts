from formatting import date_to_words, number_to_words, percent_to_words, time_to_words, wind_to_words
from location import get_location
from weather import get_weather

TIME_FIELDS = {"time", "weekday", "date"}
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

AVAILABLE_FIELDS = TIME_FIELDS | LOCATION_FIELDS | WEATHER_FIELDS


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
        "high_temp": number_to_words(weather["high_temp"]),
        "low_temp": number_to_words(weather["low_temp"]),
        "wind": wind_to_words(weather["wind_speed"]),
        "wind_speed": number_to_words(weather["wind_speed"]),
        "precip_chance": percent_to_words(weather["precip_chance"]),
        "timezone": weather["timezone"],
    }


def build_template_context(fields, now):
    context = {}

    needs_location = bool(fields & LOCATION_FIELDS)
    needs_weather = bool(fields & WEATHER_FIELDS)

    if needs_location or needs_weather:
        location_context = build_location_context()
        context.update(location_context)

        if needs_weather:
            weather_context = build_weather_context(location_context)
            context.update(weather_context)

    context.update(
        {
            "time": time_to_words(now),
            "weekday": now.strftime("%A"),
            "date": date_to_words(now),
        }
    )
    return context
