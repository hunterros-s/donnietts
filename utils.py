import json
from urllib.request import Request, urlopen

from config import USER_AGENT


def fetch_json(url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:
        return json.load(response)
