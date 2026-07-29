# =====================================
# Titan Voice Exceptions
# =====================================

"""Exception hierarchy for Voice Runtime V1."""


class VoiceError(Exception):
    """Base error for voice runtime failures."""


class VoiceConfigurationError(VoiceError):
    """Invalid or incomplete voice configuration."""

    def __init__(self, message: str, *, code: str = "configuration_error") -> None:
        super().__init__(message)
        self.code = code


class VoiceProviderError(VoiceError):
    """STT or TTS provider failure."""


class VoiceSessionError(VoiceError):
    """Session lifecycle or persistence failure."""


class VoiceDeviceError(VoiceError):
    """Microphone or speaker device failure."""


class VoiceStateError(VoiceError):
    """Invalid state transition or operation for current voice state."""


class VoiceInterruptedError(VoiceError):
    """Operation cancelled due to user interruption."""


class VoiceEnrollmentError(VoiceError):
    """Guided enrollment lifecycle failure (Phase 20.2)."""

    def __init__(self, message: str, *, code: str = "enrollment_error") -> None:
        super().__init__(message)
        self.code = code


class VoiceLiveSessionError(VoiceError):
    """Live voice session orchestration failure (Phase 20.3)."""

    def __init__(self, message: str, *, code: str = "live_session_error") -> None:
        super().__init__(message)
        self.code = code
