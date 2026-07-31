"""Run the public, local-only weekly AI briefing demonstration.

Usage: ``python -m localdesk.desktop.weekly_briefing_demo``.
The command only reads the three explicitly listed public URLs and writes staged
artifacts below ``.localdesk/weekly-ai-briefing-demo``.  It never sends email.
"""
from __future__ import annotations

import json
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

from localdesk.desktop.browser import WebChunk
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.weekly_briefing import NewsSource, WeeklyBriefingWorkflow
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig


DEMO_SOURCES = [
    NewsSource(
        "model",
        "Microsoft Discovery 将 AI 模型、仿真与科研数据工作流整合",
        "2026-07-22",
        "https://blogs.microsoft.com/blog/2026/07/22/powering-americas-genesis-mission-microsofts-commitment-to-scientific-discovery/",
        "Microsoft 介绍了一个将 AI 模型、仿真、数据与实验流程连接起来的科研平台，用于加速科学发现。",
        "模型能力只有与领域数据、可复现过程和受治理的工作流结合，才能稳定转化为业务价值。",
    ),
    NewsSource(
        "agent_product",
        "Microsoft 为科研工作流引入 Agentic Memory 与自主实验室编排",
        "2026-07-22",
        "https://blogs.microsoft.com/blog/2026/07/22/powering-americas-genesis-mission-microsofts-commitment-to-scientific-discovery/",
        "该产品还描述了自主实验室编排和 Agentic Memory，并将其放在受治理的科研工作流中。",
        "Agent 产品的价值来自领域工作流集成和可检查的记忆，而不是单纯增加聊天入口。",
    ),
    NewsSource(
        "industry",
        "Microsoft 与 AMD 扩展 Azure AI 和高性能计算基础设施",
        "2026-07-20",
        "https://blogs.microsoft.com/blog/2026/07/20/microsoft-expands-azure-ai-and-hpc-infrastructure-with-amd/",
        "Microsoft 宣布扩展 Azure AI 与高性能计算基础设施，并指出 AI 与 Agent 工作负载正在增长。",
        "当 Agent 工作负载走向规模化，基础设施供给与成本会和模型能力一样成为产品约束。",
    ),
]


class PublicSourceSnapshotAdapter:
    """Explicit, immutable public-source snapshots for a reproducible offline demo.

    The normal product path uses ``HttpBrowserAdapter``.  This demo adapter is
    deliberately labelled in Trace because the current desktop environment's
    HTTPS proxy rejects the direct requests; it never pretends to be a live
    browser fetch.
    """
    source_mode = "manual_public_snapshot"

    def __init__(self, sources: list[NewsSource]) -> None:
        self.sources = {source.url: source for source in sources}

    def open(self, url: str) -> WebChunk:
        source = self.sources[url]
        text = f"{source.title}. {source.summary} {source.value}"
        return WebChunk(
            chunk_id=f"snapshot:{hashlib.sha256(url.encode()).hexdigest()[:12]}",
            url=url,
            title=source.title,
            text=text,
            accessed_at=datetime.now(UTC).isoformat(),
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )


def run_demo(root: Path | None = None) -> dict:
    root = (root or Path.cwd() / ".localdesk" / "weekly-ai-briefing-demo").resolve()
    sources, output, tasks = root / "sources", root / "deliveries", root / "tasks"
    for directory in (sources, output, tasks):
        directory.mkdir(parents=True, exist_ok=True)
    workspace = DesktopWorkspace(WorkspaceConfig(
        read_roots=[sources], output_root=output, task_root=tasks,
        browser_allowed_domains=["openai.com", "blogs.microsoft.com"],
    ))
    traces = TaskTraceStore(workspace)
    service = DesktopTaskService(DesktopPolicyGuard(workspace), traces)
    workflow = WeeklyBriefingWorkflow(workspace, traces, browser=PublicSourceSnapshotAdapter(DEMO_SOURCES))
    start, end = date(2026, 7, 20), date(2026, 7, 26)
    task = workflow.create_task(service, start, end)
    result = workflow.run(task.task_id, start, end, DEMO_SOURCES)
    return {
        "task_id": task.task_id,
        "task_status": task.status.value,
        "root": str(root),
        "pptx": str(result["pptx"]),
        "pdf": str(result["pdf"]),
        "email": str(result["email"]),
        "confirmation": str(result["confirmation"]),
        "review": {"approved": result["review"].approved, "findings": result["review"].findings},
        "trace": str(workspace.task_dir(task.task_id) / "events.jsonl"),
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
