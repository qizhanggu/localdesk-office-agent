"""可复现的 Phase 6A 求职材料 Demo：构造 JD + 构造履历 + 真实 LibreOffice。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from localdesk.desktop.browser import FakeBrowserAdapter, WebChunk
from localdesk.desktop.dashboard import render_task_board
from localdesk.desktop.docx_delivery import LibreOfficeDocxRenderer
from localdesk.desktop.job_materials import JobMaterialRequest, JobMaterialsWorkflow
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.skills.document import DocumentSkill
from localdesk.desktop.skills.knowledge import KnowledgeSkill
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig
from run_baseline import REPOSITORY_ROOT, write_json


def main() -> int:
    run_root = REPOSITORY_ROOT / ".localdesk" / f"phase6a-demo-{uuid4().hex[:8]}"
    sources, output, tasks = run_root / "sources", run_root / "output", run_root / "tasks"
    for directory in (sources, output, tasks):
        directory.mkdir(parents=True)
    (sources / "sample_resume.md").write_text(
        "Candidate built a Python Agent workflow with local RAG, tool policy, Trace, deterministic tests and DOCX validation.",
        encoding="utf-8",
    )
    url = "https://jobs.example.com/agent-developer"
    page = WebChunk(
        "web:sample-jd", url, "Sample Agent Developer",
        "The role requires Python, Agent, RAG, Docker, SQL, testing and end-to-end delivery.",
        datetime.now(UTC).isoformat(), "sample-content-hash", ("https://jobs.example.com/apply",),
    )
    workspace = DesktopWorkspace(WorkspaceConfig(
        read_roots=[sources], output_root=output, task_root=tasks, browser_allowed_domains=["jobs.example.com"],
    ))
    service = DesktopTaskService(DesktopPolicyGuard(workspace), TaskTraceStore(workspace))
    workflow = JobMaterialsWorkflow(service, KnowledgeSkill(workspace), DocumentSkill(workspace))
    task = service.create_task("Python Agent RAG testing end-to-end delivery")
    draft = workflow.prepare(
        task,
        JobMaterialRequest("Sample Company", "Agent Developer", url, "job-materials.md", "job-materials.docx", "突出完整闭环与测试证据"),
        FakeBrowserAdapter({url: page}),
        LibreOfficeDocxRenderer(),
    )
    events = service.trace_store.load_events(task.task_id)
    board = render_task_board(service.trace_store)
    result = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "task_id": task.task_id,
        "status": task.status.value,
        "markdown": draft.final_path,
        "artifacts": [artifact.__dict__ for artifact in task.artifacts],
        "event_types": [event["event_type"] for event in events],
        "trace_dir": str(workspace.task_dir(task.task_id)),
        "task_board": str(board),
        "uses_constructed_data": True,
        "uses_real_libreoffice": True,
    }
    target = REPOSITORY_ROOT / "evaluation" / "results" / "phase6a_demo.json"
    write_json(target, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if task.status.value == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
