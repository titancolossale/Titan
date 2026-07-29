# =====================================
# Titan TTS Strategy
# =====================================

"""Speech synthesis strategies for live voice sessions (Phase 20.3).

Supports full-response TTS and sentence-buffered TTS with markdown/code
cleanup. Never speaks internal diagnostics, tool payloads, or hidden metadata.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator

from voice.text_to_speech import SynthesisResult, TextToSpeechRegistry, synthesize_speech

logger = logging.getLogger(__name__)


class TTSStrategyMode(str, Enum):
    FULL_RESPONSE = "full_response"
    SENTENCE_BUFFERED = "sentence_buffered"


# Language-aware default OpenAI-style voice ids (safe fallbacks for mock too).
_LOCALE_VOICES: dict[str, str] = {
    "fr": "alloy",
    "fr-FR": "alloy",
    "en": "verse",
    "en-US": "verse",
    "en-GB": "verse",
}


@dataclass
class TTSStrategyConfig:
    mode: TTSStrategyMode = TTSStrategyMode.SENTENCE_BUFFERED
    min_text_chunk_chars: int = 24
    strip_code_blocks: bool = True
    strip_markdown: bool = True
    french_voice: str = "alloy"
    english_voice: str = "verse"


_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_BOLD_ITALIC_RE = re.compile(r"(\*\*|__|\*|_|\~\~)")
_MD_LIST_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_INCOMPLETE_MARKER_RE = re.compile(r"(```|``|\[.*\]\([^)]*$|\*\*$|__$)")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+|(?<=\n)")


def select_voice_for_locale(
    locale: str,
    *,
    configured_voice: str = "default",
    config: TTSStrategyConfig | None = None,
) -> str:
    """Pick a language-aware voice; honor explicit non-default configuration."""
    cfg = config or TTSStrategyConfig()
    if configured_voice and configured_voice != "default":
        return configured_voice
    normalized = (locale or "fr-FR").strip()
    if normalized.lower().startswith("fr"):
        return cfg.french_voice or _LOCALE_VOICES.get("fr-FR", "alloy")
    if normalized.lower().startswith("en"):
        return cfg.english_voice or _LOCALE_VOICES.get("en-US", "verse")
    return _LOCALE_VOICES.get(normalized, cfg.french_voice)


def clean_text_for_speech(text: str, *, config: TTSStrategyConfig | None = None) -> str:
    """Remove markdown/code/formatting before TTS; drop incomplete markers."""
    cfg = config or TTSStrategyConfig()
    raw = (text or "").strip()
    if not raw:
        return ""
    # Never speak incomplete trailing markdown fences / markers.
    if _INCOMPLETE_MARKER_RE.search(raw[-12:] if len(raw) > 12 else raw):
        # Trim from last incomplete marker start when at end of stream chunk.
        for marker in ("```", "``", "**", "__"):
            idx = raw.rfind(marker)
            if idx >= 0 and idx >= len(raw) - len(marker) - 2:
                raw = raw[:idx].rstrip()
                break
    cleaned = raw
    if cfg.strip_code_blocks:
        cleaned = _CODE_BLOCK_RE.sub(" ", cleaned)
        cleaned = _INLINE_CODE_RE.sub(r"\1", cleaned)
    if cfg.strip_markdown:
        cleaned = _MD_IMAGE_RE.sub(r"\1", cleaned)
        cleaned = _MD_LINK_RE.sub(r"\1", cleaned)
        cleaned = _MD_HEADING_RE.sub("", cleaned)
        cleaned = _MD_LIST_RE.sub("", cleaned)
        cleaned = _MD_BOLD_ITALIC_RE.sub("", cleaned)
        cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def split_sentences(text: str) -> list[str]:
    """Split cleaned text into speakable sentence units."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    parts = _SENTENCE_END_RE.split(cleaned)
    return [p.strip() for p in parts if p and p.strip()]


@dataclass
class SentenceTTSBuffer:
    """Accumulate streamed text deltas into speakable sentence chunks."""

    min_chars: int = 24
    _pending: str = ""
    _emitted: list[str] = field(default_factory=list)

    def push(self, delta: str) -> list[str]:
        if not delta:
            return []
        self._pending += delta
        ready: list[str] = []
        # Only consider completed sentences (ending punctuation).
        while True:
            match = re.search(r"[.!?…]\s|\n", self._pending)
            if not match:
                break
            end = match.end()
            chunk = self._pending[:end].strip()
            self._pending = self._pending[end:]
            if len(chunk) >= self.min_chars:
                ready.append(chunk)
                self._emitted.append(chunk)
            elif chunk:
                # Hold short fragments until min size by re-prefixing next cycle.
                self._pending = chunk + " " + self._pending
                break
        return ready

    def flush(self) -> list[str]:
        leftover = self._pending.strip()
        self._pending = ""
        if leftover:
            self._emitted.append(leftover)
            return [leftover]
        return []

    @property
    def emitted(self) -> list[str]:
        return list(self._emitted)


class TTSStrategy:
    """Synthesize Brain responses with full or sentence-buffered strategies."""

    def __init__(
        self,
        *,
        config: TTSStrategyConfig | None = None,
        registry: TextToSpeechRegistry | None = None,
        provider_id: str = "mock",
        locale: str = "fr-FR",
        voice: str = "default",
        speed: float = 0.95,
        volume: float = 1.0,
    ) -> None:
        self.config = config or TTSStrategyConfig()
        self._registry = registry
        self.provider_id = provider_id
        self.locale = locale
        self.voice = voice
        self.speed = speed
        self.volume = volume
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def reset_cancel(self) -> None:
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def resolve_voice(self) -> str:
        return select_voice_for_locale(
            self.locale,
            configured_voice=self.voice,
            config=self.config,
        )

    def synthesize_full(self, text: str) -> SynthesisResult | None:
        cleaned = clean_text_for_speech(text, config=self.config)
        if not cleaned or self._cancelled:
            return None
        return synthesize_speech(
            cleaned,
            locale=self.locale,
            voice=self.resolve_voice(),
            speed=self.speed,
            volume=self.volume,
            provider_id=self.provider_id,
            registry=self._registry,
        )

    def iter_sentence_audio(
        self,
        text: str,
        *,
        on_chunk: Callable[[str, SynthesisResult], None] | None = None,
    ) -> Iterator[tuple[str, SynthesisResult]]:
        """Yield (sentence, audio) in order for sentence-buffered TTS."""
        cleaned = clean_text_for_speech(text, config=self.config)
        sentences = split_sentences(cleaned)
        if not sentences and cleaned:
            sentences = [cleaned]
        for sentence in sentences:
            if self._cancelled:
                break
            if len(sentence) < self.config.min_text_chunk_chars and sentence is not sentences[-1]:
                # Merge tiny middle fragments conservatively by skipping yield
                # — still preserve order by synthesizing combined leftovers.
                continue
            result = synthesize_speech(
                sentence,
                locale=self.locale,
                voice=self.resolve_voice(),
                speed=self.speed,
                volume=self.volume,
                provider_id=self.provider_id,
                registry=self._registry,
            )
            if on_chunk is not None:
                on_chunk(sentence, result)
            yield sentence, result

    def synthesize_streaming_deltas(
        self,
        deltas: list[str],
        *,
        on_chunk: Callable[[str, SynthesisResult], None] | None = None,
    ) -> list[tuple[str, SynthesisResult]]:
        """Sentence-buffer a list of text deltas; preserves response order."""
        buffer = SentenceTTSBuffer(min_chars=self.config.min_text_chunk_chars)
        outputs: list[tuple[str, SynthesisResult]] = []
        for delta in deltas:
            if self._cancelled:
                break
            for sentence in buffer.push(delta):
                cleaned = clean_text_for_speech(sentence, config=self.config)
                if not cleaned:
                    continue
                result = synthesize_speech(
                    cleaned,
                    locale=self.locale,
                    voice=self.resolve_voice(),
                    speed=self.speed,
                    volume=self.volume,
                    provider_id=self.provider_id,
                    registry=self._registry,
                )
                outputs.append((cleaned, result))
                if on_chunk is not None:
                    on_chunk(cleaned, result)
        for sentence in buffer.flush():
            if self._cancelled:
                break
            cleaned = clean_text_for_speech(sentence, config=self.config)
            if not cleaned:
                continue
            result = synthesize_speech(
                cleaned,
                locale=self.locale,
                voice=self.resolve_voice(),
                speed=self.speed,
                volume=self.volume,
                provider_id=self.provider_id,
                registry=self._registry,
            )
            outputs.append((cleaned, result))
            if on_chunk is not None:
                on_chunk(cleaned, result)
        return outputs

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.config.mode.value,
            "min_text_chunk_chars": self.config.min_text_chunk_chars,
            "locale": self.locale,
            "voice": self.resolve_voice(),
            "provider_id": self.provider_id,
        }
