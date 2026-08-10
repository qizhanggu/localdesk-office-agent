"""Natural-language entry point for the two verified LocalDesk demos."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from localdesk.desktop.main_agent import MainAgentExecutor, MainAgentPlan, ThinMainAgent
from localdesk.desktop.reimbursement_demo import run_demo as run_reimbursement_demo
from localdesk.desktop.weekly_briefing_live_demo import run_live_demo as run_weekly_demo


def run(user_query: str, root: Path, *, plan_only: bool = False) -> dict[str, object]:
    plan = ThinMainAgent().plan(user_query)
    if plan_only or not plan.executable:
        return {"plan": plan.to_dict(), "executed": False}

    executor: MainAgentExecutor[dict[str, object]] = MainAgentExecutor({
        "weekly_briefing": lambda selected: run_weekly_demo(
            root / "weekly", main_agent_plan=selected.to_dict(), user_query=user_query,
        ),
        "reimbursement": lambda selected: run_reimbursement_demo(
            root / "reimbursement", main_agent_plan=selected.to_dict(), user_query=user_query,
        ),
    })
    result = executor.execute(plan)
    return {"plan": plan.to_dict(), "executed": True, "result": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the thin LocalDesk Main Agent.")
    parser.add_argument("--task", required=True, help="Natural-language office task")
    parser.add_argument("--root", type=Path, default=Path.cwd() / ".localdesk" / "main-agent-demo")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.task, args.root.resolve(), plan_only=args.plan_only), ensure_ascii=False, indent=2))
