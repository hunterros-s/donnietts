# DonnieTTS

Scheduled spoken announcements with local or OpenAI-compatible speech generation.

## Speech providers

The existing embedded Qwen provider remains the default:

```bash
uv run python speak.py "Hello."
```

To use the standalone Qwen speech service, start it first:

```bash
cd services/qwen-speech
uv sync --dev
uv run qwen-speech serve
```

Then run the controller with the HTTP provider:

```bash
TTS_PROVIDER=openai uv run python speak.py "Hello."
```

Controller speech configuration:

- `TTS_PROVIDER`: `embedded` or `openai`
- `TTS_BASE_URL`: defaults to `http://127.0.0.1:8101/v1`
- `TTS_API_KEY`: defaults to `local`
- `TTS_MODEL`: defaults to `qwen3-tts-0.6b`
- `TTS_VOICE`: defaults to `announcer`
- `TTS_INSTRUCTIONS`: optional provider-specific speaking instructions
- `TTS_TIMEOUT_SECONDS`: defaults to `300`

The same HTTP provider can target another OpenAI-compatible speech endpoint by changing these variables.
