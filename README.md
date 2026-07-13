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
uv run python speak.py "Hello."
```

Initialize the controller database and start its API in another terminal:

```bash
uv run donnietts db upgrade
uv run donnietts serve
```

The database migration seeds the existing daily schedule the first time it is applied.

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

The controller stays available and reports `degraded` if the speech service is unavailable. Its readiness endpoint returns `503` until database migrations have been applied.

The controller defaults to `http://127.0.0.1:8101/v1` using the `qwen3-tts-0.6b` model and `announcer` voice.

The SQLite database defaults to `~/.local/state/donnietts/donnietts.sqlite3`. Override it with `DONNIETTS_DB_PATH`.

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
