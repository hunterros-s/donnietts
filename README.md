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

Start the controller API and announcement worker together in one process:

```bash
uv run donnietts run
```

`run` serves the API on `127.0.0.1:8000` and runs the scheduler. The scheduler
loads `schedule.yaml`, generates speech before each scheduled time, and plays
it. The pieces are also available separately for development: `uv run
donnietts serve` (API only) and `uv run donnietts worker` (scheduler only).

YAML is the source of truth for the schedule. SQLite stores pause state, the
schedule projection used by the worker, and durable run history. The controller
creates its database schema and default settings automatically on startup.

Inspect its status, YAML, and projected schedule:

```bash
curl http://127.0.0.1:8000/api/v1/status
curl http://127.0.0.1:8000/api/v1/schedule
curl http://127.0.0.1:8000/api/v1/announcements
```

Or inspect them without a running controller:

```bash
uv run donnietts schedule   # the current schedule
uv run donnietts runs       # recent run history (--limit N to change the cap)
uv run donnietts pause      # stop speaking; due runs are skipped as 'paused'
uv run donnietts resume     # resume speaking
```

Pausing keeps the controller and schedule running (the worker skips due runs
with reason `announcements paused`), so resume is instant. The equivalent API
is `PATCH /api/v1/settings` with `{"announcements_enabled": false}`.

Pause announcements through the operational settings API:

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/settings \
  -H 'Content-Type: application/json' \
  -d '{"announcements_enabled": false}'
```

Edit `schedule.yaml` directly with `vim`, or use the Schedule tab in the web UI.
The worker notices valid external edits on its next scheduling pass. Invalid
external YAML degrades readiness but leaves the last valid schedule running.

```yaml
version: 1
timezone: America/Detroit

defaults:
  lead_seconds: 300

announcements:
  - time: "07:30"
    template: Good morning. It is {time}.

  - run_at: "2030-01-01T14:30:00-05:00"
    lead_seconds: 600
    template: Leave for the appointment soon.
```

Each announcement specifies exactly one of `time` (a daily `HH:MM` time in the
configured IANA timezone) or `run_at` (an RFC 3339 timestamp with an offset).
`enabled` defaults to true. `lead_seconds` can be set globally or per item; the
older `lead_minutes` spelling is also accepted. Duplicate daily or one-off
times are rejected.

The raw-file API is `GET`/`PUT /api/v1/schedule`. Saves validate the complete
file and use the response ETag with `If-Match` to prevent overwriting a newer
server-side edit.

Supported template fields are `time`, `weekday`, `date`, `location`, `city`, `state`, `latitude`, `longitude`, `weather_condition`, `current_temp`, `high_temp`, `low_temp`, `wind`, `wind_speed`, and `precip_chance`.

The controller stays available and reports `degraded` if the speech service is unavailable.
Its readiness endpoint returns `503` if the database is unavailable or the YAML schedule is missing or invalid.

The controller defaults to `http://127.0.0.1:8101/v1` using the `qwen3-tts-0.6b` model and `announcer` voice.

The SQLite database defaults to `~/.local/state/donnietts/donnietts.sqlite3`. Override it with `DONNIETTS_DB_PATH`.

To do a one-time export from a database-backed installation before switching
to YAML:

```bash
uv run scripts/export-schedule.py --output schedule.yaml --force
```

Use `--database PATH` when the old database is not at the default location.

## Context and audio configuration

Template rendering fetches location (via IP) and weather (open-meteo) when the
template uses those fields:

- `DONNIETTS_DISPLAY_CITY` / `DONNIETTS_DISPLAY_STATE`: spoken location name; defaults to `edwardsburg, michigan`
- `DONNIETTS_USER_AGENT`: user agent for context lookups; defaults to `chime-announcement/0.1`
- `DONNIETTS_SCHEDULE_PATH`: YAML schedule path; defaults to `schedule.yaml` in the working directory
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

## Running as a systemd service

For a machine that should announce around the clock, install two user services
after syncing dependencies:

```bash
scripts/install-systemd.sh --start
```

This installs `donnietts-speech` (the Qwen speech service) and `donnietts` (the
controller API + worker in one process) as systemd user services, enables them
to start at boot, and keeps them running with automatic restarts.

```bash
systemctl --user status donnietts
journalctl --user -u donnietts -f
```

To stop things: `systemctl --user stop donnietts` stops the controller and
worker (the YAML schedule and SQLite run history remain on disk);
`systemctl --user stop donnietts-speech` unloads the speech model and frees
its memory — while it is stopped, due announcements are skipped. To pause
announcements without stopping anything, use `uv run donnietts pause`.

Override any variable (for example `TTS_BASE_URL` or `DONNIETTS_DB_PATH`) in
`~/.config/donnietts/env`. The first speech-service start downloads the Qwen
model from Hugging Face, so the controller reports `warming` until it is ready.

## Web UI

The controller serves a small single-page interface at
<http://127.0.0.1:8000/> (no build step — it is static files served by the
FastAPI app, and only reachable from the machine itself):

- **Status** — controller health, a pause/resume switch for announcements, the
  speech service's state (ready / warming / unavailable), and the next few
  upcoming announcements (shown in the controller's timezone).
- **Schedule** — a monospace YAML editor with Save and Reload controls. It
  edits the same file that can be changed directly with `vim` on the server.
- **Runs** — recent run history with status and outcome (what was spoken, or
  why a run was skipped or failed).

The UI is built on [Web Awesome](https://webawesome.com/) (the actively
maintained successor to Shoelace) using `wa-*` web components — tabs, switch,
dialog, select, inputs, tags. The components are **vendored** under
`src/donnietts/web/vendor/` (MIT licensed, ~2.5 MB) so the page works fully
offline with no CDN dependency, plus a small local icon set so even the
component glyphs (select chevron, dialog close) never hit the network.

To reach it from another machine, tunnel over SSH:

```bash
ssh -L 8000:127.0.0.1:8000 hunter@donnied   # then open http://127.0.0.1:8000/
```

It deliberately has no authentication — it binds to loopback only. If you want
it on your LAN, add a reverse proxy with auth in front of it instead of
opening the port.
