"""生成 Phase 4 受控文件整理与回滚的离线回归证据。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime

from run_baseline import REPOSITORY_ROOT, load_task_set, parse_pytest_summary, write_json


TASK_SET_PATH = REPOSITORY_ROOT / "evaluation" / "phase4_tasks.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "evaluation" / "results" / "phase4_file_organization.json"
TEST_TARGETS = (
    "tests/test_file_workflow.py",
    "tests/test_desktop_foundation.py",
    "tests/test_desktop_reporting.py",
    "tests/test_grounded_renderer.py",
)


def main() -> int:
    tasks = load_task_set(TASK_SET_PATH)
    with tempfile.TemporaryDirectory(prefix="localdesk-phase4-") as base_temp:
        command = [sys.executable, "-m", "pytest", "-q", *TEST_TARGETS, "-p", "no:cacheprovider", "--basetemp", base_temp]
        completed = subprocess.run(command, cwd=REPOSITORY_ROOT, text=True, capture_output=True, check=False)
    summary = parse_pytest_summary(completed.stdout + completed.stderr)
    executed = sum(summary.values())
    measured = summary["passed"] + summary["failed"] + summary["error"]
    result = {
        "schema_version": 1,
        "phase": "phase4",
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "authorized file dry-run, independent confirmation, serial move journal, and separately confirmed rollback",
        "command": command,
        "pytest_return_code": completed.returncode,
        "test_summary": {**summary, "executed": executed},
        "evaluation_task_set": {
            "path": str(TASK_SET_PATH.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
            "task_count": len(tasks),
            "by_type": dict(sorted(Counter(str(task.get("type", "unknown")) for task in tasks).items())),
        },
        "measured_metrics": {
            "phase4_regression_pass_rate": (summary["passed"] / measured) if measured else None,
            "task_scenarios_covered": len(tasks),
        },
        "not_measured": ["real_user_download_directory_success_rate", "large_directory_latency", "junction_creation_rate_on_this_windows_account"],
        "notes": [
            "All file inputs are test-generated and non-sensitive.",
            "The skipped symlink case depends on Windows account permission; mocked symlink rejection is covered separately.",
            "This offline result does not claim arbitrary file-management capability outside managed_roots.",
        ],
    }
    write_json(DEFAULT_OUTPUT, result)
    print(json.dumps(result["test_summary"], ensure_ascii=False, sort_keys=True))
    print(f"phase4_result={DEFAULT_OUTPUT}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
