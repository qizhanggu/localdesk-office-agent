"""生成 Phase 3 DOCX 交付链路的离线回归证据。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from run_baseline import REPOSITORY_ROOT, load_task_set, parse_pytest_summary, write_json


TASK_SET_PATH = REPOSITORY_ROOT / "evaluation" / "phase3_tasks.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "evaluation" / "results" / "phase3_docx_delivery.json"
TEST_TARGETS = ("tests/test_desktop_foundation.py", "tests/test_desktop_reporting.py")


def main() -> int:
    tasks = load_task_set(TASK_SET_PATH)
    with tempfile.TemporaryDirectory(prefix="localdesk-phase3-") as base_temp:
        command = [sys.executable, "-m", "pytest", "-q", *TEST_TARGETS, "-p", "no:cacheprovider", "--basetemp", base_temp]
        completed = subprocess.run(command, cwd=REPOSITORY_ROOT, text=True, capture_output=True, check=False)
    summary = parse_pytest_summary(completed.stdout + completed.stderr)
    executed = sum(summary.values())
    measured = summary["passed"] + summary["failed"] + summary["error"]
    result = {
        "schema_version": 1,
        "phase": "phase3",
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "offline DOCX staging, structural validation, render-gate orchestration, and delivery preflight",
        "command": command,
        "pytest_return_code": completed.returncode,
        "test_summary": {**summary, "executed": executed},
        "evaluation_task_set": {
            "path": str(TASK_SET_PATH.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
            "task_count": len(tasks),
            "by_type": dict(sorted(Counter(str(task.get("type", "unknown")) for task in tasks).items())),
        },
        "measured_metrics": {"phase3_regression_pass_rate": (summary["passed"] / measured) if measured else None},
        "not_measured": ["real_renderer_success_rate", "visual_layout_quality", "document_generation_latency"],
        "notes": [
            "The regression suite uses FakeDocxRenderer to test orchestration and refusal paths.",
            "A real LibreOffice PDF/PNG render is a separate required acceptance gate and is not claimed by this result.",
        ],
    }
    write_json(DEFAULT_OUTPUT, result)
    print(json.dumps(result["test_summary"], ensure_ascii=False, sort_keys=True))
    print(f"phase3_result={DEFAULT_OUTPUT}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
