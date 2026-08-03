# DonnieTTS

Scheduled spoken announcements using an OpenAI-compatible speech endpoint.

## Local Qwen speech service

Start the standalone service:

```bash
cd services/qwen-speech
uv sync --dev
uv run qwen-speech serve
```

Then, from the repository root, test speech playback:

```bash
uv run donnietts say "Hello."
```

`say` renders the template (defaulting to the daily briefing), prints the text,
generates speech, prepends the chime, and plays it. Pass any template, e.g.
`uv run donnietts say "It is {time} in {location}."`

Start the controller API:

```bash
uv run donnietts serve
```

In a third terminal, run the announcement worker, which materializes runs from the
announcements table, generates speech before each scheduled time, and plays it:

```bash
uv run donnietts worker
```

The controller creates its database schema and default settings automatically on
startup, so no separate setup step is required.

Inspect its status and persisted settings:

```bash
curl http://127.0.0.1:8000/api/v1/status
curl http://127.0.0.1:8000/api/v1/settings
curl http://127.0.0.1:8000/api/v1/announcements
```

Pause announcements or update the IANA timezone:

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/settings \
  -H 'Content-Type: application/json' \
  -d '{"announcements_enabled": false}'

curl -X PATCH http://127.0.0.1:8000/api/v1/settings \
  -H 'Content-Type: application/json' \
  -d '{"timezone": "America/Detroit"}'
```

Daily times are interpreted in this timezone. One-off announcements require an RFC 3339 timestamp with a UTC offset and are stored in UTC.

Create announcements:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/announcements/daily \
  -H 'Content-Type: application/json' \
  -d '{"time":"07:30","template":"Good morning. It is {time}.","lead_seconds":300}'

curl -X POST http://127.0.0.1:8000/api/v1/announcements/one-off \
  -H 'Content-Type: application/json' \
  -d '{"run_at":"2030-01-01T14:30:00-05:00","template":"Leave for the appointment soon."}'
```

Edits require the current `revision` and increment it when successful. Stale edits and deletes return `409 Conflict`.

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/announcements/15 \
  -H 'Content-Type: application/json' \
  -d '{"expected_revision":1,"enabled":false}'

curl -X DELETE 'http://127.0.0.1:8000/api/v1/announcements/15?expected_revision=2'
```

Supported template fields are `time`, `weekday`, `date`, `location`, `city`, `state`, `latitude`, `longitude`, `weather_condition`, `current_temp`, `high_temp`, `low_temp`, `wind`, `wind_speed`, and `precip_chance`.

The controller stays available and reports `degraded` if the speech service is unavailable.
Its readiness endpoint returns `503` if its database is unavailable.

The controller defaults to `http://127.0.0.1:8101/v1` using the `qwen3-tts-0.6b` model and `announcer` voice.

The SQLite database defaults to `~/.local/state/donnietts/donnietts.sqlite3`. Override it with `DONNIETTS_DB_PATH`.

## Context and audio configuration

Template rendering fetches location (via IP) and weather (open-meteo) when the
template uses those fields:

- `DONNIETTS_DISPLAY_CITY` / `DONNIETTS_DISPLAY_STATE`: spoken location name; defaults to `edwardsburg, michigan`
- `DONNIETTS_USER_AGENT`: user agent for context lookups; defaults to `chime-announcement/0.1`
- `DONNIETTS_FETCH_TIMEOUT_SECONDS`: context lookup timeout; defaults to `20`
- `DONNIETTS_CHIME_AUDIO` / `DONNIETTS_SOUND_OFF_AUDIO`: chime and closing sound paths; default to `assets/startup3.mp3` and `assets/sound_off.mp3`

## Speech endpoint configuration

- `TTS_BASE_URL`: defaults to `http://127.0.0.1:8101/v1`
- `TTS_API_KEY`: defaults to `local`
- `TTS_MODEL`: defaults to `qwen3-tts-0.6b`
- `TTS_VOICE`: defaults to `announcer`
- `TTS_INSTRUCTIONS`: optional provider-specific speaking instructions
- `TTS_TIMEOUT_SECONDS`: generation timeout; defaults to `300`
- `TTS_HEALTH_URL`: optional provider readiness endpoint; automatically derived for a local service
- `TTS_STATUS_TIMEOUT_SECONDS`: provider status timeout; defaults to `2`

The controller can target another OpenAI-compatible speech provider by changing these variables. It does not load or depend on Qwen directly.

## Tests

```bash
uv sync --dev
uv run pytest
```

The controller tests use isolated temporary SQLite databases and do not modify the configured application database.
