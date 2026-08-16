"""访问一个真实公开网页，并保存满足最终评测要求的可审计 Trace 摘要。"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import uuid4

from localdesk.desktop.browser import HttpBrowserAdapter
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.reporting import KnowledgeReportWorkflow
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.skills.document import DocumentSkill
from localdesk.desktop.skills.knowledge import KnowledgeSkill
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig
from run_baseline import REPOSITORY_ROOT, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://example.org/")
    args = parser.parse_args()
    domain = urlparse(args.url).hostname
    if not domain:
        raise ValueError("URL 缺少域名")

    run_root = REPOSITORY_ROOT / ".localdesk" / f"real-web-{uuid4().hex[:8]}"
    sources, output, tasks = run_root / "sources", run_root / "output", run_root / "tasks"
    for directory in (sources, output, tasks):
        directory.mkdir(parents=True)
    (sources / "context.md").write_text("Public web evidence capture acceptance test.", encoding="utf-8")
    workspace = DesktopWorkspace(WorkspaceConfig(
        read_roots=[sources], output_root=output, task_root=tasks, browser_allowed_domains=[domain],
    ))
    service = DesktopTaskService(DesktopPolicyGuard(workspace), TaskTraceStore(workspace))
    workflow = KnowledgeReportWorkflow(service, KnowledgeSkill(workspace), DocumentSkill(workspace))
    task = service.create_task("Public web evidence capture acceptance test")
    workflow.prepare(task, "real-web-evidence.md", browser=HttpBrowserAdapter(), web_urls=[args.url], auto_deliver=True)
    events = service.trace_store.load_events(task.task_id)
    captured = next(event for event in events if event["event_type"] == "web_evidence_captured")
    result = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "task_id": task.task_id,
        "status": task.status.value,
        "trace_dir": str(workspace.task_dir(task.task_id)),
        "artifact": task.artifacts[0].final_path,
        "web_evidence": captured["payload"],
        "note": "This is a real public HTTPS read; no login, form submission, cookie reuse, or external write was performed.",
    }
    target = REPOSITORY_ROOT / "evaluation" / "results" / "real_public_web_trace.json"
    write_json(target, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if task.status.value == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
