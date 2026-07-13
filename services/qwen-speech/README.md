# Qwen Speech Service

An independently installable HTTP service exposing an OpenAI-compatible speech endpoint.

This first scaffold uses a deterministic fake backend. It does not load Qwen yet and currently emits WAV audio only.

## Run

From the repository root:

```bash
cd services/qwen-speech
uv sync --dev
uv run qwen-speech serve
```

The service binds to `127.0.0.1:8101` by default.

```bash
curl http://127.0.0.1:8101/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "fake-tts",
    "input": "Hello from the speech service.",
    "voice": "announcer",
    "response_format": "wav"
  }' \
  --output speech.wav
```

Set `QWEN_SPEECH_API_KEY` to require `Authorization: Bearer <token>` for API requests.

## Endpoints

- `POST /v1/audio/speech`
- `GET /v1/models`
- `GET /health/live`
- `GET /health/ready`
