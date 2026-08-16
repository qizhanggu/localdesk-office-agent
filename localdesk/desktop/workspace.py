from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


class WorkspaceError(ValueError):
    """用户提供的工作区配置或路径不满足 LocalDesk 的硬边界。"""


@dataclass(frozen=True)
class WorkspaceConfig:
    """用户显式授权的目录。

    read_roots 只允许读取资料。managed_roots 用于用户要求“整理这个目录”
    的场景，允许在目录内部移动/重命名；output_root 专用于交付产物。
    """

    read_roots: list[Path]
    output_root: Path
    task_root: Path
    managed_roots: list[Path] = field(default_factory=list)
    browser_allowed_domains: list[str] = field(default_factory=list)
    desktop_allowed_window_titles: list[str] = field(default_factory=list)


class DesktopWorkspace:
    def __init__(self, config: WorkspaceConfig) -> None:
        self.read_roots = self._resolve_roots(config.read_roots, "read_roots")
        self.managed_roots = self._resolve_roots(config.managed_roots, "managed_roots")
        self.output_root = self._resolve_root(config.output_root, "output_root")
        self.task_root = self._resolve_root(config.task_root, "task_root")
        self.browser_allowed_domains = self._normalize_domains(config.browser_allowed_domains)
        self.desktop_allowed_window_titles = tuple(title.strip() for title in config.desktop_allowed_window_titles if title.strip())

    @staticmethod
    def _normalize_domains(domains: list[str]) -> tuple[str, ...]:
        normalized = tuple(domain.strip().lower() for domain in domains if domain.strip())
        if len(set(normalized)) != len(normalized):
            raise WorkspaceError("browser_allowed_domains 不允许重复域名")
        if any("/" in domain or ":" in domain for domain in normalized):
            raise WorkspaceError("browser_allowed_domains 只接受域名，不接受 URL")
        return normalized

    @staticmethod
    def _resolve_root(path: Path, name: str) -> Path:
        candidate = path.expanduser()
        if not candidate.is_absolute():
            raise WorkspaceError(f"{name} 必须是绝对路径")
        return candidate.resolve(strict=False)

    def _resolve_roots(self, paths: list[Path], name: str) -> tuple[Path, ...]:
        if not paths:
            return ()
        roots = tuple(self._resolve_root(path, name) for path in paths)
        if len(set(roots)) != len(roots):
            raise WorkspaceError(f"{name} 不允许重复目录")
        return roots

    @staticmethod
    def resolve_path(path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            raise WorkspaceError("Desktop 路径必须使用绝对路径，禁止依赖当前工作目录")
        return candidate.resolve(strict=False)

    @staticmethod
    def _is_within(path: Path, roots: tuple[Path, ...] | list[Path]) -> bool:
        return any(_is_relative_to(path, root) for root in roots)

    def can_read(self, path: str | Path) -> bool:
        resolved = self.resolve_path(path)
        return self._is_within(
            resolved,
            (*self.read_roots, *self.managed_roots, self.output_root, self.task_root),
        )

    def can_write_artifact(self, path: str | Path) -> bool:
        resolved = self.resolve_path(path)
        return self._is_within(resolved, (self.output_root, self.task_root))

    def is_task_artifact(self, path: str | Path) -> bool:
        """判断路径是否位于任务私有 staging/trace 区。"""

        return self._is_within(self.resolve_path(path), (self.task_root,))

    def is_output_artifact(self, path: str | Path) -> bool:
        return self._is_within(self.resolve_path(path), (self.output_root,))

    def can_manage(self, path: str | Path) -> bool:
        resolved = self.resolve_path(path)
        return self._is_within(resolved, self.managed_roots)

    def can_browse(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host:
            return False
        return any(host == domain or host.endswith("." + domain) for domain in self.browser_allowed_domains)

    def can_automate_window(self, title: str) -> bool:
        return title in self.desktop_allowed_window_titles

    def task_dir(self, task_id: str) -> Path:
        if not task_id or any(char in task_id for char in "\\/:"):
            raise WorkspaceError("非法 task_id")
        return self.task_root / task_id


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
