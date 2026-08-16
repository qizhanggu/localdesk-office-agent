"""冻结 Phase 6A 工程底座：统一运行当前 Desktop Runtime 回归并保存真实摘要。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime

from run_baseline import REPOSITORY_ROOT, load_task_set, parse_pytest_summary, write_json

TASK_SET_PATH = REPOSITORY_ROOT / "evaluation" / "phase6a_tasks.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "evaluation" / "results" / "phase6a_baseline.json"
TEST_TARGETS = (
    "tests/test_desktop_foundation.py",
    "tests/test_desktop_reporting.py",
    "tests/test_grounded_renderer.py",
    "tests/test_file_workflow.py",
    "tests/test_desktop_computer_use.py",
    "tests/test_dashboard.py",
    "tests/test_job_materials.py",
)


def main() -> int:
    tasks = load_task_set(TASK_SET_PATH)
    with tempfile.TemporaryDirectory(prefix="localdesk-phase6a-") as base_temp:
        command = [sys.executable, "-m", "pytest", "-q", *TEST_TARGETS, "-p", "no:cacheprovider", "--basetemp", base_temp]
        completed = subprocess.run(command, cwd=REPOSITORY_ROOT, text=True, capture_output=True, check=False)
    summary = parse_pytest_summary(completed.stdout + completed.stderr)
    measured = summary["passed"] + summary["failed"] + summary["error"]
    result = {
        "schema_version": 1,
        "phase": "phase6a",
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "controlled Desktop Runtime baseline plus risk-tiered delivery, Trace board, and job-materials workflow",
        "command": command,
        "pytest_return_code": completed.returncode,
        "test_summary": {**summary, "executed": sum(summary.values())},
        "evaluation_task_set": {
            "path": str(TASK_SET_PATH.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
            "task_count": len(tasks),
            "by_type": dict(sorted(Counter(str(task["type"]) for task in tasks).items())),
        },
        "measured_metrics": {"desktop_regression_pass_rate": (summary["passed"] / measured) if measured else None},
        "not_measured": [
            "arbitrary_website_search_success_rate",
            "real_job_application_quality",
            "automatic_external_submission",
            "arbitrary_third_party_GUI_success_rate",
        ],
        "notes": [
            "Offline tests use fake browser and DOCX renderer where deterministic isolation is required.",
            "Real public-web Trace and real LibreOffice rendering are recorded by separate acceptance scripts.",
        ],
    }
    write_json(DEFAULT_OUTPUT, result)
    print(json.dumps(result["test_summary"], ensure_ascii=False, sort_keys=True))
    print(f"phase6a_result={DEFAULT_OUTPUT}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
