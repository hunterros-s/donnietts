import httpx

from config import USER_AGENT


async def fetch_json(client: httpx.AsyncClient, url: str) -> dict:
    response = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    return response.json()
