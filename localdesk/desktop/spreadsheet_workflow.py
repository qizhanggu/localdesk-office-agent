from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from localdesk.desktop.models import ActionKind, Artifact, PlannedAction, Task, TaskStatus
from localdesk.desktop.registry import DesktopToolRegistry, create_desktop_registry
from localdesk.desktop.service import DesktopTaskService, TaskStateError
from localdesk.desktop.skills.spreadsheet import SpreadsheetSkill, SpreadsheetTransform, StagedSpreadsheet


class SpreadsheetWorkflow:
    """将结构化表格转换接入 Task、Policy、Trace 与确认交付。"""

    def __init__(self, service: DesktopTaskService, spreadsheets: SpreadsheetSkill, registry: DesktopToolRegistry | None = None) -> None:
        self.service, self.spreadsheets = service, spreadsheets
        self.registry = registry or create_desktop_registry(service)

    def prepare(self, task: Task, source_path: str, output_filename: str, transform: SpreadsheetTransform) -> StagedSpreadsheet:
        if task.status != TaskStatus.DRAFT:
            raise TaskStateError("只有 draft 任务可以准备表格转换")
        inspection = self.registry.execute(
            task,
            PlannedAction("spreadsheet-inspect", "spreadsheet.inspect", ActionKind.READ, {"path": source_path}, "读取授权工作簿结构"),
            lambda: self.spreadsheets.inspect(source_path),
            verify=lambda result: bool(result.sheets),
        )
        staged_path = self.spreadsheets.workspace.task_dir(task.task_id) / "staging" / output_filename
        staged = self.registry.execute(
            task,
            PlannedAction("spreadsheet-stage", "spreadsheet.stage_transform", ActionKind.WRITE, {"source": source_path, "destination": str(staged_path)}, "将结构化转换结果写入 task staging"),
            lambda: self.spreadsheets.stage_transform(task.task_id, source_path, output_filename, transform),
            verify=lambda result: result.validation.approved and Path(result.staged_path).is_file(),
        )
        action = PlannedAction(
            "spreadsheet-commit", "spreadsheet.commit", ActionKind.WRITE,
            {"destination": staged.final_path}, "确认后交付已校验的新工作簿",
            preview={"staged": asdict(staged), "inspection": asdict(inspection)},
        )
        self.service.set_plan(task, "读取授权工作簿，执行确定性结构化转换，确认后交付新文件。", [action])
        self.service.trace_store.append(task.task_id, "spreadsheet_staged", asdict(staged))
        return staged

    def confirm_and_deliver(self, task: Task, approved: bool) -> None:
        if task.status != TaskStatus.AWAITING_CONFIRMATION:
            raise TaskStateError("表格任务不在等待确认状态")
        self.service.confirm(task, approved)
        if not approved: return
        action = task.actions[0]; draft = _draft(action.preview["staged"])
        try:
            self.spreadsheets.validate_commit(draft)
            self.registry.execute(task, action, lambda: self.spreadsheets.commit(draft), verify=lambda _: Path(draft.final_path).is_file())
            self.service.add_artifact(task, Artifact("spreadsheet", draft.staged_path, draft.final_path, draft.sha256, "已通过哈希与确定性校验的工作簿"))
            action.status = "succeeded"; self.service.finish(task)
        except Exception as exc:
            self.service.finish(task, str(exc)); raise


def _draft(data: dict) -> StagedSpreadsheet:
    from localdesk.desktop.skills.spreadsheet import SpreadsheetValidation
    return StagedSpreadsheet(
        staged_path=data["staged_path"], final_path=data["final_path"], source_path=data["source_path"], source_sha256=data["source_sha256"], sha256=data["sha256"], summary=data["summary"], validation=SpreadsheetValidation(**data["validation"]),
    )
