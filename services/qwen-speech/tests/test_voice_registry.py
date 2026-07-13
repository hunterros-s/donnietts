from qwen_speech.voice_registry import VoiceRegistry


def test_packaged_announcer_voice_is_available() -> None:
    registry = VoiceRegistry.from_package()
    voice = registry.get("announcer")

    assert voice is not None
    assert voice.language == "English"
    assert voice.reference_audio.name == "announcer.wav"
    assert voice.reference_audio.is_file()
    assert "advanced artificial intelligence" in voice.reference_text
