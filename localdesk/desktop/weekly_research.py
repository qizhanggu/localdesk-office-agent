"""Frozen, auditable RSS discovery plus official article reading."""
from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from localdesk.desktop.browser import BrowserAdapter, HttpBrowserAdapter, WebChunk
from localdesk.desktop.weekly_briefing import NewsSource


class WeeklyResearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class OfficialFeedSource:
    source_id: str
    category: str
    feed_url: str
    article_domains: tuple[str, ...]
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class FeedItem:
    source_id: str
    category: str
    title: str
    url: str
    published: str
    feed_excerpt: str


@dataclass(frozen=True)
class ResearchPlan:
    version: str
    frozen_at: str
    start: str
    end: str
    generated_at: str
    agents: list[dict[str, object]]
    rules: list[str]


@dataclass(frozen=True)
class ResearchRun:
    plan: ResearchPlan
    sources: list[NewsSource]
    browser: BrowserAdapter
    feed_reads: list[dict[str, object]]
    article_reads: list[dict[str, object]]


class RecordedBrowserAdapter:
    source_mode = "official_rss_plus_live_html"

    def __init__(self, pages: dict[str, WebChunk], modes: dict[str, str]) -> None:
        self.pages = dict(pages)
        self.modes = dict(modes)

    def open(self, url: str) -> WebChunk:
        try:
            page = self.pages[url]
            self.source_mode = self.modes[url]
            return page
        except KeyError as exc:
            raise WeeklyResearchError(f"研究缓存中没有已读取文章：{url}") from exc


class OfficialWeeklyResearch:
    def __init__(
        self,
        config_path: Path,
        *,
        feed_client: httpx.Client | None = None,
        article_browser: BrowserAdapter | None = None,
    ) -> None:
        self.config_path = config_path.resolve()
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.version = str(raw["version"])
        self.frozen_at = str(raw["frozen_at"])
        self.max_items = int(raw["max_items_per_category"])
        self.sources = [
            OfficialFeedSource(
                source_id=str(item["source_id"]),
                category=str(item["category"]),
                feed_url=str(item["feed_url"]),
                article_domains=tuple(str(value) for value in item["article_domains"]),
                keywords=tuple(str(value).casefold() for value in item["keywords"]),
            )
            for item in raw["sources"]
        ]
        self.feed_client = feed_client
        allowed_domains = tuple(sorted({domain for source in self.sources for domain in source.article_domains}))
        self.article_browser = article_browser or HttpBrowserAdapter(
            timeout_seconds=20,
            allowed_redirect_domains=allowed_domains,
        )

    def plan(self, start: date, end: date) -> ResearchPlan:
        if end < start:
            raise ValueError("研究时间窗的结束日期不能早于开始日期。")
        return ResearchPlan(
            version=self.version,
            frozen_at=self.frozen_at,
            start=start.isoformat(),
            end=end.isoformat(),
            generated_at=datetime.now(UTC).isoformat(),
            agents=[
                {
                    "agent": source.category,
                    "source_id": source.source_id,
                    "feed_url": source.feed_url,
                    "article_domains": list(source.article_domains),
                    "keywords": list(source.keywords),
                    "max_items": self.max_items,
                    "steps": ["读取冻结 RSS", "按时间窗和关键词筛选", "读取官方原文", "保存证据"],
                }
                for source in self.sources
            ],
            rules=[
                "来源集合在运行前冻结",
                "只接受 HTTPS 和配置中的官方文章域名",
                "优先读取官方原文；正文失败时，只允许使用带正文摘要的官方 RSS 条目并显式标记回退",
                "任一研究方向没有合格文章时失败，不自动改来源或回退到预置答案",
                "摘要仅做确定性原文截取，不宣称 LLM 生成",
            ],
        )

    def run(self, start: date, end: date, output_dir: Path) -> ResearchRun:
        output_dir.mkdir(parents=True, exist_ok=True)
        plan = self.plan(start, end)
        (output_dir / "research_plan.json").write_text(
            json.dumps(asdict(plan), ensure_ascii=False, indent=2), encoding="utf-8",
        )
        feed_reads: list[dict[str, object]] = []
        article_reads: list[dict[str, object]] = []
        selected_sources: list[NewsSource] = []
        pages: dict[str, WebChunk] = {}
        modes: dict[str, str] = {}
        used_urls: set[str] = set()
        failures: list[dict[str, str]] = []
        feed_cache: dict[str, tuple[bytes, dict[str, object]]] = {}

        for source in self.sources:
            try:
                items, feed_read = self._discover(source, start, end, feed_cache)
                feed_reads.append(feed_read)
                accepted = 0
                for item in items:
                    if accepted >= self.max_items:
                        break
                    if item.url in used_urls:
                        continue
                    try:
                        page = self.article_browser.open(item.url)
                        self._validate_article_url(page.url, source.article_domains)
                        excerpt = _clean_excerpt(page.text, 360)
                        if len(excerpt) < 80:
                            raise WeeklyResearchError("原文可提取内容过短")
                        pages[item.url] = page
                        modes[item.url] = "official_rss_plus_live_html"
                        summary = excerpt[:220]
                        selected_sources.append(NewsSource(
                            category=source.category,
                            title=item.title,
                            published=item.published,
                            url=item.url,
                            summary=summary,
                            value="该条目来自冻结官方来源；业务影响仍需人工结合场景判断。",
                        ))
                        article_reads.append({
                            "source_id": source.source_id,
                            "category": source.category,
                            "url": page.url,
                            "title": page.title,
                            "published": item.published,
                            "accessed_at": page.accessed_at,
                            "content_hash": page.content_hash,
                            "quote": excerpt,
                            "source_mode": "official_rss_plus_live_html",
                        })
                        accepted += 1
                    except Exception as exc:
                        failures.append({"source_id": source.source_id, "url": item.url, "error": str(exc)})
                        if len(item.feed_excerpt) < 80:
                            continue
                        feed_text = f"{item.title}. {item.feed_excerpt}"
                        page = WebChunk(
                            chunk_id=f"rss:{source.source_id}:{hashlib.sha256(item.url.encode()).hexdigest()[:12]}",
                            url=source.feed_url,
                            title=item.title,
                            text=feed_text,
                            accessed_at=str(feed_read["accessed_at"]),
                            content_hash=str(feed_read["content_hash"]),
                        )
                        pages[item.url] = page
                        modes[item.url] = "official_rss_item_fallback"
                        summary = item.feed_excerpt[:220]
                        selected_sources.append(NewsSource(
                            category=source.category,
                            title=item.title,
                            published=item.published,
                            url=item.url,
                            summary=summary,
                            value="该条目来自冻结官方 RSS；正文页未成功读取，业务影响需人工判断。",
                        ))
                        article_reads.append({
                            "source_id": source.source_id,
                            "category": source.category,
                            "article_url": item.url,
                            "evidence_url": source.feed_url,
                            "title": item.title,
                            "published": item.published,
                            "accessed_at": feed_read["accessed_at"],
                            "content_hash": feed_read["content_hash"],
                            "quote": feed_text,
                            "source_mode": "official_rss_item_fallback",
                        })
                        accepted += 1
                    if accepted:
                        used_urls.add(item.url)
                if accepted == 0:
                    failures.append({"source_id": source.source_id, "url": source.feed_url, "error": "该方向没有成功读取的官方文章"})
            except Exception as exc:
                failures.append({"source_id": source.source_id, "url": source.feed_url, "error": str(exc)})

        report = {
            "plan_version": plan.version,
            "feed_reads": feed_reads,
            "article_reads": article_reads,
            "failures": failures,
        }
        (output_dir / "research_evidence.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        covered = {item.category for item in selected_sources}
        missing = sorted({source.category for source in self.sources} - covered)
        if missing:
            raise WeeklyResearchError(
                "真实研究未覆盖全部方向：" + ", ".join(missing) + "；详情见 research_evidence.json"
            )
        return ResearchRun(plan, selected_sources, RecordedBrowserAdapter(pages, modes), feed_reads, article_reads)

    def _discover(
        self,
        source: OfficialFeedSource,
        start: date,
        end: date,
        feed_cache: dict[str, tuple[bytes, dict[str, object]]] | None = None,
    ) -> tuple[list[FeedItem], dict[str, object]]:
        cache = feed_cache if feed_cache is not None else {}
        if source.feed_url in cache:
            body, base_read = cache[source.feed_url]
            items = self._parse_feed(source, body, start, end)
            return items, {**base_read, "source_id": source.source_id, "category": source.category, "candidate_count": len(items), "cache_hit": True}
        owns_client = self.feed_client is None
        client = self.feed_client or httpx.Client(follow_redirects=True, timeout=20)
        try:
            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    response = client.get(source.feed_url, headers={"User-Agent": "LocalDesk/1.0 RSS research"})
                    response.raise_for_status()
                    final_url = str(response.url)
                    self._validate_feed_url(final_url, source.feed_url)
                    body = response.content
                    if len(body) > 2_000_000:
                        raise WeeklyResearchError("RSS 超过 2MB 上限")
                    break
                except (httpx.HTTPError, WeeklyResearchError) as exc:
                    last_error = exc
                    if attempt < 3:
                        time.sleep(0.5 * attempt)
            else:
                raise WeeklyResearchError(f"RSS 读取失败（3 次尝试）：{last_error}")
        except httpx.HTTPError as exc:
            raise WeeklyResearchError(f"RSS 读取失败：{exc}") from exc
        finally:
            if owns_client:
                client.close()
        items = self._parse_feed(source, body, start, end)
        base_read = {
            "feed_url": source.feed_url,
            "final_url": final_url,
            "accessed_at": datetime.now(UTC).isoformat(),
            "content_hash": hashlib.sha256(body).hexdigest(),
        }
        cache[source.feed_url] = (body, base_read)
        return items, {**base_read, "source_id": source.source_id, "category": source.category, "candidate_count": len(items), "cache_hit": False}

    @staticmethod
    def _parse_feed(source: OfficialFeedSource, body: bytes, start: date, end: date) -> list[FeedItem]:
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise WeeklyResearchError(f"RSS XML 解析失败：{exc}") from exc
        raw_items = list(root.findall(".//item"))
        if not raw_items:
            raw_items = [node for node in root.iter() if _local_name(node.tag) == "entry"]
        parsed: list[FeedItem] = []
        for node in raw_items:
            title = _child_text(node, "title")
            link = _entry_link(node)
            published_raw = _child_text(node, "pubDate") or _child_text(node, "published") or _child_text(node, "updated")
            description = _child_text(node, "description") or _child_text(node, "summary") or _child_text(node, "content")
            published = _parse_date(published_raw)
            searchable = f"{title} {description}".casefold()
            if not title or not link or published is None or not (start <= published <= end):
                continue
            if source.keywords and not any(keyword in searchable for keyword in source.keywords):
                continue
            OfficialWeeklyResearch._validate_article_url(link, source.article_domains)
            parsed.append(FeedItem(
                source_id=source.source_id,
                category=source.category,
                title=title.strip(),
                url=link.strip(),
                published=published.isoformat(),
                feed_excerpt=_clean_excerpt(description, 280),
            ))
        return sorted(parsed, key=lambda item: (item.published, item.title), reverse=True)

    @staticmethod
    def _validate_feed_url(final_url: str, configured_url: str) -> None:
        final = urlparse(final_url)
        configured = urlparse(configured_url)
        if final.scheme != "https" or final.hostname != configured.hostname:
            raise WeeklyResearchError(f"RSS 重定向越出冻结域名：{final_url}")

    @staticmethod
    def _validate_article_url(url: str, domains: tuple[str, ...]) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or not any(host == domain or host.endswith("." + domain) for domain in domains):
            raise WeeklyResearchError(f"文章 URL 越出官方白名单：{url}")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, name: str) -> str:
    for child in node.iter():
        if _local_name(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def _entry_link(node: ET.Element) -> str:
    direct = _child_text(node, "link")
    if direct:
        return direct
    for child in node.iter():
        if _local_name(child.tag) == "link" and child.attrib.get("href"):
            if child.attrib.get("rel", "alternate") in {"alternate", ""}:
                return child.attrib["href"]
    return ""


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def _clean_excerpt(value: str, limit: int) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(without_tags.split())[:limit]
