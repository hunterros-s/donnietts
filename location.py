from utils import fetch_json

DISPLAY_CITY = "edwardsburg"
DISPLAY_STATE = "michigan"
DISPLAY_LOCATION = f"{DISPLAY_CITY}, {DISPLAY_STATE}"


def detect_coordinates():
    data = fetch_json("https://ipapi.co/json/")
    lat = data.get("latitude")
    lon = data.get("longitude")

    if lat is None or lon is None:
        raise RuntimeError(data.get("reason") or data.get("error") or "IP lookup did not return coordinates")

    print("Location source: IP")
    return float(lat), float(lon)


def get_location():
    lat, lon = detect_coordinates()
    location = {
        "location": DISPLAY_LOCATION,
        "city": DISPLAY_CITY,
        "state": DISPLAY_STATE,
        "latitude": lat,
        "longitude": lon,
    }
    print(f"Using display location: {DISPLAY_LOCATION} ({lat:.4f}, {lon:.4f})")
    return location
