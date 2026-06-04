from urllib.parse import urlencode

from utils import fetch_json


def detect_location():
    data = fetch_json("https://ipapi.co/json/")
    lat = data.get("latitude")
    lon = data.get("longitude")

    if lat is None or lon is None:
        raise RuntimeError(data.get("reason") or data.get("error") or "IP lookup did not return coordinates")

    print("Location source: IP")
    return float(lat), float(lon)


def reverse_geocode(lat, lon):
    query = urlencode({"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 10, "addressdetails": 1})
    data = fetch_json(f"https://nominatim.openstreetmap.org/reverse?{query}")
    address = data.get("address", {})

    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("hamlet")
        or address.get("municipality")
        or address.get("county")
    )
    state = address.get("state")

    if city and state:
        return f"{city}, {state}"
    return city or state or data.get("display_name", "your current location")
