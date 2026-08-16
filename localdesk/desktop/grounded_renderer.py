from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from localdesk.client import LLMClient
from localdesk.conversation import ConversationManager
from localdesk.desktop.skills.knowledge import SourceChunk
from localdesk.tools.base import TextDelta, ToolCallComplete, ToolCallStart


class GroundedRenderError(ValueError):
    pass


class GroundedSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=4000)
    citation_ids: list[str] = Field(min_length=1, max_length=8)


class GroundedReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    sections: list[GroundedSection] = Field(min_length=1, max_length=12)


@dataclass(frozen=True)
class GroundedRenderResult:
    report: GroundedReport
    raw_json: str


class GroundedLLMRenderer:
    """只向 LLM 提供本次检索得到的带 citation_id 的文本片段。"""

    def __init__(self, client: LLMClient, timeout_seconds: float = 45.0) -> None:
        self.client = client
        self.timeout_seconds = timeout_seconds

    async def render(self, query: str, chunks: list[SourceChunk]) -> GroundedRenderResult:
        if not chunks:
            raise GroundedRenderError("没有可供 LLM 使用的检索片段")
        allowed = {chunk.chunk_id for chunk in chunks}
        payload = {"task": query, "sources": [{"citation_id": chunk.chunk_id, "text": chunk.text} for chunk in chunks]}
        conv = ConversationManager()
        conv.add_user_message(json.dumps(payload, ensure_ascii=False))
        system = (
            "Return JSON only. You are a grounded report renderer, not an agent. "
            "Use only sources supplied by the user. Do not read files, call tools, choose paths, or mention unsupplied facts. "
            "Schema: {title:string,sections:[{heading:string,content:string,citation_ids:[string,...]}]}. "
            "Every section must cite one or more supplied citation_ids."
        )
        text: list[str] = []
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async for event in self.client.stream(conv, system=system, tools=None):
                    if isinstance(event, TextDelta):
                        text.append(event.text)
                    elif isinstance(event, (ToolCallStart, ToolCallComplete)):
                        raise GroundedRenderError("LLM 不允许调用工具")
        except TimeoutError as exc:
            raise GroundedRenderError("LLM 渲染超时") from exc
        except GroundedRenderError:
            raise
        except Exception as exc:
            raise GroundedRenderError(f"LLM 渲染异常: {exc}") from exc
        raw = "".join(text)
        try:
            report = GroundedReport.model_validate_json(raw)
        except ValidationError as exc:
            raise GroundedRenderError(f"LLM 输出不是合法结构化报告: {exc.errors()[0]['msg']}") from exc
        for section in report.sections:
            unknown = set(section.citation_ids) - allowed
            if unknown:
                raise GroundedRenderError(f"LLM 使用了不存在的 citation_id: {sorted(unknown)}")
            if not section.citation_ids:
                raise GroundedRenderError("LLM 生成了无引用的结论")
        return GroundedRenderResult(report=report, raw_json=raw)
