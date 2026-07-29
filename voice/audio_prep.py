# =====================================
# Titan Voice Audio Prep for Embeddings
# =====================================

"""PCM / WAV helpers for speaker embedding backends (Phase 20.12).

Synthetic / capture audio only — never logs waveform contents.

Uses only ``wave`` / ``struct`` / ``array`` so Titan stays compatible with
Python 3.13+ (stdlib ``audioop`` removed).
"""

from __future__ import annotations

import array
import struct
import wave
from io import BytesIO


def strip_wav_header(audio_bytes: bytes) -> bytes:
    """Return PCM payload when *audio_bytes* is RIFF/WAV; else original bytes."""
    if len(audio_bytes) > 44 and audio_bytes[:4] == b"RIFF":
        return audio_bytes[44:]
    return audio_bytes


def _pcm16_to_floats(pcm: bytes) -> list[float]:
    count = len(pcm) // 2
    if count <= 0:
        return []
    samples = array.array("h")
    samples.frombytes(pcm[: count * 2])
    return [s / 32768.0 for s in samples]


def _downsample_mono(samples: list[float], source_rate: int, target_rate: int) -> list[float]:
    if source_rate <= 0 or target_rate <= 0 or source_rate == target_rate:
        return samples
    if not samples:
        return []
    ratio = source_rate / float(target_rate)
    out_len = max(1, int(len(samples) / ratio))
    out: list[float] = []
    for i in range(out_len):
        src = i * ratio
        left = int(src)
        right = min(left + 1, len(samples) - 1)
        frac = src - left
        out.append(samples[left] * (1.0 - frac) + samples[right] * frac)
    return out


def decode_pcm16_mono(
    audio_bytes: bytes,
    *,
    source_rate: int = 16000,
    target_rate: int = 16000,
) -> tuple[list[float], int]:
    """Decode bytes to mono float32 samples in [-1, 1] at *target_rate*.

    Accepts raw PCM16 little-endian or WAV-wrapped PCM16. Returns
    ``(samples, sample_rate)``. Empty input yields ``([], target_rate)``.
    """
    if not audio_bytes:
        return [], target_rate

    rate = source_rate
    channels = 1
    sample_width = 2
    pcm = audio_bytes

    if len(audio_bytes) > 44 and audio_bytes[:4] == b"RIFF":
        try:
            with wave.open(BytesIO(audio_bytes), "rb") as handle:
                rate = int(handle.getframerate())
                channels = int(handle.getnchannels())
                sample_width = int(handle.getsampwidth())
                pcm = handle.readframes(handle.getnframes())
        except wave.Error:
            pcm = strip_wav_header(audio_bytes)

    if not pcm:
        return [], target_rate

    # Normalize to 16-bit little-endian frames.
    if sample_width == 1:
        # Unsigned 8-bit → signed 16-bit.
        pcm = b"".join(
            struct.pack("<h", (b - 128) << 8) for b in pcm
        )
        sample_width = 2
    elif sample_width == 4:
        count = len(pcm) // 4
        ints = struct.unpack(f"<{count}i", pcm[: count * 4])
        pcm = struct.pack(
            f"<{count}h",
            *[max(-32768, min(32767, v >> 16)) for v in ints],
        )
        sample_width = 2
    elif sample_width != 2:
        return [], target_rate

    if channels > 1:
        frames = memoryview(pcm).cast("h")
        mono = frames[0::channels]
        pcm = mono.tobytes()
        channels = 1

    samples = _pcm16_to_floats(pcm)
    if rate != target_rate:
        samples = _downsample_mono(samples, rate, target_rate)
        rate = target_rate
    return samples, rate


def floats_to_pcm16_wav(
    samples: list[float],
    *,
    sample_rate: int = 16000,
) -> bytes:
    """Encode float samples as a mono PCM16 WAV (for synthetic test audio)."""
    clipped = [max(-1.0, min(1.0, float(s))) for s in samples]
    pcm = struct.pack(
        f"<{len(clipped)}h",
        *[int(s * 32767.0) for s in clipped],
    )
    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()
