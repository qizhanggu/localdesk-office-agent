from __future__ import annotations

from pathlib import Path

import pytest

from localdesk.desktop.browser import FakeBrowserAdapter, WebChunk
from localdesk.desktop.docx_delivery import FakeDocxRenderer
from localdesk.desktop.job_materials import JobMaterialRequest, JobMaterialsWorkflow
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.skills.document import DocumentSkill
from localdesk.desktop.skills.knowledge import KnowledgeSkill
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig, WorkspaceError


@pytest.fixture
def job_runtime(tmp_path: Path) -> tuple[DesktopWorkspace, JobMaterialsWorkflow]:
    sources, output, tasks = tmp_path / "sources", tmp_path / "output", tmp_path / "tasks"
    for directory in (sources, output, tasks):
        directory.mkdir()
    workspace = DesktopWorkspace(WorkspaceConfig(
        read_roots=[sources],
        output_root=output,
        task_root=tasks,
        browser_allowed_domains=["jobs.example.com"],
    ))
    service = DesktopTaskService(DesktopPolicyGuard(workspace), TaskTraceStore(workspace))
    return workspace, JobMaterialsWorkflow(service, KnowledgeSkill(workspace), DocumentSkill(workspace))


def test_job_materials_close_real_local_web_docx_trace_loop(job_runtime: tuple[DesktopWorkspace, JobMaterialsWorkflow]) -> None:
    workspace, workflow = job_runtime
    (workspace.read_roots[0] / "resume.md").write_text(
        "LocalDesk Agent project: Python, Agent, RAG, tool registry, deterministic tests and Trace.",
        encoding="utf-8",
    )
    url = "https://jobs.example.com/agent-role"
    jd = WebChunk(
        "web:jd",
        url,
        "Agent Developer",
        "We need Python, Agent, RAG, Docker and SQL engineering experience.",
        "2026-07-22T00:00:00+00:00",
        "a" * 64,
        ("https://jobs.example.com/apply",),
    )
    task = workflow.service.create_task("Python Agent RAG LocalDesk 项目岗位匹配")
    draft = workflow.prepare(
        task,
        JobMaterialRequest("Example", "Agent Developer", url, "agent-match.md", "agent-match.docx", "突出端到端闭环"),
        FakeBrowserAdapter({url: jd}),
        FakeDocxRenderer(),
    )

    assert task.status.value == "succeeded"
    assert (workspace.output_root / "agent-match.md").exists()
    assert (workspace.output_root / "agent-match.docx").exists()
    content = Path(draft.final_path).read_text(encoding="utf-8")
    assert "用户反馈修订" in content
    assert "Docker, SQL" in content
    events = workflow.service.trace_store.load_events(task.task_id)
    web_trace = next(event for event in events if event["event_type"] == "web_evidence_captured")
    assert web_trace["payload"]["url"] == url
    assert web_trace["payload"]["content_hash"] == "a" * 64
    assert web_trace["payload"]["citation_excerpt"]
    assert {"docx_structure_verified", "docx_render_verified", "low_risk_auto_approved", "artifact_committed"}.issubset(
        {event["event_type"] for event in events}
    )


def test_job_materials_never_overwrite_existing_output(job_runtime: tuple[DesktopWorkspace, JobMaterialsWorkflow]) -> None:
    workspace, workflow = job_runtime
    (workspace.read_roots[0] / "resume.md").write_text("Python Agent", encoding="utf-8")
    (workspace.output_root / "existing.md").write_text("keep", encoding="utf-8")
    url = "https://jobs.example.com/role"
    jd = WebChunk("web:jd", url, "Role", "Python Agent", "2026-07-22T00:00:00+00:00", "b" * 64)

    with pytest.raises(WorkspaceError, match="禁止覆盖"):
        workflow.prepare(
            workflow.service.create_task("Python Agent"),
            JobMaterialRequest("Example", "Agent", url, "existing.md"),
            FakeBrowserAdapter({url: jd}),
        )
    assert (workspace.output_root / "existing.md").read_text(encoding="utf-8") == "keep"
