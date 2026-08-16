"""Run the weekly briefing with frozen official RSS feeds and live articles."""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.weekly_briefing import WeeklyBriefingWorkflow
from localdesk.desktop.weekly_research import OfficialWeeklyResearch, WeeklyResearchError
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig


DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "evaluation" / "frozen_weekly_sources_v3.json"


def _runtime(root: Path) -> tuple[DesktopWorkspace, TaskTraceStore, DesktopTaskService]:
    sources, output, tasks = root / "sources", root / "deliveries", root / "tasks"
    for directory in (sources, output, tasks):
        directory.mkdir(parents=True, exist_ok=True)
    workspace = DesktopWorkspace(WorkspaceConfig(
        read_roots=[sources],
        output_root=output,
        task_root=tasks,
        browser_allowed_domains=["deepmind.google", "openai.com", "blogs.microsoft.com"],
    ))
    traces = TaskTraceStore(workspace)
    service = DesktopTaskService(DesktopPolicyGuard(workspace), traces)
    return workspace, traces, service


def run_live_demo(
    root: Path | None = None,
    *,
    start: date | None = None,
    end: date | None = None,
    config_path: Path = DEFAULT_CONFIG,
    main_agent_plan: dict[str, object] | None = None,
    user_query: str | None = None,
) -> dict[str, object]:
    root = (root or Path.cwd() / ".localdesk" / "weekly-ai-briefing-live").resolve()
    end = end or date.today()
    start = start or (end - timedelta(days=6))
    workspace, traces, service = _runtime(root)
    workflow = WeeklyBriefingWorkflow(workspace, traces)
    task = workflow.create_task(service, start, end, user_query=user_query)
    if main_agent_plan is not None:
        traces.append(task.task_id, "main_agent_planned", main_agent_plan)
    research_dir = workspace.task_dir(task.task_id) / "staging" / "research"
    try:
        research = OfficialWeeklyResearch(config_path).run(start, end, research_dir)
    except Exception as exc:
        service.fail(task, str(exc), event_type="weekly_live_research_failed")
        return {
            "task_id": task.task_id,
            "task_status": task.status.value,
            "root": str(root),
            "error": str(exc),
            "research_plan": str(research_dir / "research_plan.json"),
            "research_evidence": str(research_dir / "research_evidence.json"),
            "trace": str(workspace.task_dir(task.task_id) / "events.jsonl"),
        }
    traces.append(task.task_id, "weekly_live_research_completed", {
        "plan_version": research.plan.version,
        "feed_read_count": len(research.feed_reads),
        "article_read_count": len(research.article_reads),
        "source_modes": sorted({str(item["source_mode"]) for item in research.article_reads}),
        "live_html_count": sum(item["source_mode"] == "official_rss_plus_live_html" for item in research.article_reads),
        "rss_fallback_count": sum(item["source_mode"] == "official_rss_item_fallback" for item in research.article_reads),
    })
    workflow.browser = research.browser
    result = workflow.run(service, task, start, end, research.sources)
    return {
        "task_id": task.task_id,
        "task_status": task.status.value,
        "root": str(root),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "selected_cards": len(result["cards"]),
        "pptx": str(result["pptx"]),
        "pdf": str(result["pdf"]),
        "email": str(result["email"]),
        "confirmation": str(result["confirmation"]),
        "research_plan": str(research_dir / "research_plan.json"),
        "research_evidence": str(research_dir / "research_evidence.json"),
        "trace": str(workspace.task_dir(task.task_id) / "events.jsonl"),
    }


def confirm_live_demo(task_id: str, root: Path | None = None, *, approved: bool = True) -> dict[str, object]:
    root = (root or Path.cwd() / ".localdesk" / "weekly-ai-briefing-live").resolve()
    workspace, traces, service = _runtime(root)
    task = traces.load_task_object(task_id)
    WeeklyBriefingWorkflow(workspace, traces).confirm_and_deliver(service, task, approved=approved)
    return {
        "task_id": task.task_id,
        "task_status": task.status.value,
        "artifacts": [artifact.final_path for artifact in task.artifacts],
        "trace": str(workspace.task_dir(task.task_id) / "events.jsonl"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run or confirm the live-source weekly briefing demo.")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--confirm", metavar="TASK_ID")
    parser.add_argument("--reject", action="store_true")
    args = parser.parse_args()
    if args.confirm:
        payload = confirm_live_demo(args.confirm, args.root, approved=not args.reject)
    else:
        payload = run_live_demo(args.root, start=args.start, end=args.end, config_path=args.config)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload.get("task_status") == "failed":
        raise SystemExit(2)
