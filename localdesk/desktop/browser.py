"""受控的公开网页读取 adapter。

第一版不处理登录、验证码、表单提交、下载或 Cookie；它只读取用户授权域名的
HTTPS 页面，并将网页视为不可信资料而不是可执行指令。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urljoin, urlparse

import httpx


class BrowserError(ValueError):
    pass


@dataclass(frozen=True)
class WebChunk:
    chunk_id: str
    url: str
    title: str
    text: str
    accessed_at: str
    content_hash: str = ""
    discovered_links: tuple[str, ...] = ()

    def citation(self) -> str:
        return f"{self.title} ({self.url}; accessed {self.accessed_at})"

    def excerpt(self, limit: int = 280) -> str:
        return " ".join(self.text.split())[:limit]


class BrowserAdapter(Protocol):
    def open(self, url: str) -> WebChunk: ...


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = "Untitled web page"
        self._in_title = False
        self._parts: list[str] = []
        self._links: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "template"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title = text
        self._parts.append(text)

    def result(self) -> tuple[str, str, list[str]]:
        return self.title, " ".join(self._parts), self._links


class HttpBrowserAdapter:
    """只读 HTTPS 页面；重定向必须由用户以最终 URL 重新授权。

    不自动跟随重定向是刻意的安全取舍：否则 Policy 虽然校验了原 URL，
    HTTP 客户端仍可能在未经过域名白名单检查的情况下访问另一个站点。
    """

    def __init__(
        self,
        timeout_seconds: float = 15,
        max_chars: int = 30_000,
        max_response_bytes: int = 1_000_000,
        client: httpx.Client | None = None,
        allowed_redirect_domains: tuple[str, ...] = (),
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_chars = max_chars
        self.max_response_bytes = max_response_bytes
        self.client = client
        self.allowed_redirect_domains = tuple(domain.casefold() for domain in allowed_redirect_domains)

    def open(self, url: str) -> WebChunk:
        owns_client = self.client is None
        client = self.client or httpx.Client()
        try:
            with client.stream(
                "GET",
                url,
                follow_redirects=bool(self.allowed_redirect_domains),
                timeout=self.timeout_seconds,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            ) as response:
                if self.allowed_redirect_domains:
                    for hop in [*response.history, response]:
                        parsed = urlparse(str(hop.url))
                        host = (parsed.hostname or "").casefold()
                        if parsed.scheme != "https" or not any(
                            host == domain or host.endswith("." + domain)
                            for domain in self.allowed_redirect_domains
                        ):
                            raise BrowserError(f"重定向越出官方来源白名单：{hop.url}")
                if response.is_redirect:
                    destination = response.headers.get("location", "unknown destination")
                    raise BrowserError(f"拒绝自动重定向到 {destination}; 请将最终 HTTPS URL 显式加入授权范围")
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "html" not in content_type and "text/plain" not in content_type:
                    raise BrowserError(f"拒绝非文本网页内容: {content_type or 'unknown'}")
                declared_size = response.headers.get("content-length")
                if declared_size:
                    try:
                        declared_bytes = int(declared_size)
                    except ValueError as exc:
                        raise BrowserError("网页返回了无效的 Content-Length") from exc
                    if declared_bytes > self.max_response_bytes:
                        raise BrowserError(f"网页内容超过 {self.max_response_bytes} 字节上限")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > self.max_response_bytes:
                        raise BrowserError(f"网页内容超过 {self.max_response_bytes} 字节上限")
                text_body = bytes(body).decode(response.encoding or "utf-8", errors="replace")
        except httpx.HTTPError as exc:
            raise BrowserError(f"网页读取失败: {exc}") from exc
        finally:
            if owns_client:
                client.close()
        parser = _TextExtractor()
        parser.feed(text_body)
        title, text, raw_links = parser.result()
        if not text:
            raise BrowserError("网页未提取到可用正文")
        links = []
        for raw_link in raw_links:
            candidate = urljoin(url, raw_link)
            parsed = urlparse(candidate)
            if parsed.scheme == "https" and parsed.netloc and candidate not in links:
                links.append(candidate)
        return WebChunk(
            chunk_id=f"web:{url}",
            url=url,
            title=title,
            text=text[: self.max_chars],
            accessed_at=datetime.now(UTC).isoformat(),
            content_hash=hashlib.sha256(text[: self.max_chars].encode("utf-8")).hexdigest(),
            discovered_links=tuple(links[:100]),
        )


class FakeBrowserAdapter:
    """离线测试 adapter：仅返回预先声明的公开页面。"""

    def __init__(self, pages: dict[str, WebChunk]) -> None:
        self.pages = pages

    def open(self, url: str) -> WebChunk:
        try:
            return self.pages[url]
        except KeyError as exc:
            raise BrowserError(f"Fake browser has no page for: {url}") from exc
