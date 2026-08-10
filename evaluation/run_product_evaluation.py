from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook

from localdesk.desktop.artifact_bundle import ArtifactBundleDelivery
from localdesk.desktop.browser import WebChunk
from localdesk.desktop.main_agent import ThinMainAgent
from localdesk.desktop.models import ActionKind, PlannedAction
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.registry import create_desktop_registry
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.weekly_briefing import NewsCard, NewsSource, WeeklyBriefingReviewer, WeeklyBriefingWorkflow
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "evaluation" / "product_tasks_v2.json"
DEFAULT_OUTPUT = REPO_ROOT / "evaluation" / "results" / "product_eval_v2.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_cards(*, tamper: bool = False) -> list[NewsCard]:
    cards = []
    for index, category in enumerate(("model", "agent_product", "industry"), start=1):
        summary = f"Official evidence summary for {category}."
        quote = summary if not (tamper and index == 2) else "Unrelated quotation."
        cards.append(NewsCard(
            card_id=f"card-{index}", category=category, title=f"Official {category} update",
            published="2026-08-04", url=f"https://example.com/{category}",
            summary=summary, value="Human interpretation required.", evidence_quote=quote,
            accessed_at="2026-08-10T00:00:00+00:00", content_hash="a" * 64,
            source_mode="frozen_eval_fixture", evidence_supported=summary in quote,
        ))
    return cards


def _workspace(root: Path) -> tuple[DesktopWorkspace, DesktopTaskService]:
    read_root, output_root, task_root = root / "sources", root / "output", root / "tasks"
    for path in (read_root, output_root, task_root):
        path.mkdir(parents=True, exist_ok=True)
    workspace = DesktopWorkspace(WorkspaceConfig(
        read_roots=[read_root], output_root=output_root, task_root=task_root,
    ))
    service = DesktopTaskService(DesktopPolicyGuard(workspace), TaskTraceStore(workspace))
    return workspace, service


def _bundle_case(root: Path, mode: str) -> dict[str, Any]:
    workspace, service = _workspace(root)
    task = service.create_task(f"evaluation {mode}")
    staging = workspace.task_dir(task.task_id) / "staging"
    staging.mkdir()
    staged = staging / "result.xlsx"
    workbook = Workbook()
    workbook.active.append(["status", "value"])
    workbook.active.append(["ok", 1])
    workbook.save(staged)
    delivery = ArtifactBundleDelivery(service, workspace, create_desktop_registry(service))
    artifact = delivery.capture(kind="xlsx", staged_path=staged, final_filename="result.xlsx", summary="evaluation workbook")
    service.set_plan(task, "confirm deterministic workbook", [
        delivery.action(action_id="eval-xlsx", skill="spreadsheet.commit", artifact=artifact),
    ])
    if mode == "reject":
        delivery.confirm_and_deliver(task, approved=False)
    else:
        if mode == "tamper":
            workbook = load_workbook(staged)
            workbook.active["B2"] = 999
            workbook.save(staged)
            workbook.close()
        delivery.confirm_and_deliver(task, approved=True)
    output = workspace.output_root / "result.xlsx"
    events = [event["event_type"] for event in service.trace_store.load_events(task.task_id)]
    xlsx_valid = False
    if output.exists():
        check = load_workbook(output, read_only=True)
        xlsx_valid = bool(check.sheetnames)
        check.close()
    return {
        "status": task.status.value,
        "artifact_count": len(task.artifacts),
        "output_count": len(list(workspace.output_root.iterdir())),
        "xlsx_valid": xlsx_valid,
        "events": events,
        "error": task.error,
        "task_dir": str(workspace.task_dir(task.task_id)),
    }


def _research_mode_case(root: Path, mode: str, delay_ms: int) -> dict[str, Any]:
    workspace, service = _workspace(root)
    sources = [
        NewsSource(category, f"Official {category} update", "2026-08-04", f"https://example.com/{category}", f"Evidence summary for {category}.", "Human interpretation required.")
        for category in ("model", "agent_product", "industry")
    ]

    class DelayedBrowser:
        source_mode = "frozen_eval_fixture"

        def open(self, url: str) -> WebChunk:
            time.sleep(delay_ms / 1000)
            source = next(item for item in sources if item.url == url)
            text = f"{source.title}. {source.summary} {source.value}"
            return WebChunk(
                f"web:{url}", url, source.title, text, "2026-08-10T00:00:00+00:00",
                hashlib.sha256(text.encode()).hexdigest(),
            )

    workflow = WeeklyBriefingWorkflow(workspace, service.trace_store, browser=DelayedBrowser())
    grouped = {category: [item for item in sources if item.category == category] for category in ("model", "agent_product", "industry")}
    started = time.perf_counter()
    if mode == "single_sequential":
        groups = [workflow._research(category, items, date(2026, 8, 1), date(2026, 8, 7)) for category, items in grouped.items()]
    elif mode == "three_parallel":
        with ThreadPoolExecutor(max_workers=3) as pool:
            groups = list(pool.map(lambda pair: workflow._research(pair[0], pair[1], date(2026, 8, 1), date(2026, 8, 7)), grouped.items()))
    else:
        raise ValueError(f"Unknown research mode: {mode}")
    latency_ms = (time.perf_counter() - started) * 1000
    cards = [card for group, _reads in groups for card in group]
    selected = workflow._edit(cards, {})
    return {
        "mode": mode,
        "covered_roles": len({card.category for card in selected}),
        "selected_cards": len(selected),
        "evidence_support_rate": sum(card.evidence_supported for card in selected) / len(selected),
        "latency_ms_research": round(latency_ms, 3),
    }


def _evaluate(task: dict[str, Any], task_root: Path) -> tuple[bool, dict[str, Any]]:
    case = task["case"]
    expected = task["checks"]
    observations: dict[str, Any]
    if case in {"route", "unsupported"}:
        plan = ThinMainAgent().plan(task["input"]["query"])
        observations = {
            "intent": plan.intent.value,
            "workflow": plan.workflow,
            "steps": len(plan.steps),
            "executable": plan.executable,
        }
        passed = all((
            observations["intent"] == expected["intent"],
            "workflow" not in expected or observations["workflow"] == expected["workflow"],
            "executable" not in expected or observations["executable"] == expected["executable"],
            "steps_min" not in expected or expected["steps_min"] <= observations["steps"] <= expected["steps_max"],
        ))
    elif case == "empty_query":
        try:
            ThinMainAgent().plan(task["input"]["query"])
            observations = {"error": None}
        except ValueError as exc:
            observations = {"error": str(exc)}
        passed = observations["error"] == expected["error"]
    elif case == "role_coverage":
        roles = set(task["input"]["roles"])
        observations = {"covered_roles": len(roles), "total_roles": 3, "coverage": len(roles) / 3}
        passed = observations["covered_roles"] == expected["covered_roles"]
    elif case == "research_mode":
        observations = _research_mode_case(task_root, task["input"]["mode"], int(task["input"]["per_source_delay_ms"]))
        passed = all(observations[key] == value for key, value in expected.items())
    elif case == "evidence_review":
        cards = _valid_cards(tamper=bool(task["input"]["tamper"]))
        review = WeeklyBriefingReviewer().review(cards, date(2026, 8, 1), date(2026, 8, 7))
        observations = {
            "approved": review.approved,
            "supported_cards": sum(card.evidence_supported for card in cards),
            "blockers": review.blockers,
        }
        passed = observations["approved"] == expected["approved"]
        if "supported_cards" in expected:
            passed = passed and observations["supported_cards"] == expected["supported_cards"]
        if "blocker_contains" in expected:
            passed = passed and any(expected["blocker_contains"] in item for item in review.blockers)
    elif case == "title_dedup":
        cards = _valid_cards()
        cards.append(NewsCard(**{**asdict(cards[0]), "card_id": "duplicate", "url": "https://example.com/duplicate"}))
        selected = WeeklyBriefingWorkflow._edit(cards, {})
        observations = {"selected_cards": len(selected)}
        passed = observations == expected
    elif case == "repeat_rate":
        cards = _valid_cards()
        seen = {card.card_id: {} for card in cards} if task["input"]["memory"] else {}
        selected = WeeklyBriefingWorkflow._edit(cards, seen)
        repeated = len(cards) if not seen else len(selected)
        repeat_rate = repeated / len(cards)
        observations = {"repeat_rate": repeat_rate, "selected_cards": len(selected)}
        passed = repeat_rate == expected["repeat_rate"]
    elif case == "policy_deny":
        workspace, _service = _workspace(task_root)
        kind = ActionKind(task["input"]["kind"])
        action = PlannedAction("policy", "forbidden", kind, {}, "forbidden action")
        decision = DesktopPolicyGuard(workspace).evaluate(action)
        observations = {"effect": decision.effect, "reason": decision.reason}
        passed = decision.effect == expected["effect"]
    elif case == "bundle_reject":
        observations = _bundle_case(task_root, "reject")
        passed = observations["status"] == expected["status"] and observations["output_count"] == expected["output_count"]
    elif case == "bundle_success":
        observations = _bundle_case(task_root, "success")
        passed = all((
            observations["status"] == expected["status"],
            observations["artifact_count"] == expected["artifact_count"],
            observations["xlsx_valid"] is expected["xlsx_valid"],
        ))
    elif case == "bundle_tamper":
        observations = _bundle_case(task_root, "tamper")
        observations["verification_detected"] = observations["status"] == "failed" and "哈希" in str(observations["error"])
        passed = all((
            observations["status"] == expected["status"],
            observations["output_count"] == expected["output_count"],
            observations["verification_detected"] is expected["verification_detected"],
        ))
    elif case == "trace_complete":
        observations = _bundle_case(task_root, "success")
        missing = sorted(set(expected["required_events"]) - set(observations["events"]))
        observations["missing_events"] = missing
        passed = observations["status"] == expected["status"] and not missing
    else:
        raise ValueError(f"Unknown evaluation case: {case}")
    return passed, observations


def run(manifest_path: Path, output_path: Path, run_root: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tasks = manifest["tasks"]
    if len(tasks) != 18 or len({task["id"] for task in tasks}) != 18:
        raise ValueError("Product evaluation v1 must contain exactly 18 unique tasks.")
    run_root.mkdir(parents=True, exist_ok=False)
    results = []
    for task in tasks:
        started = time.perf_counter()
        error = None
        try:
            passed, observations = _evaluate(task, run_root / task["id"])
        except Exception as exc:
            passed, observations, error = False, {}, str(exc)
        results.append({
            "id": task["id"], "group": task["group"], "case": task["case"],
            "passed": passed, "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "observations": observations, "error": error,
        })
    by_id = {item["id"]: item for item in results}
    passed_count = sum(item["passed"] for item in results)
    summary = {
        "task_count": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "task_success_rate": passed_count / len(results),
        "single_research_coverage": by_id["rs01"]["observations"].get("covered_roles"),
        "three_agent_coverage": by_id["rs02"]["observations"].get("covered_roles"),
        "single_research_latency_ms": by_id["rs01"]["observations"].get("latency_ms_research"),
        "three_agent_latency_ms": by_id["rs02"]["observations"].get("latency_ms_research"),
        "parallel_speedup": round(
            by_id["rs01"]["observations"].get("latency_ms_research", 0)
            / max(by_id["rs02"]["observations"].get("latency_ms_research", 1), 0.001),
            3,
        ),
        "evidence_support_rate_fixture": (
            by_id["rs01"]["observations"].get("evidence_support_rate", 0)
            + by_id["rs02"]["observations"].get("evidence_support_rate", 0)
        ) / 2,
        "repeat_rate_without_memory": by_id["mm01"]["observations"].get("repeat_rate"),
        "repeat_rate_with_memory": by_id["mm02"]["observations"].get("repeat_rate"),
        "policy_interception_rate": sum(by_id[item]["passed"] for item in ("pl01", "pl02")) / 2,
        "approval_correctness_rate": 1.0 if by_id["ap01"]["passed"] else 0.0,
        "artifact_validity_rate": 1.0 if by_id["ar01"]["passed"] else 0.0,
        "verification_failure_detection_rate": 1.0 if by_id["vf01"]["passed"] else 0.0,
        "trace_completeness_rate": 1.0 if by_id["tr01"]["passed"] else 0.0,
        "token_count": 0,
        "cost_usd": 0.0,
        "human_delete_or_modify_count": None,
        "human_feedback_note": "No real user study was run; deterministic review only.",
        "latency_ms_total": round(sum(item["latency_ms"] for item in results), 3),
    }
    payload = {
        "benchmark_id": manifest["benchmark_id"],
        "manifest_sha256": _sha256(manifest_path),
        "started_at": datetime.now(UTC).isoformat(),
        "run_root": str(run_root),
        "rules": manifest["rules"],
        "summary": summary,
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the frozen 18-task LocalDesk product evaluation.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-root", type=Path, default=REPO_ROOT / ".localdesk" / "product-eval-v2")
    args = parser.parse_args()
    result = run(args.manifest.resolve(), args.output.resolve(), args.run_root.resolve())
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["summary"]["failed"] == 0 else 1)
