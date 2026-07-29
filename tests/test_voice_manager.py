# =====================================
# Titan Voice Manager Tests
# =====================================

"""Tests for Phase 17.8 voice orchestration facade."""

from __future__ import annotations

from voice.voice_manager import VoiceManager


def test_voice_manager_default_config(monkeypatch) -> None:
    monkeypatch.setattr("voice.voice_manager.app_settings.TITAN_VOICE_ENABLED", True)
    monkeypatch.setattr("voice.voice_manager.app_settings.TITAN_VOICE_CONTINUOUS", False)
    monkeypatch.setattr("voice.voice_manager.app_settings.TITAN_VOICE_LOCALE", "fr-FR")
    monkeypatch.setattr("voice.voice_manager.app_settings.TITAN_VOICE_TTS_RATE", 0.95)
    monkeypatch.setattr("voice.voice_manager.app_settings.TITAN_VOICE_TTS_PITCH", 1.0)
    monkeypatch.setattr("voice.voice_manager.app_settings.TITAN_VOICE_STT_PROVIDER", "mock")
    monkeypatch.setattr("voice.voice_manager.app_settings.TITAN_VOICE_TTS_PROVIDER", "mock")
    monkeypatch.setattr(
        "voice.voice_manager.app_settings.TITAN_VOICE_SPEAKER_ID_ENABLED", True
    )
    monkeypatch.setattr(
        "voice.voice_manager.app_settings.TITAN_VOICE_SPEAKER_MIN_CONFIDENCE", 0.72
    )

    manager = VoiceManager()
    config = manager.get_config()

    assert config["capabilities"]["enabled"] is True
    assert config["capabilities"]["push_to_talk"] is True
    assert config["capabilities"]["wake_word"] is False
    assert config["capabilities"]["speaker_identification"] is True
    assert config["providers"]["stt"] == "browser_webspeech"
    assert config["providers"]["tts"] == "browser_speech_synthesis"
    assert config["speech"]["locale"] == "fr-FR"
    assert config["speaker_identification"]["enabled"] is True


def test_voice_manager_capabilities_flags(monkeypatch) -> None:
    monkeypatch.setattr("voice.voice_manager.app_settings.TITAN_VOICE_ENABLED", False)
    monkeypatch.setattr("voice.voice_manager.app_settings.TITAN_VOICE_CONTINUOUS", True)

    caps = VoiceManager().get_capabilities()

    assert caps.enabled is False
    assert caps.continuous_listening is True
    assert caps.interrupt_on_listen is True
