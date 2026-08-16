from __future__ import annotations

import json
import os
from pathlib import Path

from localdesk.desktop.models import Task, TraceEvent
from localdesk.desktop.workspace import DesktopWorkspace


class TaskTraceStore:
    def __init__(self, workspace: DesktopWorkspace) -> None:
        self.workspace = workspace

    def create(self, task: Task) -> None:
        task_dir = self.workspace.task_dir(task.task_id)
        task_dir.mkdir(parents=True, exist_ok=False)
        self.save_task(task)
        self.append(task.task_id, "task_created", {"user_query": task.user_query})

    def save_task(self, task: Task) -> None:
        self._atomic_json(self._task_path(task.task_id), task.to_dict())

    def load_task(self, task_id: str) -> dict:
        return json.loads(self._task_path(task_id).read_text(encoding="utf-8"))

    def load_task_object(self, task_id: str) -> Task:
        return Task.from_dict(self.load_task(task_id))

    def append(self, task_id: str, event_type: str, payload: dict) -> TraceEvent:
        events_path = self._events_path(task_id)
        sequence = 1
        if events_path.exists():
            sequence = sum(1 for _ in events_path.open(encoding="utf-8")) + 1
        event = TraceEvent(sequence=sequence, event_type=event_type, payload=payload)
        with events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event.__dict__, ensure_ascii=False, sort_keys=True) + "\n")
        return event

    def load_events(self, task_id: str) -> list[dict]:
        path = self._events_path(task_id)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def _task_path(self, task_id: str) -> Path:
        return self.workspace.task_dir(task_id) / "task.json"

    def _events_path(self, task_id: str) -> Path:
        return self.workspace.task_dir(task_id) / "events.jsonl"

    @staticmethod
    def _atomic_json(path: Path, payload: dict) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
