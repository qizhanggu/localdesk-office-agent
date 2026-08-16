"""生成 Phase 2 受控网页研究的离线回归证据。

这不是联网成功率，也不把测试用例数量当作用户任务成功率。它只记录
Fake/Mock Browser 与确定性 Reviewer 下可重复的安全闭环测试结果。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from run_baseline import REPOSITORY_ROOT, load_task_set, parse_pytest_summary, write_json


TASK_SET_PATH = REPOSITORY_ROOT / "evaluation" / "phase2_tasks.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "evaluation" / "results" / "phase2_controlled_research.json"
PHASE2_TEST_TARGETS = (
    "tests/test_desktop_foundation.py",
    "tests/test_desktop_reporting.py",
)


def run_phase2_suite() -> tuple[list[str], int, str]:
    with tempfile.TemporaryDirectory(prefix="localdesk-phase2-") as base_temp:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *PHASE2_TEST_TARGETS,
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
    executed = sum(summary.values())
    measured = summary["passed"] + summary["failed"] + summary["error"]
    if return_code == 0 and not executed:
        raise RuntimeError("pytest exited successfully but no summary could be parsed")
    return {
        "schema_version": 1,
        "phase": "phase2",
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "offline controlled public-web research and deterministic-review regression",
        "command": command,
        "pytest_return_code": return_code,
        "test_summary": {**summary, "executed": executed},
        "evaluation_task_set": {
            "path": str(TASK_SET_PATH.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
            "task_count": len(tasks),
            "by_type": dict(sorted(Counter(str(task.get("type", "unknown")) for task in tasks).items())),
        },
        "measured_metrics": {
            "phase2_regression_pass_rate": (summary["passed"] / measured) if measured else None,
        },
        "not_measured": [
            "live_internet_task_success_rate",
            "search_engine_discovery_quality",
            "citation_factual_correctness",
            "browser_latency",
            "model_quality_or_cost",
        ],
        "notes": [
            "Every browser response is supplied by FakeBrowserAdapter or httpx.MockTransport; no live website is used in this regression result.",
            "The task set describes covered scenarios. It is not reported as an end-to-end task-success percentage.",
        ],
    }


def main() -> int:
    tasks = load_task_set(TASK_SET_PATH)
    command, return_code, output = run_phase2_suite()
    result = build_result(command, return_code, output, tasks)
    write_json(DEFAULT_OUTPUT, result)
    print(json.dumps(result["test_summary"], ensure_ascii=False, sort_keys=True))
    print(f"phase2_result={DEFAULT_OUTPUT}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
