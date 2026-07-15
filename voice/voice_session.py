# =====================================
# Titan Voice Session
# =====================================

"""Persistent voice session storage for Voice Runtime V1."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import settings as app_settings
from voice.exceptions import VoiceSessionError
from voice.models import VoiceConfig, VoiceSession, VoiceState

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VoiceSessionStore:
    """Load, save, and manage voice conversation sessions."""

    def __init__(self, file_path: Path | str | None = None) -> None:
        raw = file_path or app_settings.TITAN_VOICE_SESSIONS_PATH
        self.file_path = Path(raw)
        self._data: dict[str, Any] | None = None

    def default_schema(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "active_session_id": None,
            "sessions": {},
        }

    def load(self) -> dict[str, Any]:
        if self._data is not None:
            return self._data
        if not self.file_path.exists():
            self._data = self.default_schema()
            return self._data
        try:
            with self.file_path.open("r", encoding="utf-8") as handle:
                self._data = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Corrupt voice sessions file %s: %s", self.file_path, exc)
            raise VoiceSessionError(f"Failed to load voice sessions: {exc}") from exc
        if "sessions" not in self._data:
            self._data = self.default_schema()
        return self._data

    def save(self) -> None:
        data = self.load()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=4, ensure_ascii=False)

    def create_session(
        self,
        *,
        config: VoiceConfig | None = None,
        conversation_id: str | None = None,
    ) -> VoiceSession:
        cfg = config or VoiceConfig()
        session = VoiceSession(
            conversation_id=conversation_id or str(uuid4()),
            microphone_device=cfg.microphone_device,
            speaker_device=cfg.speaker_device,
            language=cfg.language,
            config=cfg,
            state=VoiceState.IDLE,
            active=True,
        )
        data = self.load()
        data["sessions"][session.conversation_id] = session.to_dict()
        data["active_session_id"] = session.conversation_id
        self.save()
        logger.info("Voice session created id=%s", session.conversation_id)
        return session

    def get_session(self, conversation_id: str) -> VoiceSession | None:
        data = self.load()
        raw = data.get("sessions", {}).get(conversation_id)
        if raw is None:
            return None
        return VoiceSession.from_dict(raw)

    def get_active_session(self) -> VoiceSession | None:
        data = self.load()
        active_id = data.get("active_session_id")
        if not active_id:
            return None
        return self.get_session(str(active_id))

    def update_session(self, session: VoiceSession) -> None:
        data = self.load()
        if session.conversation_id not in data.get("sessions", {}):
            raise VoiceSessionError(f"Unknown session {session.conversation_id}")
        session.updated_at = _utc_now()
        data["sessions"][session.conversation_id] = session.to_dict()
        self.save()

    def end_session(self, conversation_id: str) -> VoiceSession:
        session = self.get_session(conversation_id)
        if session is None:
            raise VoiceSessionError(f"Unknown session {conversation_id}")
        session.active = False
        session.state = VoiceState.IDLE
        session.ended_at = _utc_now()
        data = self.load()
        data["sessions"][conversation_id] = session.to_dict()
        if data.get("active_session_id") == conversation_id:
            data["active_session_id"] = None
        self.save()
        logger.info(
            "Voice session ended id=%s duration=%.1fs",
            conversation_id,
            session.session_duration_seconds,
        )
        return session

    def list_sessions(self, *, active_only: bool = False) -> list[VoiceSession]:
        data = self.load()
        sessions = [
            VoiceSession.from_dict(raw)
            for raw in data.get("sessions", {}).values()
        ]
        if active_only:
            sessions = [s for s in sessions if s.active]
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)
