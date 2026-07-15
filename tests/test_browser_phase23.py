# =====================================
# Titan Browser Phase 23.0 Tests
# =====================================

"""Tests for Phase 23.0 Browser Intelligence — cognitive web exploration."""

from __future__ import annotations

import json

import pytest

from api.memory_activity import format_memory_activity
from api.tool_activity import format_tool_activity, normalize_tool_key
from brain.pipeline.context_bundle import ThinkContext
from brain.pipeline.stages import ThinkPipeline
from memory.models import RetrievalResult
from tools.audit.tool_audit_models import ToolAuditEvent
from tools.browser_intelligence import BrowserIntelligenceService
from tools.browser_tool import BrowserTool
from tools.connectors.browser_connector import BrowserConnector
from tools.connectors.browser_models import BrowserSource
from tools.decision.browser_decision import BrowserDecision, BrowserDecisionEngine
from tools.tool_result import ToolResult


def _fetcher(url: str, timeout: float) -> tuple[str, str, tuple[str, ...]]:
    _ = timeout
    html = (
        f"<html><head><title>Page — {url}</title></head>"
        f"<body><p>Contenu visible pour {url}.</p></body></html>"
    )
    return url, html, ()


def _search_fn(query: str, max_results: int) -> list[tuple[str, str, str]]:
    _ = query
    return [
        ("Alpha Source", "https://alpha.example/article", "Snippet alpha."),
        ("Beta Source", "https://beta.example/article", "Snippet beta."),
    ][:max_results]


@pytest.fixture
def connector() -> BrowserConnector:
    return BrowserConnector(enabled=True, fetcher=_fetcher)


@pytest.fixture
def intelligence(connector: BrowserConnector) -> BrowserIntelligenceService:
    return BrowserIntelligenceService(connector, search_fn=_search_fn)


def test_browser_source_citation_label_truncates() -> None:
    source = BrowserSource(
        title="A" * 80,
        url="https://example.com",
        excerpt="text",
        index=1,
    )
    assert len(source.citation_label()) <= 64


def test_research_web_collects_sources(intelligence: BrowserIntelligenceService) -> None:
    result = intelligence.research_web("intelligence artificielle")
    assert result.status == "ok"
    assert len(result.sources) == 2
    assert "[1]" in result.citations_block()
    assert "Alpha Source" in result.format_for_tool()


def test_compare_sources_requires_two_urls(intelligence: BrowserIntelligenceService) -> None:
    result = intelligence.compare_sources(["https://one.example"])
    assert result.status == "insufficient_urls"


def test_compare_sources_reads_multiple_pages(intelligence: BrowserIntelligenceService) -> None:
    result = intelligence.compare_sources(
        ["https://one.example", "https://two.example"],
    )
    assert result.status == "ok"
    assert len(result.sources) == 2


def test_browser_decision_routes_research_web(connector: BrowserConnector) -> None:
    engine = BrowserDecisionEngine(connector)
    result = engine.decide("Recherche sur le web des dernières nouvelles IA")
    assert result.decision == BrowserDecision.RESEARCH_WEB
    assert result.tool_params_dict()["action"] == "research_web"


def test_browser_decision_routes_compare_sources(connector: BrowserConnector) -> None:
    engine = BrowserDecisionEngine(connector)
    message = (
        "Compare les sources https://a.example/page "
        "et https://b.example/page"
    )
    result = engine.decide(message)
    assert result.decision == BrowserDecision.COMPARE_SOURCES


def test_browser_tool_research_web() -> None:
    connector = BrowserConnector(enabled=True, fetcher=_fetcher)
    tool = BrowserTool(
        connector=connector,
        intelligence=BrowserIntelligenceService(connector, search_fn=_search_fn),
    )
    result = tool.run(action="research_web", query="Titan AI")
    assert result.success
    assert result.metadata["exploration"] is True
    assert len(result.metadata["sources"]) == 2
    assert "Références" in result.data


def test_track_browser_exploration_from_tool_results() -> None:
    ctx = ThinkContext(user_message="test")
    ctx.tool_results = [
        ToolResult(
            tool_name="browser",
            success=True,
            data="Exploration",
            metadata={
                "exploration": True,
                "citations": ["Alpha Source", "Beta Source"],
                "sources": [
                    {"title": "Alpha Source", "url": "https://alpha.example", "excerpt": "a"},
                    {"title": "Beta Source", "url": "https://beta.example", "excerpt": "b"},
                ],
            },
        ),
    ]
    ThinkPipeline._track_browser_exploration(ctx)
    assert ctx.browser_exploring is True
    assert ctx.browser_source_labels == ["Alpha Source", "Beta Source"]


def test_format_tool_activity_exploration_timeline() -> None:
    ctx = ThinkContext(
        user_message="Recherche web",
        browser_exploring=True,
        browser_source_labels=["Alpha Source"],
    )
    events = [
        ToolAuditEvent.build(event_type="started", tool_name="browser", run_id="run-b"),
        ToolAuditEvent.build(
            event_type="completed",
            tool_name="browser",
            run_id="run-b",
            success=True,
        ),
    ]
    activity = format_tool_activity(events, ctx)
    assert activity[0]["title"] == "Exploration web"
    assert activity[0]["steps"] == [
        "Navigation web",
        "Recherche",
        "Analyse",
        "Synthèse",
    ]
    assert activity[0]["cognitive_state"] == "exploration"
    assert "Source · Alpha Source" in activity[0]["sources"]
    serialized = json.dumps(activity)
    assert "playwright" not in serialized.lower()


def test_format_memory_activity_includes_browser_exploration() -> None:
    ctx = ThinkContext(
        user_message="Explore le web",
        retrieval_result=RetrievalResult(
            text="Aucune mémoire pertinente trouvée.",
            items=[],
            user="Nolan",
        ),
        browser_exploring=True,
        browser_source_labels=["Alpha Source"],
    )
    activity = format_memory_activity(ctx)
    sources = {record["source"] for record in activity}
    assert "browser" in sources
    browser_recall = next(
        record for record in activity if record.get("run_id") == "mem-recall-browser"
    )
    assert "Source · Alpha Source" in browser_recall["cards"]


def test_normalize_tool_key_browser() -> None:
    assert normalize_tool_key("browser_research") == "browser"
