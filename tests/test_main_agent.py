from pathlib import Path

import pytest

from localdesk.desktop.main_agent import MainAgentExecutor, OfficeIntent, ThinMainAgent
from localdesk.desktop.main_agent_demo import run


def test_routes_weekly_briefing_with_short_plan() -> None:
    plan = ThinMainAgent().plan("帮我整理本周 AI 资讯并生成 PPT")
    assert plan.intent is OfficeIntent.WEEKLY_BRIEFING
    assert plan.workflow == "weekly_briefing"
    assert 3 <= len(plan.steps) <= 6


def test_routes_reimbursement_with_short_plan() -> None:
    plan = ThinMainAgent().plan("帮我核对这些报销发票和支付流水")
    assert plan.intent is OfficeIntent.REIMBURSEMENT
    assert plan.workflow == "reimbursement"
    assert 3 <= len(plan.steps) <= 6


def test_ambiguous_or_unknown_request_fails_honestly() -> None:
    agent = ThinMainAgent()
    ambiguous = agent.plan("把报销做成周报 PPT")
    unknown = agent.plan("帮我整理桌面所有文件")
    assert not ambiguous.executable and ambiguous.intent is OfficeIntent.UNSUPPORTED
    assert not unknown.executable and "只支持" in unknown.reason


def test_executor_only_calls_selected_workflow() -> None:
    called: list[str] = []
    plan = ThinMainAgent().plan("核对报销材料")
    executor = MainAgentExecutor({"reimbursement": lambda _plan: called.append("reimbursement") or "ok"})
    assert executor.execute(plan) == "ok"
    assert called == ["reimbursement"]


def test_plan_only_entry_does_not_generate_artifacts(tmp_path: Path) -> None:
    result = run("生成本周 AI 资讯 PPT", tmp_path, plan_only=True)
    assert result["executed"] is False
    assert result["plan"]["workflow"] == "weekly_briefing"
    assert list(tmp_path.iterdir()) == []


def test_empty_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="不能为空"):
        ThinMainAgent().plan("  ")
