from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from localdesk.desktop.models import ActionKind, PlannedAction, TaskStatus
from localdesk.desktop.cli import run_desktop_foundation
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.registry import create_desktop_registry
from localdesk.desktop.service import DesktopTaskService, TaskStateError
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig, WorkspaceError


@pytest.fixture
def workspace(tmp_path: Path) -> DesktopWorkspace:
    sources = tmp_path / "sources"
    managed = tmp_path / "downloads"
    output = tmp_path / "output"
    tasks = tmp_path / "tasks"
    for directory in (sources, managed, output, tasks):
        directory.mkdir()
    return DesktopWorkspace(
        WorkspaceConfig(
            read_roots=[sources],
            managed_roots=[managed],
            output_root=output,
            task_root=tasks,
        )
    )


def action(kind: ActionKind, **args: str) -> PlannedAction:
    return PlannedAction(
        action_id="a1", skill="test", kind=kind, args=args, summary="test action"
    )


def test_workspace_rejects_relative_paths(workspace: DesktopWorkspace) -> None:
    with pytest.raises(WorkspaceError, match="绝对路径"):
        workspace.resolve_path("relative/file.md")


def test_workspace_rejects_relative_config_root(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError, match="绝对路径"):
        DesktopWorkspace(
            WorkspaceConfig(
                read_roots=[Path("relative")],
                output_root=tmp_path / "output",
                task_root=tmp_path / "tasks",
            )
        )


def test_read_allows_only_authorized_roots(workspace: DesktopWorkspace, tmp_path: Path) -> None:
    allowed = workspace.read_roots[0] / "note.md"
    outside = tmp_path / "outside.md"
    assert workspace.can_read(allowed)
    assert not workspace.can_read(outside)


def test_write_requires_staging_or_output(workspace: DesktopWorkspace, tmp_path: Path) -> None:
    assert workspace.can_write_artifact(workspace.output_root / "report.md")
    assert workspace.can_write_artifact(workspace.task_root / "task-1" / "draft.md")
    assert not workspace.can_write_artifact(tmp_path / "outside.md")


def test_policy_denies_unsafe_actions(workspace: DesktopWorkspace) -> None:
    guard = DesktopPolicyGuard(workspace)
    for kind in (ActionKind.DELETE, ActionKind.SHELL, ActionKind.NETWORK):
        assert guard.evaluate(action(kind)).effect == "deny"


def test_policy_denies_outside_and_existing_write(workspace: DesktopWorkspace, tmp_path: Path) -> None:
    guard = DesktopPolicyGuard(workspace)
    assert guard.evaluate(action(ActionKind.READ, path=str(tmp_path / "outside.md"))).effect == "deny"

    existing = workspace.output_root / "exists.md"
    existing.write_text("existing", encoding="utf-8")
    assert guard.evaluate(action(ActionKind.WRITE, destination=str(existing))).effect == "deny"


def test_policy_requires_confirmation_for_new_output(workspace: DesktopWorkspace) -> None:
    guard = DesktopPolicyGuard(workspace)
    decision = guard.evaluate(
        action(ActionKind.WRITE, destination=str(workspace.output_root / "new-report.md"))
    )
    assert decision.effect == "ask"
    assert decision.requires_confirmation


def test_policy_requires_confirmation_for_managed_move(workspace: DesktopWorkspace) -> None:
    guard = DesktopPolicyGuard(workspace)
    source = workspace.managed_roots[0] / "inbox" / "a.pdf"
    destination = workspace.managed_roots[0] / "pdf" / "a.pdf"
    decision = guard.evaluate(action(ActionKind.MOVE, source=str(source), destination=str(destination)))
    assert decision.effect == "ask"
    assert decision.requires_confirmation


def test_policy_denies_move_between_managed_and_output(workspace: DesktopWorkspace) -> None:
    guard = DesktopPolicyGuard(workspace)
    decision = guard.evaluate(
        action(
            ActionKind.MOVE,
            source=str(workspace.managed_roots[0] / "a.pdf"),
            destination=str(workspace.output_root / "a.pdf"),
        )
    )
    assert decision.effect == "deny"


def test_task_trace_and_confirmation_lifecycle(workspace: DesktopWorkspace) -> None:
    service = DesktopTaskService(DesktopPolicyGuard(workspace), TaskTraceStore(workspace))
    task = service.create_task("整理下载目录")
    service.set_plan(
        task,
        "移动 PDF",
        [
            action(
                ActionKind.MOVE,
                source=str(workspace.managed_roots[0] / "a.pdf"),
                destination=str(workspace.managed_roots[0] / "pdf" / "a.pdf"),
            )
        ],
    )
    assert task.status == TaskStatus.AWAITING_CONFIRMATION
    service.confirm(task, approved=True)
    assert task.status == TaskStatus.EXECUTING
    service.finish(task)
    assert task.status == TaskStatus.SUCCEEDED

    store = TaskTraceStore(workspace)
    assert store.load_task(task.task_id)["status"] == "succeeded"
    assert [event["event_type"] for event in store.load_events(task.task_id)] == [
        "task_created",
        "status_changed",
        "plan_created",
        "status_changed",
        "confirmation",
        "status_changed",
        "status_changed",
    ]


def test_cannot_confirm_without_plan(workspace: DesktopWorkspace) -> None:
    service = DesktopTaskService(DesktopPolicyGuard(workspace), TaskTraceStore(workspace))
    task = service.create_task("测试")
    with pytest.raises(TaskStateError):
        service.confirm(task, approved=True)


def test_rejected_action_cannot_enter_execution(workspace: DesktopWorkspace, tmp_path: Path) -> None:
    service = DesktopTaskService(DesktopPolicyGuard(workspace), TaskTraceStore(workspace))
    task = service.create_task("删除不安全文件")
    service.set_plan(task, "删除文件", [action(ActionKind.DELETE, path=str(tmp_path / "x"))])
    assert task.status == TaskStatus.PLANNED
    assert task.error == "计划包含被安全策略拒绝的动作"
    with pytest.raises(TaskStateError):
        service.confirm(task, approved=True)


def test_auto_deliver_flag_only_applies_to_registered_document_commit(workspace: DesktopWorkspace) -> None:
    guard = DesktopPolicyGuard(workspace)
    destination = str(workspace.output_root / "new.md")
    forged = PlannedAction("forged", "test", ActionKind.WRITE, {"destination": destination, "auto_deliver": True}, "forged")
    document_commit = PlannedAction("commit", "document.commit_markdown", ActionKind.WRITE, {"destination": destination, "auto_deliver": True}, "commit")
    email_draft = PlannedAction("email", "mail.commit_eml", ActionKind.WRITE, {"destination": str(workspace.output_root / "draft.eml"), "auto_deliver": True}, "email draft")

    assert guard.evaluate(forged).requires_confirmation
    assert not guard.evaluate(document_commit).requires_confirmation
    assert not guard.evaluate(email_draft).requires_confirmation


def test_desktop_registry_does_not_leak_coding_tools() -> None:
    names = {tool.name for tool in create_desktop_registry().list_tools()}
    assert names.isdisjoint({"Bash", "WriteFile", "EditFile", "Agent", "TeamCreate"})
    assert names == {
        "knowledge.search",
        "browser.open",
        "document.stage_markdown",
        "document.commit_markdown",
        "document.stage_docx",
        "document.commit_docx",
        "document.inspect_docx",
        "document.stage_pdf",
        "document.commit_pdf",
        "mail.stage_eml",
        "mail.commit_eml",
        "files.scan",
        "files.move",
        "files.rollback_move",
        "spreadsheet.inspect",
        "spreadsheet.stage_transform",
        "spreadsheet.commit",
        "desktop.uia.observe",
        "desktop.uia.set_text",
        "desktop.uia.invoke",
        "desktop.visual_fallback",
    }


def test_desktop_cli_creates_trace_only(workspace: DesktopWorkspace, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_desktop_foundation(
        Namespace(
            desktop_task="生成周报",
            desktop_read_root=[str(workspace.read_roots[0])],
            desktop_managed_root=[str(workspace.managed_roots[0])],
            desktop_output_root=str(workspace.output_root),
            desktop_task_root=str(workspace.task_root),
        )
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "desktop tools registered: 21" in output
    assert "no file operation" in output
    assert len(list(workspace.task_root.iterdir())) == 1
