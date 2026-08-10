"""Build a local, static Demo UI from live traces or recorded real-run snapshots."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from localdesk.desktop.dashboard import load_task_run, render_demo_ui


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT = REPO_ROOT / "demo" / "recorded_showcase.json"
DEFAULT_METRICS = REPO_ROOT / "evaluation" / "results" / "product_eval_v2.json"


def _parse_run(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--run 格式必须是 标签=TASK_DIR")
    label, raw_path = value.split("=", 1)
    if not label.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("--run 的标签和路径都不能为空")
    return label.strip(), Path(raw_path).expanduser().resolve()


def _sanitize(value: Any, roots: list[Path]) -> Any:
    if isinstance(value, dict):
        return {_sanitize(key, roots): _sanitize(item, roots) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, roots) for item in value]
    if isinstance(value, str):
        result = value
        for index, root in enumerate(roots, start=1):
            marker = f"<recorded-run-{index}>"
            result = result.replace(str(root), marker).replace(str(root).replace("\\", "/"), marker)
        return result
    return value


def record_snapshot(run_specs: list[tuple[str, Path]], output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"拒绝覆盖已有录制快照：{output}")
    runs = [
        load_task_run(
            task_dir,
            label=label,
            mode="recorded_real_trace",
            source_note="来自已完成真实 Demo 的 Task Trace；用于稳定回放，不代表当前正在执行。",
        )
        for label, task_dir in run_specs
    ]
    roots = [task_dir.parents[1] for _, task_dir in run_specs]
    payload = {
        "version": "localdesk-recorded-showcase-v1",
        "recorded_at": datetime.now(UTC).isoformat(),
        "truth_label": "recorded_real_trace",
        "runs": _sanitize(runs, roots),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _load_metrics(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload.get("summary", {}))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the LocalDesk static Agent execution console.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record_parser = subparsers.add_parser("record", help="Create a sanitized snapshot from completed real Task traces")
    record_parser.add_argument("--run", action="append", type=_parse_run, required=True, metavar="LABEL=TASK_DIR")
    record_parser.add_argument("--output", type=Path, required=True)

    render_parser = subparsers.add_parser("render", help="Render a local static HTML console")
    render_parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    render_parser.add_argument("--run", action="append", type=_parse_run, metavar="LABEL=TASK_DIR")
    render_parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    render_parser.add_argument("--output", type=Path, default=REPO_ROOT / ".localdesk" / "demo-ui" / "index.html")
    args = parser.parse_args()

    if args.command == "record":
        result = record_snapshot(args.run, args.output.resolve())
        print(json.dumps({"runs": len(result["runs"]), "output": str(args.output.resolve())}, ensure_ascii=False, indent=2))
        return 0

    if args.run:
        runs = [load_task_run(task_dir, label=label) for label, task_dir in args.run]
    else:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        runs = list(snapshot["runs"])
    target = render_demo_ui(runs, args.output, metrics=_load_metrics(args.metrics))
    print(json.dumps({"runs": len(runs), "output": str(target)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
