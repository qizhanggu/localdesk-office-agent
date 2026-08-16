"""以构造资料跑通一次真实 DOCX 渲染与确认交付，保存可复查证据。"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from localdesk.desktop.docx_delivery import DocxDeliveryError, LibreOfficeDocxRenderer
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.reporting import KnowledgeReportWorkflow
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.skills.document import DocumentSkill
from localdesk.desktop.skills.knowledge import KnowledgeSkill
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig

from run_baseline import write_json


DEFAULT_OUTPUT = REPOSITORY_ROOT / "evaluation" / "results" / "phase3_real_render_demo.json"


def run_demo() -> dict:
    with tempfile.TemporaryDirectory(prefix="localdesk-phase3-real-") as temporary:
        root = Path(temporary)
        sources, output, tasks = root / "sources", root / "output", root / "tasks"
        for directory in (sources, output, tasks):
            directory.mkdir()
        (sources / "constructed_evidence.md").write_text(
            "Project Orion milestone is Friday. Python Agent workflow is required.\n",
            encoding="utf-8",
        )
        workspace = DesktopWorkspace(WorkspaceConfig(read_roots=[sources], output_root=output, task_root=tasks))
        service = DesktopTaskService(DesktopPolicyGuard(workspace), TaskTraceStore(workspace))
        workflow = KnowledgeReportWorkflow(service, KnowledgeSkill(workspace), DocumentSkill(workspace))
        task = service.create_task("Project Orion Python Agent milestone")
        workflow.prepare(
            task,
            "orion.md",
            title="Orion Brief",
            docx_filename="orion.docx",
            docx_renderer=LibreOfficeDocxRenderer(timeout_seconds=90),
        )
        workflow.confirm_and_deliver(task, approved=True)
        events = service.trace_store.load_events(task.task_id)
        docx_action = next(action for action in task.actions if action.action_id == "deliver-docx")
        render = docx_action.preview["render"]
        return {
            "status": task.status.value,
            "artifacts": [artifact.kind for artifact in task.artifacts],
            "trace_event_types": [event["event_type"] for event in events],
            "structure": docx_action.preview["structure"],
            "render": {
                "page_count": render["page_count"],
                "png_count": len(render["image_paths"]),
                "pdf_created": bool(render["pdf_path"]),
            },
        }


def main() -> int:
    payload = {
        "schema_version": 1,
        "phase": "phase3",
        "scope": "constructed-data real DOCX render and confirmed delivery",
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    try:
        payload["result"] = run_demo()
        payload["success"] = True
    except DocxDeliveryError as exc:
        payload["success"] = False
        payload["error"] = str(exc)
    write_json(DEFAULT_OUTPUT, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    print(f"phase3_real_render_result={DEFAULT_OUTPUT}")
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
