import asyncio
from datetime import datetime

import httpx

from template import render_template


def test_time_only_template_performs_no_network_requests() -> None:
    async def exercise() -> None:
        async def unexpected_request(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"Unexpected request: {request.url}")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(unexpected_request)
        ) as client:
            rendered = await render_template(
                client,
                "It is {time} on {weekday}, {date}.",
                datetime(2026, 1, 2, 9, 0),
            )

        assert rendered == "It is nine o'clock A M on Friday, January second."

    asyncio.run(exercise())


def test_location_and_weather_context_use_async_http_client() -> None:
    async def exercise() -> None:
        requested_urls: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            assert request.headers["User-Agent"] == "chime-announcement/0.1"
            if request.url.host == "ipapi.co":
                return httpx.Response(
                    200,
                    json={"latitude": 41.8, "longitude": -86.1},
                )
            if request.url.host == "api.open-meteo.com":
                return httpx.Response(
                    200,
                    json={
                        "current": {
                            "temperature_2m": 32,
                            "weather_code": 3,
                            "wind_speed_10m": 5,
                        },
                        "daily": {
                            "temperature_2m_max": [40],
                            "temperature_2m_min": [25],
                            "precipitation_probability_max": [20],
                        },
                        "timezone": "America/Detroit",
                    },
                )
            raise AssertionError(f"Unexpected request: {request.url}")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            rendered = await render_template(
                client,
                "In {location}, it is {current_temp} degrees and {weather_condition}.",
                datetime(2026, 1, 2, 9, 0),
            )

        assert rendered == "In edwardsburg, michigan, it is thirty two degrees and overcast."
        assert len(requested_urls) == 2
        assert requested_urls[0] == "https://ipapi.co/json/"
        assert requested_urls[1].startswith("https://api.open-meteo.com/v1/forecast?")

    asyncio.run(exercise())
