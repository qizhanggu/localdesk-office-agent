from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator

import pytest

from localdesk.client import LLMClient
from localdesk.desktop.grounded_renderer import GroundedLLMRenderer, GroundedRenderError
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.reporting import KnowledgeReportWorkflow
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.skills.document import DocumentSkill
from localdesk.desktop.skills.knowledge import KnowledgeSkill
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig
from localdesk.tools.base import StreamEnd, StreamEvent, TextDelta


class FakeLLM(LLMClient):
    def __init__(self, response: str | None = None, error: Exception | None = None, delay: float = 0) -> None:
        self.response, self.error, self.delay = response, error, delay

    async def stream(self, _conversation, system: str = "", tools=None) -> AsyncIterator[StreamEvent]:
        assert tools is None
        assert "grounded report renderer" in system
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        yield TextDelta(self.response or "")
        yield StreamEnd("end_turn")


@pytest.fixture
def workspace(tmp_path: Path) -> DesktopWorkspace:
    source, output, tasks = tmp_path / "source", tmp_path / "output", tmp_path / "tasks"
    for item in (source, output, tasks): item.mkdir()
    source.joinpath("notes.md").write_text("Orion milestone is Friday. Risk is API delay.", encoding="utf-8")
    return DesktopWorkspace(WorkspaceConfig(read_roots=[source], output_root=output, task_root=tasks))


def make_workflow(workspace: DesktopWorkspace) -> KnowledgeReportWorkflow:
    service = DesktopTaskService(DesktopPolicyGuard(workspace), TaskTraceStore(workspace))
    return KnowledgeReportWorkflow(service, KnowledgeSkill(workspace), DocumentSkill(workspace))


def valid_response() -> str:
    return json.dumps({"title":"Orion 周报","sections":[{"heading":"进展","content":"里程碑计划在周五完成。","citation_ids":["notes.md:L1-L1"]}]}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_legal_output_stages_and_delivers_with_citations(workspace: DesktopWorkspace) -> None:
    workflow = make_workflow(workspace)
    task = workflow.service.create_task("总结 Orion 进展")
    draft = await workflow.prepare_grounded(task, "orion.md", GroundedLLMRenderer(FakeLLM(valid_response())))
    assert task.status.value == "awaiting_confirmation"
    assert not Path(draft.final_path).exists()
    assert "`notes.md:L1-L1`" in Path(draft.staged_path).read_text(encoding="utf-8")
    workflow.confirm_and_deliver(task, approved=True)
    assert Path(draft.final_path).exists()


@pytest.mark.asyncio
async def test_hallucinated_citation_is_rejected_without_staging(workspace: DesktopWorkspace) -> None:
    response = json.dumps({"title":"x","sections":[{"heading":"x","content":"x","citation_ids":["fake"]}]})
    workflow = make_workflow(workspace); task = workflow.service.create_task("Orion")
    with pytest.raises(GroundedRenderError, match="不存在"):
        await workflow.prepare_grounded(task, "bad.md", GroundedLLMRenderer(FakeLLM(response)))
    assert task.status.value == "failed" and not list(workspace.output_root.iterdir())
    assert "llm_render_failed" in [e["event_type"] for e in workflow.service.trace_store.load_events(task.task_id)]


@pytest.mark.asyncio
async def test_uncited_conclusion_is_rejected(workspace: DesktopWorkspace) -> None:
    response = json.dumps({"title":"x","sections":[{"heading":"x","content":"claim","citation_ids":[]}]})
    workflow = make_workflow(workspace); task = workflow.service.create_task("Orion")
    with pytest.raises(GroundedRenderError):
        await workflow.prepare_grounded(task, "bad.md", GroundedLLMRenderer(FakeLLM(response)))
    assert task.status.value == "failed" and not list(workspace.output_root.iterdir())


@pytest.mark.asyncio
async def test_timeout_fails_without_output(workspace: DesktopWorkspace) -> None:
    workflow = make_workflow(workspace); task = workflow.service.create_task("Orion")
    with pytest.raises(GroundedRenderError, match="超时"):
        await workflow.prepare_grounded(task, "slow.md", GroundedLLMRenderer(FakeLLM(valid_response(), delay=0.02), timeout_seconds=0.001))
    assert task.status.value == "failed" and not list(workspace.output_root.iterdir())


@pytest.mark.asyncio
async def test_rejected_and_tampered_draft_have_no_output(workspace: DesktopWorkspace) -> None:
    workflow = make_workflow(workspace); task = workflow.service.create_task("Orion")
    draft = await workflow.prepare_grounded(task, "reject.md", GroundedLLMRenderer(FakeLLM(valid_response())))
    workflow.confirm_and_deliver(task, approved=False)
    assert not Path(draft.final_path).exists()
    task2 = workflow.service.create_task("Orion")
    draft2 = await workflow.prepare_grounded(task2, "tamper.md", GroundedLLMRenderer(FakeLLM(valid_response())))
    Path(draft2.staged_path).write_text("tampered", encoding="utf-8")
    with pytest.raises(Exception): workflow.confirm_and_deliver(task2, approved=True)
    assert not Path(draft2.final_path).exists()
