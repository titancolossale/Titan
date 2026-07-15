# =====================================
# Titan Audio Devices
# =====================================

"""Audio device discovery and playback/capture abstractions for Voice Runtime V1."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from voice.exceptions import VoiceDeviceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioDeviceInfo:
    """Describes an input or output audio device."""

    device_id: str
    name: str
    is_input: bool
    is_output: bool
    is_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "is_input": self.is_input,
            "is_output": self.is_output,
            "is_default": self.is_default,
        }


class AudioCapture(ABC):
    """Abstract microphone capture — real hardware or test double."""

    @abstractmethod
    def start_listening(self, *, device_id: str, silence_timeout: float) -> None:
        """Begin capturing audio from the given device."""

    @abstractmethod
    def stop_listening(self) -> bytes:
        """Stop capture and return recorded audio bytes."""

    @abstractmethod
    def is_listening(self) -> bool:
        """Return True while capture is active."""


class AudioPlayback(ABC):
    """Abstract speaker playback with interruption support."""

    @abstractmethod
    def play(self, audio_bytes: bytes, *, device_id: str, volume: float) -> None:
        """Play audio on the given output device."""

    @abstractmethod
    def stop(self) -> None:
        """Stop current playback immediately."""

    @abstractmethod
    def is_playing(self) -> bool:
        """Return True while audio is playing."""


class MockAudioCapture(AudioCapture):
    """Test double that returns preloaded audio on stop."""

    def __init__(self, *, audio_payload: bytes = b"mock-audio-input") -> None:
        self._audio_payload = audio_payload
        self._listening = False
        self._device_id = "default"

    def set_audio_payload(self, payload: bytes) -> None:
        self._audio_payload = payload

    def start_listening(self, *, device_id: str, silence_timeout: float) -> None:
        self._device_id = device_id
        self._listening = True
        logger.debug(
            "Mock capture start device=%s silence_timeout=%.2f",
            device_id,
            silence_timeout,
        )

    def stop_listening(self) -> bytes:
        self._listening = False
        logger.debug("Mock capture stop device=%s bytes=%d", self._device_id, len(self._audio_payload))
        return self._audio_payload

    def is_listening(self) -> bool:
        return self._listening


class MockAudioPlayback(AudioPlayback):
    """Test double that records playback calls without hardware."""

    def __init__(self) -> None:
        self._playing = False
        self.last_audio: bytes = b""
        self.last_device: str = ""
        self.last_volume: float = 1.0
        self.play_count = 0
        self.stop_count = 0

    def play(self, audio_bytes: bytes, *, device_id: str, volume: float) -> None:
        self._playing = True
        self.last_audio = audio_bytes
        self.last_device = device_id
        self.last_volume = volume
        self.play_count += 1
        logger.debug(
            "Mock playback device=%s volume=%.2f bytes=%d",
            device_id,
            volume,
            len(audio_bytes),
        )
        self._playing = False

    def stop(self) -> None:
        self._playing = False
        self.stop_count += 1
        logger.debug("Mock playback stopped")

    def is_playing(self) -> bool:
        return self._playing


class AudioDeviceManager:
    """Discover and resolve microphone/speaker devices."""

    def __init__(self, devices: list[AudioDeviceInfo] | None = None) -> None:
        self._devices = devices or self._default_devices()

    @staticmethod
    def _default_devices() -> list[AudioDeviceInfo]:
        return [
            AudioDeviceInfo("default", "System Default", True, True, is_default=True),
            AudioDeviceInfo("mic-1", "Built-in Microphone", True, False),
            AudioDeviceInfo("spk-1", "Built-in Speakers", False, True),
        ]

    def list_devices(self) -> list[AudioDeviceInfo]:
        return list(self._devices)

    def list_input_devices(self) -> list[AudioDeviceInfo]:
        return [d for d in self._devices if d.is_input]

    def list_output_devices(self) -> list[AudioDeviceInfo]:
        return [d for d in self._devices if d.is_output]

    def resolve_input(self, device_id: str) -> AudioDeviceInfo:
        return self._resolve(device_id, want_input=True)

    def resolve_output(self, device_id: str) -> AudioDeviceInfo:
        return self._resolve(device_id, want_input=False)

    def _resolve(self, device_id: str, *, want_input: bool) -> AudioDeviceInfo:
        key = (device_id or "default").strip()
        for device in self._devices:
            if device.device_id == key:
                if want_input and not device.is_input:
                    raise VoiceDeviceError(f"Device {key!r} is not an input device")
                if not want_input and not device.is_output:
                    raise VoiceDeviceError(f"Device {key!r} is not an output device")
                return device
        if key == "default":
            candidates = self.list_input_devices() if want_input else self.list_output_devices()
            for device in candidates:
                if device.is_default:
                    return device
            if candidates:
                return candidates[0]
        raise VoiceDeviceError(f"Audio device not found: {key!r}")
