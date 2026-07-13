# Qwen Speech Service

An independently installable HTTP service exposing Qwen voice cloning through an OpenAI-compatible speech endpoint.

The service loads one Qwen model and its configured voice prompts on a dedicated worker thread. Inference is serialized so the model is never invoked concurrently.

## Run

From the repository root:

```bash
cd services/qwen-speech
uv sync --dev
uv run qwen-speech serve
```

The service binds to `127.0.0.1:8101` by default. `/health/live` responds as soon as HTTP is available; `/health/ready` returns `503` until the model and voices have loaded.

```bash
curl http://127.0.0.1:8101/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3-tts-0.6b",
    "input": "Hello from the speech service.",
    "voice": "announcer",
    "response_format": "wav"
  }' \
  --output speech.wav
```

The Qwen backend currently supports WAV output, normal speed, audio response streaming, and no style instructions.

## Configuration

- `QWEN_SPEECH_API_KEY`: require `Authorization: Bearer <token>` when set
- `QWEN_SPEECH_MODEL_PATH`: model source passed to `from_pretrained`
- `QWEN_SPEECH_MODEL_ID`: model name exposed through the HTTP API
- `QWEN_SPEECH_MAX_PENDING_REQUESTS`: maximum running and queued generations; defaults to `2`
- `QWEN_SPEECH_BACKEND`: `qwen` by default; use `fake` for a lightweight development server

Packaged voices are defined in `src/qwen_speech/voices`. Each TOML file points to reference audio stored in the same package.

## Endpoints

- `POST /v1/audio/speech`
- `GET /v1/models`
- `GET /health/live`
- `GET /health/ready`
