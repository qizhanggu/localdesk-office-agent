from __future__ import annotations

import json
import hashlib
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceError

_CATEGORIES = {".pdf": "PDF", ".png": "Images", ".jpg": "Images", ".jpeg": "Images", ".zip": "Archives", ".rar": "Archives", ".7z": "Archives", ".txt": "Text", ".md": "Text"}


@dataclass(frozen=True)
class FileOperation:
    operation_id: str
    source: str
    destination: str
    category: str
    source_sha256: str = ""
    source_size_bytes: int = 0


@dataclass(frozen=True)
class FilePlan:
    operations: list[FileOperation]
    conflicts: list[str]


class FileSkill:
    def __init__(self, workspace: DesktopWorkspace, *, is_symlink=None, mover=None) -> None:
        self.workspace = workspace
        self._is_symlink = is_symlink or (lambda path: path.is_symlink())
        self._mover = mover or shutil.move

    def dry_run(self, root: str | Path) -> FilePlan:
        root_path = self.workspace.resolve_path(root)
        if not self.workspace.can_manage(root_path):
            raise WorkspaceError("整理根目录不在 managed_roots")
        operations: list[FileOperation] = []; conflicts: list[str] = []
        for path in sorted(root_path.rglob("*")):
            if self._is_unsafe_link(path):
                conflicts.append(f"符号链接拒绝（含 junction）: {path}"); continue
            if not path.is_file(): continue
            if not self.workspace.can_manage(path):
                conflicts.append(f"越权路径: {path}"); continue
            category = _CATEGORIES.get(path.suffix.lower(), "Other")
            if path.parent == root_path / category:
                continue
            target = root_path / category / path.name
            if target.exists():
                conflicts.append(f"目标已存在: {target}"); continue
            operations.append(FileOperation(
                f"op-{len(operations)+1}",
                str(path),
                str(target),
                category,
                self._sha256(path),
                path.stat().st_size,
            ))
        return FilePlan(operations, conflicts)

    def execute(self, operations: list[FileOperation], journal_path: Path) -> list[FileOperation]:
        completed: list[FileOperation] = []
        for operation in operations:
            source, destination = Path(operation.source), Path(operation.destination)
            try:
                self._validate(source, destination, operation)
                destination.parent.mkdir(parents=True, exist_ok=True)
                self._mover(str(source), str(destination))
            except Exception as exc:
                self._journal(journal_path, "failed", operation, str(exc)); raise WorkspaceError(f"操作失败并停止: {exc}") from exc
            self._journal(journal_path, "succeeded", operation); completed.append(operation)
        return completed

    def rollback_plan(self, journal_path: Path) -> FilePlan:
        if not journal_path.exists(): raise WorkspaceError("没有 operation journal")
        successful = [json.loads(line)["operation"] for line in journal_path.read_text(encoding="utf-8").splitlines() if json.loads(line)["status"] == "succeeded"]
        ops = [
            FileOperation(
                f"rollback-{i}",
                item["destination"],
                item["source"],
                item["category"],
                item.get("source_sha256", ""),
                item.get("source_size_bytes", 0),
            )
            for i, item in enumerate(reversed(successful), 1)
        ]
        conflicts = [f"目标已存在: {op.destination}" for op in ops if Path(op.destination).exists()]
        return FilePlan(ops, conflicts)

    def _validate(self, source: Path, destination: Path, operation: FileOperation) -> None:
        if not self.workspace.can_manage(source) or not self.workspace.can_manage(destination): raise WorkspaceError("文件操作越出 managed_roots")
        if self._is_unsafe_link(source) or not source.is_file(): raise WorkspaceError("源文件不存在、不是普通文件或为符号链接/junction")
        if destination.exists(): raise WorkspaceError("禁止覆盖已有目标文件")
        if operation.source_sha256 and (
            source.stat().st_size != operation.source_size_bytes
            or self._sha256(source) != operation.source_sha256
        ):
            raise WorkspaceError("预览后源文件已变化，需要重新 dry-run 并确认")

    def _is_unsafe_link(self, path: Path) -> bool:
        is_junction = getattr(path, "is_junction", lambda: False)
        return self._is_symlink(path) or is_junction()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _journal(path: Path, status: str, operation: FileOperation, error: str | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"status": status, "operation": asdict(operation), "error": error}
        with path.open("a", encoding="utf-8", newline="\n") as f: f.write(json.dumps(payload, ensure_ascii=False) + "\n")
