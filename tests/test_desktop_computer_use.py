from __future__ import annotations

import pytest

from localdesk.desktop.computer_use import DEMO_WINDOW_TITLE, DesktopComputerWorkflow, ManualTakeoverRequired, ScreenState, UiControl
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig


class FakeDesktopAdapter:
    def __init__(self) -> None:
        self.changed = False
        self.text = ""
        self.fallback = False
        self.calls: list[str] = []

    def observe(self, title: str) -> ScreenState:
        assert title == DEMO_WINDOW_TITLE
        generation = len(self.calls) + 1
        marker = "changed" if self.changed else "normal"
        return ScreenState(title, 10, (10, 10, 510, 270), f"hash-{marker}", generation, (
            UiControl("task_input", "Edit", "", "", (30, 90, 490, 120), True),
            UiControl("submit", "Button", "Submit safe demo", "", (180, 140, 330, 170), True),
        ), f"Status: submitted {self.text}" if self.text else "Status: awaiting safe demo input")

    def set_text(self, state: ScreenState, control: str, text: str) -> ScreenState:
        self.calls.append("set_text")
        assert control == "task_input"
        self.text = text
        return self.observe(state.window_title)

    def invoke(self, state: ScreenState, control: str) -> ScreenState:
        self.calls.append("invoke")
        assert control == "submit"
        return self.observe(state.window_title)

    def fallback_click(self, state: ScreenState, x: int, y: int) -> ScreenState:
        self.calls.append("fallback")
        assert (x, y) == (250, 220)
        self.fallback = True
        result = self.observe(state.window_title)
        return ScreenState(result.window_title, result.process_id, result.bounds, result.screen_hash, result.generation, result.controls, "Status: fallback demo completed")


@pytest.fixture
def workflow(tmp_path):
    for name in ("source", "output", "tasks"):
        (tmp_path / name).mkdir()
    workspace = DesktopWorkspace(WorkspaceConfig(read_roots=[tmp_path / "source"], output_root=tmp_path / "output", task_root=tmp_path / "tasks", desktop_allowed_window_titles=[DEMO_WINDOW_TITLE]))
    service = DesktopTaskService(DesktopPolicyGuard(workspace), TaskTraceStore(workspace))
    adapter = FakeDesktopAdapter()
    return service, adapter, DesktopComputerWorkflow(service, adapter)


def test_uia_demo_requires_confirmation_then_verifies(workflow):
    service, adapter, computer = workflow
    task = service.create_task("run safe desktop demo")
    computer.prepare(task, DEMO_WINDOW_TITLE, "Orion")
    assert task.status.value == "awaiting_confirmation"
    computer.confirm_and_run(task, True)
    assert task.status.value == "succeeded"
    assert adapter.calls == ["set_text", "invoke"]
    kinds = [event["event_type"] for event in service.trace_store.load_events(task.task_id)]
    assert {"desktop_state_observed", "desktop_step_verified", "tool_verified"}.issubset(kinds)


def test_visual_fallback_refuses_changed_screen_before_click(workflow):
    service, adapter, computer = workflow
    task = service.create_task("fallback")
    computer.prepare_visual_fallback(task, DEMO_WINDOW_TITLE, 250, 220)
    adapter.changed = True
    with pytest.raises(ManualTakeoverRequired, match="状态已变化"):
        computer.confirm_and_run(task, True)
    assert not adapter.fallback
    assert task.status.value == "failed"


def test_rejected_confirmation_has_no_desktop_input(workflow):
    service, adapter, computer = workflow
    task = service.create_task("do not run")
    computer.prepare(task, DEMO_WINDOW_TITLE, "Orion")
    computer.confirm_and_run(task, False)
    assert task.status.value == "cancelled"
    assert not adapter.calls
