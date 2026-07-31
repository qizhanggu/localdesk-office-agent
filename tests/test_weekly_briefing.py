from datetime import date
from email import policy
from email.parser import BytesParser
from pathlib import Path

from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.weekly_briefing import NewsCard, NewsSource, WeeklyBriefingWorkflow, WeeklyBriefingReviewer
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig


def _workspace(tmp_path: Path) -> tuple[DesktopWorkspace, DesktopTaskService]:
    sources, output, tasks = tmp_path / "sources", tmp_path / "out", tmp_path / "tasks"
    for path in (sources, output, tasks):
        path.mkdir()
    workspace = DesktopWorkspace(WorkspaceConfig(read_roots=[sources], output_root=output, task_root=tasks))
    return workspace, DesktopTaskService(DesktopPolicyGuard(workspace), TaskTraceStore(workspace))


def _sources() -> list[NewsSource]:
    return [
        NewsSource("model", "Model progress", "2026-07-21", "https://example.com/model", "A model update.", "Useful for workflow design."),
        NewsSource("agent_product", "Agent product", "2026-07-22", "https://example.com/agent", "A governed agent product.", "Human handoff remains important."),
        NewsSource("industry", "Industry deployment", "2026-07-23", "https://example.com/industry", "Infrastructure update.", "Cost matters at scale."),
        NewsSource("model", "Model progress", "2026-07-24", "https://example.com/duplicate", "Duplicate title.", "Should be removed."),
    ]


def _fake_renderers(workflow: WeeklyBriefingWorkflow) -> None:
    def build(_cards: Path, output: Path, _start: date, _end: date) -> None:
        output.write_bytes(b"pptx" * 6000)

    def pdf(pptx: Path) -> Path:
        result = pptx.with_suffix(".pdf")
        result.write_bytes(b"pdf" * 2200)
        return result

    def render(_pptx: Path, output: Path) -> None:
        output.mkdir(exist_ok=True)
        (output / "slide-1.png").write_bytes(b"png" * 500)

    workflow._build_pptx = build  # type: ignore[method-assign]
    workflow._export_pdf = pdf  # type: ignore[method-assign]
    workflow._render_pptx = render  # type: ignore[method-assign]
    workflow._overflow_check = lambda _pptx: []  # type: ignore[method-assign]


def test_weekly_briefing_records_roles_stages_email_and_keeps_memory(tmp_path: Path) -> None:
    workspace, service = _workspace(tmp_path)
    workflow = WeeklyBriefingWorkflow(workspace, service.trace_store)
    task = workflow.create_task(service, date(2026, 7, 20), date(2026, 7, 26))
    assert task.status.value == "awaiting_confirmation"
    _fake_renderers(workflow)

    result = workflow.run(task.task_id, date(2026, 7, 20), date(2026, 7, 26), _sources(), [{"card_id": "x", "decision": "keep"}])

    assert len(result["cards"]) == 3
    assert result["review"].approved
    email = BytesParser(policy=policy.default).parsebytes(result["email"].read_bytes())
    assert email["X-LocalDesk-Draft"] == "true"
    assert len(list(email.iter_attachments())) == 2
    events = [event["event_type"] for event in service.trace_store.load_events(task.task_id)]
    assert {"research_agent_finished", "editor_finished", "weekly_briefing_reviewed"} <= set(events)
    memory = workflow.memory.load()
    assert len(memory["seen"]) == 3 and memory["feedback"] == [{"card_id": "x", "decision": "keep"}]


def test_memory_avoids_already_seen_cards(tmp_path: Path) -> None:
    workspace, service = _workspace(tmp_path)
    workflow = WeeklyBriefingWorkflow(workspace, service.trace_store)
    first = workflow.create_task(service, date(2026, 7, 20), date(2026, 7, 26)); _fake_renderers(workflow)
    workflow.run(first.task_id, date(2026, 7, 20), date(2026, 7, 26), _sources())
    second = workflow.create_task(service, date(2026, 7, 27), date(2026, 8, 2))
    _fake_renderers(workflow)
    refreshed = [NewsSource("model", "New model", "2026-07-27", "https://example.com/new", "New evidence.", "Follow-up value.")] + [
        NewsSource(item.category, item.title, "2026-07-27", item.url, item.summary, item.value) for item in _sources()[:3]
    ]
    result = workflow.run(second.task_id, date(2026, 7, 27), date(2026, 8, 2), refreshed)
    assert [card.title for card in result["cards"]] == ["New model"]
    assert not result["review"].approved
    assert "少于三个研究方向的资讯" in result["review"].blockers


def test_reviewer_blocks_invalid_sources_date_and_duplicate() -> None:
    cards = [
        NewsCard("one", "model", "Same", "2026-07-19", "http://bad", "summary", "value"),
        NewsCard("two", "model", "Same", "2026-07-21", "https://good", "summary", "value"),
    ]
    review = WeeklyBriefingReviewer().review(cards, date(2026, 7, 20), date(2026, 7, 22))
    assert not review.approved
    assert any("超出本周时间范围" in item for item in review.blockers)
    assert any("HTTPS" in item for item in review.blockers)
    assert any("重复资讯" in item for item in review.blockers)
