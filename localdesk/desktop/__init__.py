"""LocalDesk Agent 的受控桌面任务运行时。

该包与原有 Coding Agent 并存。Desktop v1 只暴露经过工作区和策略层
约束的能力，绝不复用默认 Coding Registry 中的 Bash 或编辑工具。
"""

from localdesk.desktop.models import (
    Artifact,
    PlannedAction,
    Task,
    TaskStatus,
    TraceEvent,
)
from localdesk.desktop.policy import DesktopPolicyGuard, PolicyDecision
from localdesk.desktop.reporting import KnowledgeReportWorkflow
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig

__all__ = [
    "Artifact",
    "DesktopPolicyGuard",
    "DesktopTaskService",
    "DesktopWorkspace",
    "KnowledgeReportWorkflow",
    "PlannedAction",
    "PolicyDecision",
    "Task",
    "TaskStatus",
    "TraceEvent",
    "WorkspaceConfig",
]
