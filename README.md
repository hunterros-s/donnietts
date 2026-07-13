# DonnieTTS

Scheduled spoken announcements using an OpenAI-compatible speech endpoint.

## Local Qwen speech service

Start the standalone service:

```bash
cd services/qwen-speech
uv sync --dev
uv run qwen-speech serve
```

Then, from the repository root:

```bash
uv run python speak.py "Hello."
```

The controller defaults to `http://127.0.0.1:8101/v1` using the `qwen3-tts-0.6b` model and `announcer` voice.

## Speech endpoint configuration

- `TTS_BASE_URL`: defaults to `http://127.0.0.1:8101/v1`
- `TTS_API_KEY`: defaults to `local`
- `TTS_MODEL`: defaults to `qwen3-tts-0.6b`
- `TTS_VOICE`: defaults to `announcer`
- `TTS_INSTRUCTIONS`: optional provider-specific speaking instructions
- `TTS_TIMEOUT_SECONDS`: defaults to `300`

The controller can target another OpenAI-compatible speech provider by changing these variables. It does not load or depend on Qwen directly.
