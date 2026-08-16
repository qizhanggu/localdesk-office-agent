"""受控 Windows UI Automation：仅服务于 LocalDesk 自建测试窗口。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from localdesk.desktop.models import ActionKind, PlannedAction, Task, TaskStatus
from localdesk.desktop.registry import DesktopToolRegistry, create_desktop_registry
from localdesk.desktop.service import DesktopTaskService, TaskStateError


DEMO_WINDOW_TITLE = "LocalDesk Phase 5 Test App"


class DesktopAutomationError(RuntimeError):
    pass


class ManualTakeoverRequired(DesktopAutomationError):
    pass


@dataclass(frozen=True)
class UiControl:
    key: str
    control_type: str
    name: str
    automation_id: str
    bounds: tuple[int, int, int, int]
    enabled: bool


@dataclass(frozen=True)
class ScreenState:
    window_title: str
    process_id: int
    bounds: tuple[int, int, int, int]
    screen_hash: str
    generation: int
    controls: tuple[UiControl, ...]
    status_text: str


class DesktopAdapter(Protocol):
    def observe(self, window_title: str) -> ScreenState: ...
    def set_text(self, state: ScreenState, control: str, text: str) -> ScreenState: ...
    def invoke(self, state: ScreenState, control: str) -> ScreenState: ...
    def fallback_click(self, state: ScreenState, x: int, y: int) -> ScreenState: ...


class WindowsUiaAdapter:
    """pywinauto UIA backend; never selects an arbitrary desktop window."""

    def __init__(self) -> None:
        self._generation = 0

    def observe(self, window_title: str) -> ScreenState:
        try:
            from pywinauto import Desktop
        except ImportError as exc:  # pragma: no cover - depends on Windows environment
            raise DesktopAutomationError("缺少 pywinauto；请执行 uv sync 安装 Windows UIA 依赖") from exc
        windows = [window for window in Desktop(backend="uia").windows() if window.window_text() == window_title]
        if len(windows) != 1:
            raise ManualTakeoverRequired(f"期望唯一测试窗口 {window_title!r}，实际找到 {len(windows)} 个")
        window = windows[0]
        if not window.is_visible() or not window.is_enabled():
            raise ManualTakeoverRequired("测试窗口不可见或不可用；请人工恢复后重新开始")
        rectangle = window.rectangle()
        controls: list[UiControl] = []
        edit_seen = button_seen = 0
        for child in window.descendants():
            info = child.element_info
            kind = info.control_type or "Unknown"
            if kind not in {"Edit", "Button", "Text"}:
                continue
            if kind == "Edit":
                edit_seen += 1; key = "task_input" if edit_seen == 1 else f"edit_{edit_seen}"
            elif kind == "Button":
                button_seen += 1
                name = (info.name or "").strip()
                key = "submit" if name == "Submit safe demo" else "fallback" if name == "Run fallback demo" else f"button_{button_seen}"
            else:
                key = f"text_{len(controls)}"
            rect = child.rectangle()
            controls.append(UiControl(key, kind, (info.name or "").strip(), (info.automation_id or "").strip(), (rect.left, rect.top, rect.right, rect.bottom), bool(child.is_enabled())))
        status = next((item.name for item in controls if item.control_type == "Text" and item.name.startswith("Status:")), "")
        image = window.capture_as_image()
        digest = hashlib.sha256(image.tobytes()).hexdigest()
        self._generation += 1
        return ScreenState(window_title, window.process_id(), (rectangle.left, rectangle.top, rectangle.right, rectangle.bottom), digest, self._generation, tuple(controls), status)

    def _window_and_control(self, state: ScreenState, control: str):
        current = self.observe(state.window_title)
        if current.screen_hash != state.screen_hash:
            raise ManualTakeoverRequired("窗口状态在动作前已经变化；旧 UIA 索引和坐标全部失效")
        try:
            from pywinauto import Desktop
        except ImportError as exc:  # pragma: no cover
            raise DesktopAutomationError("缺少 pywinauto") from exc
        window = [item for item in Desktop(backend="uia").windows() if item.window_text() == state.window_title][0]
        candidates = [item for item in window.descendants() if getattr(item.element_info, "control_type", "") in {"Edit", "Button"}]
        mapped = {item.key: item for item in state.controls}
        if control not in mapped:
            raise ManualTakeoverRequired(f"UIA 未找到受控元素 {control}")
        target = mapped[control]
        matching = [item for item in candidates if item.element_info.control_type == target.control_type and (item.element_info.name or "").strip() == target.name]
        if len(matching) != 1:
            raise ManualTakeoverRequired(f"控件 {control} 不再唯一；请人工接管")
        return window, matching[0]

    def set_text(self, state: ScreenState, control: str, text: str) -> ScreenState:
        _, target = self._window_and_control(state, control)
        target.set_edit_text(text)
        return self.observe(state.window_title)

    def invoke(self, state: ScreenState, control: str) -> ScreenState:
        _, target = self._window_and_control(state, control)
        target.click_input()
        return self.observe(state.window_title)

    def fallback_click(self, state: ScreenState, x: int, y: int) -> ScreenState:
        current = self.observe(state.window_title)
        if current.screen_hash != state.screen_hash or current.bounds != state.bounds:
            raise ManualTakeoverRequired("视觉 fallback 的窗口或屏幕状态已变化；禁止使用旧坐标")
        left, top, right, bottom = state.bounds
        if not (left <= x <= right and top <= y <= bottom):
            raise DesktopAutomationError("fallback 坐标不在目标窗口内")
        try:
            from pywinauto import Desktop
            window = [item for item in Desktop(backend="uia").windows() if item.window_text() == state.window_title][0]
        except Exception as exc:  # pragma: no cover
            raise ManualTakeoverRequired("fallback 无法重新绑定测试窗口") from exc
        window.click_input(coords=(x - left, y - top))
        return self.observe(state.window_title)


class DesktopComputerWorkflow:
    """将 UIA 操作纳入任务确认、Trace、最大步骤数和人工接管。"""

    def __init__(self, service: DesktopTaskService, adapter: DesktopAdapter, registry: DesktopToolRegistry | None = None, *, max_steps: int = 3) -> None:
        self.service, self.adapter, self.registry, self.max_steps = service, adapter, registry or create_desktop_registry(service), max_steps

    def prepare(self, task: Task, window_title: str, text: str) -> ScreenState:
        state = self._observe(task, window_title)
        keys = {control.key for control in state.controls}
        if not {"task_input", "submit"}.issubset(keys):
            self.service.fail(task, "测试窗口缺少预期 UIA 控件", event_type="desktop_uia_unavailable")
            raise ManualTakeoverRequired("UIA 控件不可用；请人工接管或使用专门 fallback 测试")
        actions = [
            PlannedAction("desktop-set-text", "desktop.uia.set_text", ActionKind.DESKTOP, {"window_title": window_title, "control": "task_input", "text": text}, "向测试窗口输入无敏感演示文本", preview={"screen_hash": state.screen_hash}),
            PlannedAction("desktop-invoke", "desktop.uia.invoke", ActionKind.DESKTOP, {"window_title": window_title, "control": "submit"}, "提交测试窗口的低风险演示动作", preview={"expected_text": text}),
        ]
        self.service.set_plan(task, "在白名单测试窗口中：UIA 定位输入框 → 输入构造文本 → 调用低风险按钮 → 验证状态。", actions)
        self.service.trace_store.append(task.task_id, "desktop_state_observed", self._trace_state(state))
        return state

    def confirm_and_run(self, task: Task, approved: bool) -> None:
        self.service.confirm(task, approved)
        if not approved:
            return
        if len(task.actions) > self.max_steps:
            self.service.finish(task, "超过 Desktop 最大步骤数")
            raise DesktopAutomationError("超过 Desktop 最大步骤数")
        try:
            state = self._observe(task, task.actions[0].args["window_title"])
            for action in task.actions:
                if action.action_id == "desktop-set-text":
                    state = self.registry.execute(task, action, lambda: self.adapter.set_text(state, action.args["control"], action.args["text"]), verify=lambda result: True)
                elif action.action_id == "desktop-invoke":
                    state = self.registry.execute(task, action, lambda: self.adapter.invoke(state, action.args["control"]), verify=lambda result: action.preview["expected_text"] in result.status_text)
                else:
                    if action.preview["screen_hash"] != state.screen_hash:
                        raise ManualTakeoverRequired("fallback 前窗口状态已变化；禁止使用旧坐标")
                    state = self.registry.execute(task, action, lambda: self.adapter.fallback_click(state, action.args["x"], action.args["y"]), verify=lambda result: "fallback demo completed" in result.status_text)
                action.status = "succeeded"
                self.service.trace_store.append(task.task_id, "desktop_step_verified", {"action_id": action.action_id, **self._trace_state(state)})
        except ManualTakeoverRequired as exc:
            self.service.finish(task, str(exc))
            self.service.trace_store.append(task.task_id, "manual_takeover_required", {"reason": str(exc)})
            raise
        except Exception as exc:
            self.service.finish(task, str(exc))
            raise
        self.service.finish(task)

    def prepare_visual_fallback(self, task: Task, window_title: str, x: int, y: int) -> ScreenState:
        state = self._observe(task, window_title)
        left, top, right, bottom = state.bounds
        if not (left <= x <= right and top <= y <= bottom):
            raise DesktopAutomationError("fallback 坐标不在白名单窗口范围内")
        action = PlannedAction(
            "desktop-fallback",
            "desktop.visual_fallback",
            ActionKind.DESKTOP,
            {"window_title": window_title, "x": x, "y": y, "screen_hash": state.screen_hash},
            "在状态哈希与窗口边界均未变化时执行测试用视觉 fallback",
            preview={"screen_hash": state.screen_hash},
        )
        self.service.set_plan(task, "UIA 不可用时，只在自建测试窗口中执行一次状态绑定的坐标 fallback。", [action])
        self.service.trace_store.append(task.task_id, "desktop_visual_fallback_staged", self._trace_state(state))
        return state

    def _observe(self, task: Task, window_title: str) -> ScreenState:
        action = PlannedAction("desktop-observe", "desktop.uia.observe", ActionKind.DESKTOP, {"window_title": window_title}, "读取白名单测试窗口状态")
        return self.registry.execute(task, action, lambda: self.adapter.observe(window_title), verify=lambda result: result.window_title == window_title)

    @staticmethod
    def _trace_state(state: ScreenState) -> dict:
        return {"window_title": state.window_title, "process_id": state.process_id, "bounds": state.bounds, "screen_hash": state.screen_hash, "generation": state.generation, "status_text": state.status_text, "controls": [control.__dict__ for control in state.controls]}
