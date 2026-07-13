import httpx

from utils import fetch_json

DISPLAY_CITY = "edwardsburg"
DISPLAY_STATE = "michigan"
DISPLAY_LOCATION = f"{DISPLAY_CITY}, {DISPLAY_STATE}"


async def detect_coordinates(client: httpx.AsyncClient):
    data = await fetch_json(client, "https://ipapi.co/json/")
    lat = data.get("latitude")
    lon = data.get("longitude")

    if lat is None or lon is None:
        raise RuntimeError(data.get("reason") or data.get("error") or "IP lookup did not return coordinates")

    print("Location source: IP")
    return float(lat), float(lon)


async def get_location(client: httpx.AsyncClient):
    lat, lon = await detect_coordinates(client)
    location = {
        "location": DISPLAY_LOCATION,
        "city": DISPLAY_CITY,
        "state": DISPLAY_STATE,
        "latitude": lat,
        "longitude": lon,
    }
    print(f"Using display location: {DISPLAY_LOCATION} ({lat:.4f}, {lon:.4f})")
    return location
