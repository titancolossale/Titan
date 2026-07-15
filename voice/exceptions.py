# =====================================
# Titan Voice Exceptions
# =====================================

"""Exception hierarchy for Voice Runtime V1."""


class VoiceError(Exception):
    """Base error for voice runtime failures."""


class VoiceConfigurationError(VoiceError):
    """Invalid or incomplete voice configuration."""


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
