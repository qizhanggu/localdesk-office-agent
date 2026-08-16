"""Read-only Demo UI rendered directly from task.json and events.jsonl."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from localdesk.desktop.trace_store import TaskTraceStore


TEMPLATE_PATH = Path(__file__).with_name("demo_ui_template.html")


def load_task_run(
    task_dir: Path,
    *,
    label: str,
    mode: str = "live_trace",
    source_note: str = "数据直接来自本地 Task Trace。",
    known_limitations: Iterable[str] = (),
) -> dict[str, Any]:
    task_dir = task_dir.resolve()
    task_path = task_dir / "task.json"
    events_path = task_dir / "events.jsonl"
    if not task_path.is_file():
        raise ValueError(f"找不到 task.json：{task_path}")
    task = json.loads(task_path.read_text(encoding="utf-8"))
    events = []
    if events_path.is_file():
        events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {
        "label": label,
        "mode": mode,
        "source_note": source_note,
        "known_limitations": list(known_limitations),
        "task": task,
        "events": events,
    }


def render_demo_ui(
    runs: list[dict[str, Any]],
    target: Path,
    *,
    metrics: dict[str, Any] | None = None,
    title: str = "LocalDesk · Agent Execution Console",
) -> Path:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = {
        "title": title,
        "runs": runs,
        "metrics": metrics or {},
    }
    serialized = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    document = template.replace("__LOCALDESK_DATA__", serialized)
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8", newline="\n")
    return target


def render_task_board(store: TaskTraceStore) -> Path:
    """Compatibility entrypoint: render every task in one Trace store."""
    runs: list[dict[str, Any]] = []
    if store.workspace.task_root.exists():
        task_dirs = sorted(
            (path for path in store.workspace.task_root.iterdir() if path.is_dir() and (path / "task.json").is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for task_dir in task_dirs:
            task = store.load_task(task_dir.name)
            label = str(task.get("user_query", task_dir.name))[:36]
            runs.append(load_task_run(task_dir, label=label))
    target = store.workspace.task_root / "task_board.html"
    return render_demo_ui(runs, target, title="LocalDesk · Task Board")
