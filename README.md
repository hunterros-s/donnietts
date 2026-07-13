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

Start the controller API in another terminal:

```bash
uv run donnietts serve
```

Inspect its status:

```bash
curl http://127.0.0.1:8000/api/v1/status
```

The controller stays available and reports `degraded` if the speech service is unavailable.

The controller defaults to `http://127.0.0.1:8101/v1` using the `qwen3-tts-0.6b` model and `announcer` voice.

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
