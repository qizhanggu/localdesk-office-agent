from datetime import date
from email import policy
from email.parser import BytesParser
import hashlib
import os
from pathlib import Path
import zipfile

import fitz

from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.browser import FakeBrowserAdapter, WebChunk
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.weekly_briefing import (
    NewsCard,
    NewsSource,
    WeeklyBriefingMemory,
    WeeklyBriefingReviewer,
    WeeklyBriefingWorkflow,
    _event_id,
    _find_soffice,
    _resolve_artifact_python,
    _resolve_node_executable,
)
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


def _browser(sources: list[NewsSource]) -> FakeBrowserAdapter:
    pages = {}
    for source in sources:
        text = f"{source.title}. {source.summary} {source.value}"
        pages[source.url] = WebChunk(
            f"web:{source.url}", source.url, source.title, text,
            "2026-07-26T00:00:00+00:00", hashlib.sha256(text.encode()).hexdigest(),
        )
    return FakeBrowserAdapter(pages)


def _fake_renderers(workflow: WeeklyBriefingWorkflow) -> None:
    def build(_cards: Path, output: Path, _start: date, _end: date) -> None:
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("ppt/presentation.xml", "<presentation />")
            archive.writestr("ppt/media/test.bin", os.urandom(25_000))

    def pdf(pptx: Path) -> Path:
        result = pptx.with_suffix(".pdf")
        document = fitz.open()
        for index in range(8):
            page = document.new_page()
            page.insert_text((72, 72), f"Weekly briefing page {index + 1} " + "evidence " * 100)
        document.save(result)
        document.close()
        with result.open("ab") as handle:
            handle.write(os.urandom(6_000))
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
    workflow = WeeklyBriefingWorkflow(workspace, service.trace_store, browser=_browser(_sources()))
    task = workflow.create_task(service, date(2026, 7, 20), date(2026, 7, 26))
    assert task.status.value == "draft"
    _fake_renderers(workflow)

    result = workflow.run(service, task, date(2026, 7, 20), date(2026, 7, 26), _sources(), [{"card_id": "x", "decision": "keep"}])

    assert len(result["cards"]) == 3
    assert result["review"].approved
    assert task.status.value == "awaiting_confirmation" and len(task.actions) == 3
    email = BytesParser(policy=policy.default).parsebytes(result["email"].read_bytes())
    assert email["X-LocalDesk-Draft"] == "true"
    assert len(list(email.iter_attachments())) == 2
    events = [event["event_type"] for event in service.trace_store.load_events(task.task_id)]
    assert {"research_agent_finished", "editor_finished", "weekly_briefing_reviewed"} <= set(events)
    memory = workflow.memory.load()
    assert len(memory["seen"]) == 3 and memory["feedback"] == [{"card_id": "x", "decision": "keep"}]
    workflow.confirm_and_deliver(service, task, approved=True)
    assert task.status.value == "succeeded" and len(task.artifacts) == 3
    assert {Path(item.final_path).suffix for item in task.artifacts if item.final_path} == {".pptx", ".pdf", ".eml"}


def test_memory_avoids_already_seen_cards(tmp_path: Path) -> None:
    workspace, service = _workspace(tmp_path)
    workflow = WeeklyBriefingWorkflow(workspace, service.trace_store, browser=_browser(_sources()))
    first = workflow.create_task(service, date(2026, 7, 20), date(2026, 7, 26)); _fake_renderers(workflow)
    workflow.run(service, first, date(2026, 7, 20), date(2026, 7, 26), _sources())
    second = workflow.create_task(service, date(2026, 7, 27), date(2026, 8, 2))
    _fake_renderers(workflow)
    refreshed = [NewsSource("model", "New model", "2026-07-27", "https://example.com/new", "New evidence.", "Follow-up value.")] + [
        NewsSource(item.category, item.title, "2026-07-27", item.url, item.summary, item.value) for item in _sources()[:3]
    ]
    workflow.browser = _browser(refreshed)
    result = workflow.run(service, second, date(2026, 7, 27), date(2026, 8, 2), refreshed)
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


def test_editor_merges_cross_source_title_variants_and_keeps_preferred_representative() -> None:
    model = NewsCard(
        "model-card", "model", "OpenAI launches Codex for enterprise teams", "2026-07-24",
        "https://example.com/model", "summary", "value",
        event_id=_event_id("OpenAI launches Codex for enterprise teams"),
    )
    industry = NewsCard(
        "industry-card", "industry", "Codex for enterprise teams launched by OpenAI", "2026-07-23",
        "https://example.com/industry", "summary", "value",
        event_id=_event_id("Codex for enterprise teams launched by OpenAI"),
    )

    selected = WeeklyBriefingWorkflow._edit(
        [model, industry], {}, {}, {"industry": 2, "model": 0},
    )

    assert len(selected) == 1
    assert selected[0].card_id == "industry-card"
    assert selected[0].related_urls == ("https://example.com/model",)
    assert selected[0].merged_card_ids == ("model-card",)


def test_editor_filters_reworded_event_seen_in_previous_week() -> None:
    first_title = "OpenAI launches Codex for enterprise teams"
    reworded = NewsCard(
        "next-week-card", "model", "Codex for enterprise teams launched by OpenAI", "2026-07-30",
        "https://example.com/next-week", "summary", "value",
        event_id=_event_id("Codex for enterprise teams launched by OpenAI"),
    )

    selected = WeeklyBriefingWorkflow._edit(
        [reworded], {}, {_event_id(first_title): {"title": first_title}}, {},
    )

    assert selected == []


def test_memory_records_event_and_explicit_keep_preference(tmp_path: Path) -> None:
    memory = WeeklyBriefingMemory(tmp_path / "memory.json")
    card = NewsCard(
        "kept-card", "industry", "Industry event", "2026-07-24",
        "https://example.com/industry", "summary", "value",
        event_id=_event_id("Industry event"),
    )

    memory.save([card], [{"card_id": "kept-card", "decision": "keep"}])
    stored = memory.load()

    assert card.event_id in stored["events"]
    assert stored["preferences"] == {"industry": 1}


def test_weekly_tool_runtime_paths_are_configurable(tmp_path: Path, monkeypatch) -> None:
    node = tmp_path / "node.exe"
    python = tmp_path / "python.exe"
    soffice = tmp_path / "soffice.com"
    node.write_bytes(b"node")
    python.write_bytes(b"python")
    soffice.write_bytes(b"soffice")
    monkeypatch.setenv("LOCALDESK_NODE", str(node))
    monkeypatch.setenv("LOCALDESK_ARTIFACT_PYTHON", str(python))
    monkeypatch.setenv("LOCALDESK_SOFFICE_PATH", str(soffice))

    assert _resolve_node_executable() == str(node.resolve())
    assert _resolve_artifact_python() == str(python.resolve())
    assert _find_soffice() == str(soffice)
