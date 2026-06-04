from datetime import datetime
from zoneinfo import ZoneInfo

from audio import generate_speech, prepend_chime, write_audio
from config import OUTPUT_AUDIO
from formatting import date_to_words, number_to_words, time_to_words, wind_to_words
from location import detect_location, reverse_geocode
from weather import get_weather


def build_announcement():
    lat, lon = detect_location()
    location = reverse_geocode(lat, lon)
    weather = get_weather(lat, lon)
    now = datetime.now(ZoneInfo(weather["timezone"])) if weather.get("timezone") else datetime.now()

    print(f"Detected location: {location} ({lat:.4f}, {lon:.4f})")

    return (
        f"Today is {date_to_words(now)}. "
        f"The time is {time_to_words(now)}. "
        f"Current conditions in {location} are {weather['condition']}. "
        f"The temperature is {number_to_words(weather['temperature'])} degrees, "
        f"with {wind_to_words(weather['wind_speed'])}."
    )


def main():
    announcement = build_announcement()
    print(announcement)

    speech, sr = generate_speech(announcement)
    combined = prepend_chime(speech, sr)

    write_audio(OUTPUT_AUDIO, combined, sr)
    print(f"Wrote {OUTPUT_AUDIO}")


if __name__ == "__main__":
    main()
