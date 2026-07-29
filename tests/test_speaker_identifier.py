# =====================================
# Titan Phase 20.1 — Speaker Identifier Tests
# =====================================

"""Speaker enrollment, identification, and confirm-on-unknown protocol."""

from __future__ import annotations

from pathlib import Path

import pytest

from context.session_manager import SessionManager
from voice.exceptions import VoiceConfigurationError
from voice.speaker_identifier import (
    UNKNOWN_SPEAKER_PROMPT,
    SpeakerIdentifier,
    SpeakerIdentity,
    extract_voice_features,
    parse_spoken_identity,
)


def _audio_pattern(seed: int, size: int = 2048) -> bytes:
    return bytes((seed + i * 17) % 256 for i in range(size))


def test_extract_voice_features_fixed_dim() -> None:
    features = extract_voice_features(_audio_pattern(3))
    assert len(features) == 32
    norm = sum(v * v for v in features) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_enroll_and_identify_known_speaker(tmp_path: Path) -> None:
    identifier = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        min_confidence=0.5,
        enabled=True,
    )
    nolan_audio = _audio_pattern(11)
    identifier.enroll("Nolan", [nolan_audio, nolan_audio])
    result = identifier.identify(nolan_audio)
    assert result.identity == SpeakerIdentity.NOLAN
    assert result.matched_user == "Nolan"
    assert result.confidence >= 0.5
    assert not result.requires_confirmation


def test_unknown_when_no_profiles(tmp_path: Path) -> None:
    identifier = SpeakerIdentifier(file_path=tmp_path / "profiles.json", enabled=True)
    result = identifier.identify(_audio_pattern(5))
    assert result.identity == SpeakerIdentity.UNKNOWN
    assert result.requires_confirmation
    assert result.reason == "no_enrolled_profiles"


def test_low_confidence_requires_confirmation(tmp_path: Path) -> None:
    identifier = SpeakerIdentifier(
        file_path=tmp_path / "profiles.json",
        min_confidence=0.85,
        enabled=True,
    )
    # Highly dissimilar envelopes so cosine similarity stays low.
    identifier.enroll("Ibrahim", [bytes([0] * 2048)])
    result = identifier.identify(bytes([255] * 2048))
    assert result.identity == SpeakerIdentity.UNKNOWN
    assert result.requires_confirmation


def test_confirm_from_text_binds_session(tmp_path: Path) -> None:
    identifier = SpeakerIdentifier(file_path=tmp_path / "profiles.json", enabled=True)
    session = SessionManager(current_user="Nolan")
    session.set_user("Ibrahim")
    result = identifier.confirm_from_text("je suis Nolan")
    assert result.identity == SpeakerIdentity.NOLAN
    ok, message = identifier.bind_session_user(session, result)
    assert ok
    assert session.current_user == "Nolan"
    assert "Nolan" in message


def test_unknown_bind_returns_prompt(tmp_path: Path) -> None:
    identifier = SpeakerIdentifier(file_path=tmp_path / "profiles.json", enabled=True)
    session = SessionManager()
    result = identifier.identify(b"")
    ok, message = identifier.bind_session_user(session, result)
    assert not ok
    assert message == UNKNOWN_SPEAKER_PROMPT


def test_cannot_enroll_unauthorized_user(tmp_path: Path) -> None:
    identifier = SpeakerIdentifier(file_path=tmp_path / "profiles.json", enabled=True)
    with pytest.raises(VoiceConfigurationError):
        identifier.enroll("Alice", [_audio_pattern(1)])


def test_parse_spoken_identity() -> None:
    assert parse_spoken_identity("Je suis Ibrahim") == "Ibrahim"
    assert parse_spoken_identity("c'est Nolan") == "Nolan"
    assert parse_spoken_identity("bonjour") is None


def test_profiles_persist(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    first = SpeakerIdentifier(file_path=path, enabled=True)
    first.enroll("Ibrahim", [_audio_pattern(42)])
    second = SpeakerIdentifier(file_path=path, enabled=True)
    result = second.identify(_audio_pattern(42))
    assert result.matched_user == "Ibrahim"
