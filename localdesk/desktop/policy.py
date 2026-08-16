from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from localdesk.desktop.models import ActionKind, PlannedAction
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceError


@dataclass(frozen=True)
class PolicyDecision:
    effect: str
    reason: str
    requires_confirmation: bool = False


class DesktopPolicyGuard:
    """位于 Planner 与文件系统操作之间的 deny-first 策略层。"""

    _DENIED_KINDS = {ActionKind.DELETE, ActionKind.SHELL, ActionKind.NETWORK}

    def __init__(self, workspace: DesktopWorkspace) -> None:
        self.workspace = workspace

    def evaluate(self, action: PlannedAction) -> PolicyDecision:
        if action.kind in self._DENIED_KINDS:
            return PolicyDecision("deny", f"Desktop v1 不允许 {action.kind.value}")

        try:
            if action.kind == ActionKind.READ:
                return self._evaluate_read(action.args)
            if action.kind == ActionKind.NAVIGATE:
                return self._evaluate_navigation(action.args)
            if action.kind == ActionKind.DESKTOP:
                return self._evaluate_desktop(action)
            if action.kind == ActionKind.WRITE:
                return self._evaluate_write(action)
            if action.kind in {ActionKind.MOVE, ActionKind.RENAME}:
                return self._evaluate_manage(action.args, action.kind)
        except WorkspaceError as exc:
            return PolicyDecision("deny", str(exc))
        return PolicyDecision("deny", f"未知或未实现的动作类型: {action.kind.value}")

    def _evaluate_desktop(self, action: PlannedAction) -> PolicyDecision:
        title = action.args.get("window_title")
        if not isinstance(title, str) or not title.strip():
            return PolicyDecision("deny", "缺少受控窗口标题")
        if not self.workspace.can_automate_window(title):
            return PolicyDecision("deny", f"桌面窗口不在白名单: {title}")
        if action.skill == "desktop.uia.observe":
            return PolicyDecision("allow", "允许读取白名单测试窗口的 UIA 状态")
        if action.skill in {"desktop.uia.set_text", "desktop.uia.invoke", "desktop.visual_fallback"}:
            return PolicyDecision("ask", "桌面输入或点击需要用户确认", requires_confirmation=True)
        return PolicyDecision("deny", f"未注册的桌面动作: {action.skill}")

    def _evaluate_navigation(self, args: dict[str, Any]) -> PolicyDecision:
        url = args.get("url")
        if not isinstance(url, str) or not url.strip():
            return PolicyDecision("deny", "缺少网页 URL")
        if not self.workspace.can_browse(url):
            return PolicyDecision("deny", f"网页域名或协议不在授权范围: {url}")
        return PolicyDecision("allow", "允许域名内的只读网页导航")

    def _evaluate_read(self, args: dict[str, Any]) -> PolicyDecision:
        path = self._required_path(args, "path")
        if not self.workspace.can_read(path):
            return PolicyDecision("deny", f"读取路径越出授权范围: {path}")
        return PolicyDecision("allow", "授权目录内的只读操作")

    def _evaluate_write(self, action: PlannedAction) -> PolicyDecision:
        args = action.args
        destination = self._required_path(args, "destination")
        if not self.workspace.can_write_artifact(destination):
            return PolicyDecision("deny", f"写入目标不在 staging 或 output 目录: {destination}")
        if Path(destination).exists():
            return PolicyDecision("deny", f"禁止覆盖已有文件: {destination}")
        if self.workspace.is_task_artifact(destination):
            return PolicyDecision("allow", "任务 staging 内的草稿写入")
        if action.skill in {"document.commit_markdown", "document.commit_docx", "mail.commit_eml"} and args.get("auto_deliver") is True:
            return PolicyDecision("allow", "新建低风险产物允许自动交付；覆盖和外发仍需确认")
        return PolicyDecision("ask", "写入产物需要确认", requires_confirmation=True)

    def _evaluate_manage(self, args: dict[str, Any], kind: ActionKind) -> PolicyDecision:
        source = self._required_path(args, "source")
        destination = self._required_path(args, "destination")
        if not self.workspace.can_manage(source):
            return PolicyDecision("deny", f"{kind.value} 源路径不在可整理目录: {source}")
        if not self.workspace.can_manage(destination):
            return PolicyDecision("deny", f"{kind.value} 目标路径不在可整理目录: {destination}")
        # 目标是否已在预览后出现属于 TOCTOU 竞态；最终执行前必须由 FileSkill
        # 在同一条 journal 事务中复核并拒绝，避免“被拦截但没有失败记录”。
        return PolicyDecision("ask", f"{kind.value} 需要用户确认", requires_confirmation=True)

    @staticmethod
    def _required_path(args: dict[str, Any], name: str) -> str:
        value = args.get(name)
        if not isinstance(value, str) or not value.strip():
            raise WorkspaceError(f"缺少路径参数: {name}")
        return value
