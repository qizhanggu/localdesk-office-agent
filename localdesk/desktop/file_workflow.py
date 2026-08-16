from __future__ import annotations

from localdesk.desktop.models import ActionKind, Artifact, PlannedAction, Task, TaskStatus
from localdesk.desktop.registry import DesktopToolRegistry, create_desktop_registry
from localdesk.desktop.service import DesktopTaskService, TaskStateError
from localdesk.desktop.skills.files import FilePlan, FileSkill


class FileOrganizationWorkflow:
    def __init__(self, service: DesktopTaskService, files: FileSkill, registry: DesktopToolRegistry | None = None) -> None:
        self.service, self.files = service, files
        self.registry = registry or create_desktop_registry(service)

    def prepare(self, task: Task, root: str) -> FilePlan:
        scan_action = PlannedAction("files-scan", "files.scan", ActionKind.READ, {"path": root}, "扫描授权目录，生成整理预览")
        plan = self.registry.execute(
            task,
            scan_action,
            lambda: self.files.dry_run(root),
            verify=lambda result: isinstance(result, FilePlan),
        )
        if plan.conflicts: raise TaskStateError("dry-run 存在冲突，拒绝进入确认")
        actions = [PlannedAction(
            op.operation_id,
            "files.move",
            ActionKind.MOVE,
            {"source": op.source, "destination": op.destination},
            f"移动到 {op.category}",
            preview={"category": op.category, "source_sha256": op.source_sha256, "source_size_bytes": op.source_size_bytes},
        ) for op in plan.operations]
        self.service.set_plan(task, "按确定性扩展名规则整理文件", actions)
        self.service.trace_store.append(task.task_id, "file_dry_run", {"total_operations": len(plan.operations), "conflicts": plan.conflicts, "operations": [op.__dict__ for op in plan.operations]})
        return plan

    def confirm_and_execute(self, task: Task, approved: bool) -> None:
        self.service.confirm(task, approved)
        if not approved: return
        try:
            done = []
            for action in task.actions:
                operation = self._op(action)
                tool_name = "files.rollback_move" if action.action_id.startswith("rollback-") else "files.move"
                action.skill = tool_name
                completed = self.registry.execute(
                    task,
                    action,
                    lambda operation=operation: self.files.execute([operation], self.journal_path(task)),
                    verify=lambda result: len(result) == 1 and not __import__("pathlib").Path(action.args["source"]).exists() and __import__("pathlib").Path(action.args["destination"]).exists(),
                )
                done.extend(completed)
                action.status = "succeeded"
        except Exception as exc:
            self.service.finish(task, str(exc)); raise
        self.service.trace_store.append(task.task_id, "file_operations_completed", {"count": len(done), "journal": str(self.journal_path(task))})
        self.service.add_artifact(task, Artifact(kind="file_operation_journal", staged_path=str(self.journal_path(task)), sha256=FileSkill._sha256(self.journal_path(task)), summary=f"{len(done)} 个文件操作的可回滚 journal"))
        self.service.finish(task)

    def prepare_rollback(self, rollback_task: Task, original_task: Task) -> FilePlan:
        rollback_scan = PlannedAction("rollback-scan", "files.scan", ActionKind.READ, {"path": str(self.journal_path(original_task))}, "读取原任务 journal，生成回滚预览")
        plan = self.registry.execute(
            rollback_task,
            rollback_scan,
            lambda: self.files.rollback_plan(self.journal_path(original_task)),
            verify=lambda result: isinstance(result, FilePlan),
        )
        if plan.conflicts: raise TaskStateError("rollback 存在冲突，拒绝进入确认")
        actions = [PlannedAction(
            op.operation_id,
            "files.rollback_move",
            ActionKind.MOVE,
            {"source": op.source, "destination": op.destination},
            "回滚文件移动",
            preview={"category": op.category, "source_sha256": op.source_sha256, "source_size_bytes": op.source_size_bytes, "original_task_id": original_task.task_id},
        ) for op in plan.operations]
        self.service.set_plan(rollback_task, f"回滚任务 {original_task.task_id} 的已完成操作", actions)
        self.service.trace_store.append(rollback_task.task_id, "rollback_dry_run", {"original_task_id": original_task.task_id, "total_operations": len(plan.operations), "conflicts": plan.conflicts})
        return plan

    def journal_path(self, task: Task): return self.service.trace_store.workspace.task_dir(task.task_id) / "operations.jsonl"
    @staticmethod
    def _op(action: PlannedAction):
        from localdesk.desktop.skills.files import FileOperation
        return FileOperation(
            action.action_id,
            action.args["source"],
            action.args["destination"],
            action.preview.get("category", action.summary),
            action.preview.get("source_sha256", ""),
            action.preview.get("source_size_bytes", 0),
        )
