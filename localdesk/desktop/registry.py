from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from localdesk.desktop.models import ActionKind, PlannedAction, Task, TaskStatus
from localdesk.desktop.service import DesktopTaskService


class KnowledgeSearchParams(BaseModel):
    path: str
    query: str


class BrowserOpenParams(BaseModel):
    url: str


class StageMarkdownParams(BaseModel):
    destination: str


class CommitMarkdownParams(BaseModel):
    destination: str
    auto_deliver: bool = False


class StageDocxParams(BaseModel):
    destination: str
    source_markdown: str


class CommitDocxParams(BaseModel):
    destination: str
    auto_deliver: bool = False


class DocxInspectParams(BaseModel):
    path: str


class StagePdfParams(BaseModel):
    destination: str
    source_docx: str


class CommitPdfParams(BaseModel):
    destination: str


class StageEmlParams(BaseModel):
    destination: str
    recipient_count: int


class CommitEmlParams(BaseModel):
    destination: str
    auto_deliver: bool = False


class FileScanParams(BaseModel):
    path: str


class FileMoveParams(BaseModel):
    source: str
    destination: str


class SpreadsheetInspectParams(BaseModel):
    path: str


class SpreadsheetStageParams(BaseModel):
    source: str
    destination: str


class SpreadsheetCommitParams(BaseModel):
    destination: str


class DesktopObserveParams(BaseModel):
    window_title: str


class DesktopTextParams(BaseModel):
    window_title: str
    control: str
    text: str


class DesktopInvokeParams(BaseModel):
    window_title: str
    control: str


class DesktopFallbackParams(BaseModel):
    window_title: str
    x: int
    y: int
    screen_hash: str


@dataclass(frozen=True)
class DesktopToolDefinition:
    """受控 Desktop Tool 的静态元数据。

    这不是旧 Coding Agent 的 Tool；它声明一项办公动作必须具备的安全和
    运行属性，实际调用一律由 DesktopToolRegistry 统一编排。
    """

    name: str
    description: str
    params_model: type[BaseModel]
    action_kind: ActionKind
    risk_level: str
    read_only: bool
    side_effect: bool
    idempotent: bool
    retryable: bool
    timeout_seconds: int


class DesktopToolExecutionError(RuntimeError):
    pass


ResultT = TypeVar("ResultT")


class DesktopToolRegistry:
    """唯一允许 Desktop workflow 调用受控能力的入口。"""

    def __init__(self, service: DesktopTaskService | None = None) -> None:
        self.service = service
        self._tools: dict[str, DesktopToolDefinition] = {}

    def register(self, definition: DesktopToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Desktop tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def get(self, name: str) -> DesktopToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self) -> list[DesktopToolDefinition]:
        return list(self._tools.values())

    def execute(
        self,
        task: Task,
        action: PlannedAction,
        callback: Callable[[], ResultT],
        verify: Callable[[ResultT], bool] | None = None,
    ) -> ResultT:
        """执行一个已声明动作，并写入策略、执行和验证 Trace。"""

        if self.service is None:
            raise DesktopToolExecutionError("Desktop registry has no task service")
        if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            raise DesktopToolExecutionError("Terminal task cannot execute a tool")

        definition = self.get(action.skill)
        if definition is None:
            raise DesktopToolExecutionError(f"Desktop tool is not registered: {action.skill}")
        if action.kind != definition.action_kind:
            raise DesktopToolExecutionError(f"Tool action kind mismatch: {action.skill}")

        try:
            validated = definition.params_model.model_validate(action.args)
        except Exception as exc:
            self.service.trace_store.append(task.task_id, "tool_schema_rejected", {"tool": action.skill, "error": str(exc)})
            raise DesktopToolExecutionError(f"Tool parameter validation failed: {action.skill}") from exc

        decision = self.service.policy.evaluate(action)
        payload = {
            "tool": definition.name,
            "action_id": action.action_id,
            "risk_level": definition.risk_level,
            "params": validated.model_dump(mode="json"),
            "decision": decision.__dict__,
        }
        self.service.trace_store.append(task.task_id, "tool_requested", payload)
        self.service.trace_store.append(task.task_id, "tool_policy_decided", payload)
        if decision.effect == "deny":
            self.service.trace_store.append(task.task_id, "tool_blocked", payload)
            raise DesktopToolExecutionError(decision.reason)
        if decision.requires_confirmation and task.status != TaskStatus.EXECUTING:
            self.service.trace_store.append(task.task_id, "tool_awaiting_approval", payload)
            raise DesktopToolExecutionError("Tool requires an approved executing task")

        try:
            result = callback()
        except Exception as exc:
            self.service.trace_store.append(task.task_id, "tool_failed", {"tool": definition.name, "action_id": action.action_id, "error": str(exc)})
            raise

        self.service.trace_store.append(task.task_id, "tool_completed", {"tool": definition.name, "action_id": action.action_id})
        if verify is not None and not verify(result):
            self.service.trace_store.append(task.task_id, "tool_verification_failed", {"tool": definition.name, "action_id": action.action_id})
            raise DesktopToolExecutionError(f"Postcondition verification failed: {action.skill}")
        if verify is not None:
            self.service.trace_store.append(task.task_id, "tool_verified", {"tool": definition.name, "action_id": action.action_id})
        return result


def create_desktop_registry(service: DesktopTaskService | None = None) -> DesktopToolRegistry:
    registry = DesktopToolRegistry(service)
    registry.register(DesktopToolDefinition(
        name="knowledge.search",
        description="在用户授权的本地资料根目录检索可引用片段。",
        params_model=KnowledgeSearchParams,
        action_kind=ActionKind.READ,
        risk_level="R0",
        read_only=True,
        side_effect=False,
        idempotent=True,
        retryable=True,
        timeout_seconds=30,
    ))
    registry.register(DesktopToolDefinition("spreadsheet.inspect", "读取授权 CSV/XLSX 的工作表、表头、行列与单元格。", SpreadsheetInspectParams, ActionKind.READ, "R0", True, False, True, True, 30))
    registry.register(DesktopToolDefinition("spreadsheet.stage_transform", "在 task staging 创建经确定性校验的新 CSV/XLSX，不覆盖输入。", SpreadsheetStageParams, ActionKind.WRITE, "R2", False, True, False, False, 60))
    registry.register(DesktopToolDefinition("spreadsheet.commit", "确认后将哈希未变化且通过校验的工作簿交付到 output。", SpreadsheetCommitParams, ActionKind.WRITE, "R3", False, True, False, False, 30))
    registry.register(DesktopToolDefinition(
        name="browser.open",
        description="读取用户授权域名内的公开 HTTPS 页面，不登录、不提交表单。",
        params_model=BrowserOpenParams,
        action_kind=ActionKind.NAVIGATE,
        risk_level="R1",
        read_only=True,
        side_effect=False,
        idempotent=True,
        retryable=True,
        timeout_seconds=20,
    ))
    registry.register(DesktopToolDefinition(
        name="document.stage_markdown",
        description="只向任务 staging 写入带引用的 Markdown 草稿。",
        params_model=StageMarkdownParams,
        action_kind=ActionKind.WRITE,
        risk_level="R2",
        read_only=False,
        side_effect=True,
        idempotent=False,
        retryable=False,
        timeout_seconds=30,
    ))
    registry.register(DesktopToolDefinition(
        name="document.commit_markdown",
        description="将经批准且哈希未变化的 staging Markdown 交付到 output。",
        params_model=CommitMarkdownParams,
        action_kind=ActionKind.WRITE,
        risk_level="R3",
        read_only=False,
        side_effect=True,
        idempotent=False,
        retryable=False,
        timeout_seconds=30,
    ))
    registry.register(DesktopToolDefinition(
        name="document.stage_docx",
        description="将已通过引用审查的 Markdown 转为 DOCX，并完成结构与渲染检查后存入任务 staging。",
        params_model=StageDocxParams,
        action_kind=ActionKind.WRITE,
        risk_level="R2",
        read_only=False,
        side_effect=True,
        idempotent=False,
        retryable=False,
        timeout_seconds=120,
    ))
    registry.register(DesktopToolDefinition(
        name="document.commit_docx",
        description="将已通过哈希复核的 staging DOCX 交付到 output 目录。",
        params_model=CommitDocxParams,
        action_kind=ActionKind.WRITE,
        risk_level="R3",
        read_only=False,
        side_effect=True,
        idempotent=False,
        retryable=False,
        timeout_seconds=30,
    ))
    registry.register(DesktopToolDefinition("document.inspect_docx", "读取授权 DOCX 的正文、标题和表格，不修改源文件。", DocxInspectParams, ActionKind.READ, "R0", True, False, True, True, 30))
    registry.register(DesktopToolDefinition("document.stage_pdf", "将授权 DOCX 渲染并完成 PDF 结构与页面检查后写入 task staging。", StagePdfParams, ActionKind.WRITE, "R2", False, True, False, False, 120))
    registry.register(DesktopToolDefinition("document.commit_pdf", "确认后将已检查且哈希未变化的 staging PDF 交付到 output。", CommitPdfParams, ActionKind.WRITE, "R3", False, True, False, False, 30))
    registry.register(DesktopToolDefinition("mail.stage_eml", "生成仅本地保存、不发送的标准 .eml 邮件草稿并写入 task staging。", StageEmlParams, ActionKind.WRITE, "R2", False, True, False, False, 30))
    registry.register(DesktopToolDefinition("mail.commit_eml", "交付只读本地 .eml 草稿；没有发送邮件能力。", CommitEmlParams, ActionKind.WRITE, "R2", False, True, False, False, 30))
    registry.register(DesktopToolDefinition(
        name="files.scan",
        description="扫描用户授权的整理目录，仅返回文件清单、分类建议与冲突。",
        params_model=FileScanParams,
        action_kind=ActionKind.READ,
        risk_level="R0",
        read_only=True,
        side_effect=False,
        idempotent=True,
        retryable=True,
        timeout_seconds=30,
    ))
    registry.register(DesktopToolDefinition(
        name="files.move",
        description="在同一用户授权整理目录内移动一个已预览、未冲突的普通文件。",
        params_model=FileMoveParams,
        action_kind=ActionKind.MOVE,
        risk_level="R3",
        read_only=False,
        side_effect=True,
        idempotent=False,
        retryable=False,
        timeout_seconds=30,
    ))
    registry.register(DesktopToolDefinition(
        name="files.rollback_move",
        description="将已成功的受控文件移动按 journal 逆序回滚；仍需独立确认。",
        params_model=FileMoveParams,
        action_kind=ActionKind.MOVE,
        risk_level="R3",
        read_only=False,
        side_effect=True,
        idempotent=False,
        retryable=False,
        timeout_seconds=30,
    ))
    registry.register(DesktopToolDefinition("desktop.uia.observe", "读取白名单测试窗口的 UI Automation 状态。", DesktopObserveParams, ActionKind.DESKTOP, "R0", True, False, True, True, 15))
    registry.register(DesktopToolDefinition("desktop.uia.set_text", "向白名单测试窗口的已识别 Edit 控件写入文本。", DesktopTextParams, ActionKind.DESKTOP, "R2", False, True, False, False, 15))
    registry.register(DesktopToolDefinition("desktop.uia.invoke", "调用白名单测试窗口的已识别低风险 Button 控件。", DesktopInvokeParams, ActionKind.DESKTOP, "R2", False, True, False, False, 15))
    registry.register(DesktopToolDefinition("desktop.visual_fallback", "仅在固定测试窗口、状态哈希未变时执行窗口相对坐标 fallback。", DesktopFallbackParams, ActionKind.DESKTOP, "R3", False, True, False, False, 15))
    return registry
