"""运行并保存 LocalDesk 的离线 Phase 0 回归基线。

此脚本刻意不调用真实模型、浏览器或桌面环境。它记录稳定核心测试的
真实结果，以及评估任务集的规模和类别；尚未覆盖的指标会明确标为未测。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
TASK_SET_PATH = REPOSITORY_ROOT / "evaluation" / "evaluation_tasks.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "evaluation" / "results" / "phase0_core_baseline.json"
CORE_TEST_TARGETS = (
    "tests/test_file_workflow.py",
    "tests/test_desktop_foundation.py",
    "tests/test_desktop_reporting.py",
    "tests/test_grounded_renderer.py",
)


def parse_pytest_summary(output: str) -> dict[str, int]:
    """提取 pytest 最终摘要；没有出现的字段按 0 记录。"""

    return {
        name: int(match.group(1)) if (match := re.search(rf"(\d+) {name}", output)) else 0
        for name in ("passed", "failed", "skipped", "error")
    }


def load_task_set(path: Path) -> list[dict[str, str]]:
    tasks = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(tasks, list) or not all(isinstance(item, dict) for item in tasks):
        raise ValueError(f"Invalid evaluation task set: {path}")
    return tasks


def run_core_suite() -> tuple[list[str], int, str]:
    """在系统临时目录运行，避免在仓库生成 pytest 缓存或临时文件。"""

    with tempfile.TemporaryDirectory(prefix="localdesk-phase0-") as base_temp:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *CORE_TEST_TARGETS,
            "-p",
            "no:cacheprovider",
            "--basetemp",
            base_temp,
        ]
        completed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    return command, completed.returncode, completed.stdout + completed.stderr


def build_result(command: list[str], return_code: int, output: str, tasks: list[dict[str, str]]) -> dict:
    summary = parse_pytest_summary(output)
    executed = summary["passed"] + summary["failed"] + summary["skipped"] + summary["error"]
    if return_code == 0 and executed == 0:
        raise RuntimeError("pytest exited successfully but no summary could be parsed")
    measured = summary["passed"] + summary["failed"] + summary["error"]
    return {
        "schema_version": 1,
        "phase": "phase0",
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "offline deterministic core regression baseline",
        "command": command,
        "pytest_return_code": return_code,
        "test_summary": {**summary, "executed": executed},
        "evaluation_task_set": {
            "path": str(TASK_SET_PATH.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
            "task_count": len(tasks),
            "by_type": dict(sorted(Counter(str(task.get("type", "unknown")) for task in tasks).items())),
        },
        "measured_metrics": {
            "core_regression_pass_rate": (summary["passed"] / measured) if measured else None,
        },
        "not_measured": [
            "end_to_end_task_success_rate",
            "citation_validity",
            "citation_completeness",
            "model_cost",
            "browser_or_desktop_tool_latency",
        ],
        "notes": [
            "This baseline is test-level evidence, not a claim that every evaluation task has passed.",
            "Real model, browser, and desktop adapters are deliberately excluded from Phase 0.",
        ],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the LocalDesk Phase 0 regression baseline")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSON result path")
    args = parser.parse_args()

    tasks = load_task_set(TASK_SET_PATH)
    command, return_code, output = run_core_suite()
    result = build_result(command, return_code, output, tasks)
    output_path = args.output if args.output.is_absolute() else REPOSITORY_ROOT / args.output
    write_json(output_path, result)
    print(json.dumps(result["test_summary"], ensure_ascii=False, sort_keys=True))
    print(f"baseline_result={output_path}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
