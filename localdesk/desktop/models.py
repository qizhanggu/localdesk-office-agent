from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class TaskStatus(str, Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset(
    {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}
)


class ActionKind(str, Enum):
    READ = "read"
    NAVIGATE = "navigate"
    WRITE = "write"
    MOVE = "move"
    RENAME = "rename"
    DELETE = "delete"
    SHELL = "shell"
    NETWORK = "network"
    DESKTOP = "desktop"


@dataclass
class PlannedAction:
    action_id: str
    skill: str
    kind: ActionKind
    args: dict[str, Any]
    summary: str
    requires_confirmation: bool = False
    status: str = "pending"
    preview: dict[str, Any] = field(default_factory=dict)


@dataclass
class Artifact:
    kind: str
    staged_path: str | None = None
    final_path: str | None = None
    sha256: str | None = None
    summary: str = ""


@dataclass
class TraceEvent:
    sequence: int
    event_type: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=utc_now)


@dataclass
class Task:
    task_id: str
    user_query: str
    status: TaskStatus = TaskStatus.DRAFT
    plan: str = ""
    actions: list[PlannedAction] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def create(cls, user_query: str) -> "Task":
        return cls(task_id=str(uuid4()), user_query=user_query)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        actions = [PlannedAction(action_id=item["action_id"], skill=item["skill"], kind=ActionKind(item["kind"]), args=item["args"], summary=item["summary"], requires_confirmation=item.get("requires_confirmation", False), status=item.get("status", "pending"), preview=item.get("preview", {})) for item in data.get("actions", [])]
        artifacts = [Artifact(**item) for item in data.get("artifacts", [])]
        return cls(task_id=data["task_id"], user_query=data["user_query"], status=TaskStatus(data["status"]), plan=data.get("plan", ""), actions=actions, artifacts=artifacts, error=data.get("error"), created_at=data["created_at"], updated_at=data["updated_at"])
