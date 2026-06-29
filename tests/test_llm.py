# =====================================
# Titan LLM Error Handling Tests
# =====================================

"""Tests for LLM ask() retry and fallback behavior (P1-100–P1-102)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from openai import APIConnectionError, RateLimitError

from brain.llm import LLM, LLM_ERROR_MESSAGE


def _make_rate_limit_error() -> RateLimitError:
    response = MagicMock()
    response.request = MagicMock()
    response.status_code = 429
    return RateLimitError("rate limited", response=response, body={"error": "rate limit"})


def _make_connection_error() -> APIConnectionError:
    return APIConnectionError(request=MagicMock())


def _success_response(text: str = "Réponse du modèle.") -> MagicMock:
    response = MagicMock()
    response.output_text = text
    return response


@pytest.fixture
def llm() -> LLM:
    """LLM with mocked OpenAI client — no real API calls."""
    with patch("brain.llm.OpenAI"):
        instance = LLM()
    return instance


def test_ask_returns_output_text_on_success(llm: LLM) -> None:
    """P1-102: successful API call returns model output_text."""
    llm.client.responses.create.return_value = _success_response("Bonjour Nolan.")

    result = llm.ask("test prompt")

    assert result == "Bonjour Nolan."
    llm.client.responses.create.assert_called_once()


def test_ask_retries_transient_errors_then_succeeds(llm: LLM) -> None:
    """P1-101/P1-102: two transient failures then success returns response."""
    llm.client.responses.create.side_effect = [
        _make_rate_limit_error(),
        _make_connection_error(),
        _success_response("Après retry."),
    ]

    with patch("brain.llm.time.sleep") as mock_sleep:
        result = llm.ask("test prompt")

    assert result == "Après retry."
    assert llm.client.responses.create.call_count == 3
    assert mock_sleep.call_args_list == [((1,),), ((2,),)]


def test_ask_returns_french_fallback_after_max_retries(llm: LLM) -> None:
    """P1-100/P1-102: three consecutive transient failures return French message."""
    llm.client.responses.create.side_effect = [
        _make_rate_limit_error(),
        _make_connection_error(),
        _make_rate_limit_error(),
    ]

    with patch("brain.llm.time.sleep"):
        result = llm.ask("test prompt")

    assert result == LLM_ERROR_MESSAGE
    assert llm.client.responses.create.call_count == 3


def test_ask_does_not_retry_non_transient_errors(llm: LLM) -> None:
    """P1-101: non-transient errors fail immediately without retry."""
    llm.client.responses.create.side_effect = ValueError("bad request")

    with patch("brain.llm.time.sleep") as mock_sleep:
        result = llm.ask("test prompt")

    assert result == LLM_ERROR_MESSAGE
    assert llm.client.responses.create.call_count == 1
    mock_sleep.assert_not_called()
