from pathlib import Path

from localdesk.desktop.dashboard import load_task_run, render_demo_ui, render_task_board
from localdesk.desktop.demo_ui import record_snapshot
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig


def test_task_board_renders_real_task_state(tmp_path: Path) -> None:
    source, output, tasks = tmp_path / "source", tmp_path / "output", tmp_path / "tasks"
    for path in (source, output, tasks): path.mkdir()
    workspace = DesktopWorkspace(WorkspaceConfig(read_roots=[source], output_root=output, task_root=tasks))
    store = TaskTraceStore(workspace)
    service = DesktopTaskService(DesktopPolicyGuard(workspace), store)
    task = service.create_task("real trace task")
    board = render_task_board(store)
    text = board.read_text(encoding="utf-8")
    assert task.task_id in text and "real trace task" in text and "draft" in text
    assert "Trace Timeline" in text and "只读 UI" in text


def test_task_board_has_honest_empty_state(tmp_path: Path) -> None:
    source, output, tasks = tmp_path / "source", tmp_path / "output", tmp_path / "tasks"
    for path in (source, output, tasks):
        path.mkdir()
    workspace = DesktopWorkspace(WorkspaceConfig(read_roots=[source], output_root=output, task_root=tasks))

    board = render_task_board(TaskTraceStore(workspace))
    text = board.read_text(encoding="utf-8")

    assert "还没有可展示的任务" in text
    assert '"runs": []' in text


def test_demo_ui_combines_two_real_trace_runs_and_metrics(tmp_path: Path) -> None:
    runs = []
    for index, label in enumerate(("AI 资讯周报", "报销核对"), start=1):
        root = tmp_path / f"run-{index}"
        source, output, tasks = root / "source", root / "output", root / "tasks"
        for path in (source, output, tasks):
            path.mkdir(parents=True)
        workspace = DesktopWorkspace(WorkspaceConfig(read_roots=[source], output_root=output, task_root=tasks))
        store = TaskTraceStore(workspace)
        service = DesktopTaskService(DesktopPolicyGuard(workspace), store)
        task = service.create_task(f"{label}</script>")
        store.append(task.task_id, "main_agent_planned", {"intent": label, "steps": ["第一步", "第二步"]})
        runs.append(load_task_run(workspace.task_dir(task.task_id), label=label))

    target = render_demo_ui(runs, tmp_path / "index.html", metrics={"task_count": 18, "passed": 18})
    text = target.read_text(encoding="utf-8")

    assert "AI 资讯周报" in text and "报销核对" in text
    assert '"task_count": 18' in text
    assert "</script></script>" not in text
    assert "\\u003c/script>" in text


def test_recorded_showcase_sanitizes_local_paths(tmp_path: Path) -> None:
    run_root = tmp_path / "private-run"
    source, output, tasks = run_root / "source", run_root / "deliveries", run_root / "tasks"
    for path in (source, output, tasks):
        path.mkdir(parents=True)
    workspace = DesktopWorkspace(WorkspaceConfig(read_roots=[source], output_root=output, task_root=tasks))
    store = TaskTraceStore(workspace)
    task = DesktopTaskService(DesktopPolicyGuard(workspace), store).create_task("record me")
    private_path = str(run_root / "secret.txt")
    store.append(task.task_id, "private_path", {"path": private_path, "hashes": {private_path: "abc123"}})

    output_path = tmp_path / "recorded.json"
    record_snapshot([("Demo", workspace.task_dir(task.task_id))], output_path)
    text = output_path.read_text(encoding="utf-8")

    assert str(run_root) not in text
    assert "<recorded-run-1>" in text
    assert '"truth_label": "recorded_real_trace"' in text
