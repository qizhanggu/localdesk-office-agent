"""生成 Phase 5 Windows UIA 与受限 fallback 的离线回归证据。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime

from run_baseline import REPOSITORY_ROOT, load_task_set, parse_pytest_summary, write_json

TASK_SET_PATH = REPOSITORY_ROOT / "evaluation" / "phase5_tasks.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "evaluation" / "results" / "phase5_desktop_computer_use.json"
TEST_TARGETS = ("tests/test_desktop_computer_use.py", "tests/test_file_workflow.py", "tests/test_desktop_foundation.py", "tests/test_desktop_reporting.py", "tests/test_grounded_renderer.py")


def main() -> int:
    tasks = load_task_set(TASK_SET_PATH)
    with tempfile.TemporaryDirectory(prefix="localdesk-phase5-") as base_temp:
        command = [sys.executable, "-m", "pytest", "-q", *TEST_TARGETS, "-p", "no:cacheprovider", "--basetemp", base_temp]
        completed = subprocess.run(command, cwd=REPOSITORY_ROOT, text=True, capture_output=True, check=False)
    summary = parse_pytest_summary(completed.stdout + completed.stderr)
    measured = summary["passed"] + summary["failed"] + summary["error"]
    result = {
        "schema_version": 1, "phase": "phase5", "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Windows UIA task orchestration, window whitelist, confirmation binding, manual takeover, and state-bound visual fallback",
        "command": command, "pytest_return_code": completed.returncode,
        "test_summary": {**summary, "executed": sum(summary.values())},
        "evaluation_task_set": {"path": str(TASK_SET_PATH.relative_to(REPOSITORY_ROOT)).replace("\\", "/"), "task_count": len(tasks), "by_type": dict(sorted(Counter(str(task["type"]) for task in tasks).items()))},
        "measured_metrics": {"phase5_regression_pass_rate": (summary["passed"] / measured) if measured else None, "task_scenarios_covered": len(tasks)},
        "not_measured": ["arbitrary_third_party_app_success_rate", "OCR_accuracy", "real_business_system_automation"],
        "notes": ["The automated suite uses a deterministic fake adapter for safety and repeatability.", "A separate interactive acceptance used the self-built WinForms test app and Windows Computer Use UIA tree; no external system or account was used."],
    }
    write_json(DEFAULT_OUTPUT, result)
    print(json.dumps(result["test_summary"], ensure_ascii=False, sort_keys=True))
    print(f"phase5_result={DEFAULT_OUTPUT}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
