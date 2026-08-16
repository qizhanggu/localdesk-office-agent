import hashlib
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from localdesk.desktop.browser import FakeBrowserAdapter, WebChunk
from localdesk.desktop.weekly_research import OfficialWeeklyResearch, WeeklyResearchError


def _config(path: Path) -> Path:
    payload = {
        "version": "test-v1",
        "frozen_at": "2026-08-10",
        "max_items_per_category": 1,
        "sources": [
            {"source_id": "model", "category": "model", "feed_url": "https://model.example/feed.xml", "article_domains": ["model.example"], "keywords": ["model"]},
            {"source_id": "agent", "category": "agent_product", "feed_url": "https://agent.example/feed.xml", "article_domains": ["agent.example"], "keywords": ["agent"]},
            {"source_id": "industry", "category": "industry", "feed_url": "https://industry.example/feed.xml", "article_domains": ["industry.example"], "keywords": ["industry"]},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _feed(title: str, link: str, description: str = "evidence") -> bytes:
    return f"""<?xml version='1.0'?><rss><channel><item>
    <title>{title}</title><link>{link}</link>
    <pubDate>Tue, 04 Aug 2026 10:00:00 +0000</pubDate>
    <description>{description}</description></item></channel></rss>""".encode()


def _research(tmp_path: Path, *, omit_industry: bool = False) -> OfficialWeeklyResearch:
    feeds = {
        "model.example": _feed("Model release", "https://model.example/post", "model evidence"),
        "agent.example": _feed("Agent product", "https://agent.example/post", "agent evidence"),
        "industry.example": _feed("Adoption story" if omit_industry else "Industry adoption", "https://industry.example/post", "no matching term" if omit_industry else "industry evidence"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=feeds[request.url.host], request=request, headers={"content-type": "application/rss+xml"})

    pages = {}
    for host, title in (("model.example", "Model release"), ("agent.example", "Agent product"), ("industry.example", "Industry adoption")):
        url = f"https://{host}/post"
        text = f"{title} official article with enough source evidence to support a deterministic summary and quotation."
        pages[url] = WebChunk(
            f"web:{host}", url, title, text, "2026-08-10T00:00:00+00:00",
            hashlib.sha256(text.encode()).hexdigest(),
        )
    return OfficialWeeklyResearch(
        _config(tmp_path / "sources.json"),
        feed_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
        article_browser=FakeBrowserAdapter(pages),
    )


def test_frozen_rss_plan_and_article_evidence_are_saved(tmp_path: Path) -> None:
    output = tmp_path / "research"
    result = _research(tmp_path).run(date(2026, 8, 1), date(2026, 8, 7), output)
    assert {source.category for source in result.sources} == {"model", "agent_product", "industry"}
    assert len(result.feed_reads) == 3 and len(result.article_reads) == 3
    assert (output / "research_plan.json").is_file()
    evidence = json.loads((output / "research_evidence.json").read_text(encoding="utf-8"))
    assert evidence["failures"] == []
    assert all(len(item["content_hash"]) == 64 and item["quote"] for item in evidence["article_reads"])


def test_missing_category_fails_honestly_and_keeps_report(tmp_path: Path) -> None:
    output = tmp_path / "research"
    with pytest.raises(WeeklyResearchError, match="industry"):
        _research(tmp_path, omit_industry=True).run(date(2026, 8, 1), date(2026, 8, 7), output)
    report = json.loads((output / "research_evidence.json").read_text(encoding="utf-8"))
    assert report["failures"]
    assert (output / "research_plan.json").is_file()


def test_feed_article_domain_escape_is_rejected(tmp_path: Path) -> None:
    research = _research(tmp_path)
    source = research.sources[0]
    body = _feed("Model release", "https://evil.example/post", "model evidence")
    with pytest.raises(WeeklyResearchError, match="白名单"):
        research._parse_feed(source, body, date(2026, 8, 1), date(2026, 8, 7))
