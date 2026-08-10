"""A deliberately thin task router for LocalDesk Office workflows.

This is not an open-ended agent loop. It converts a natural-language request
into one supported intent, a short inspectable plan, and one existing workflow.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Callable, Generic, TypeVar


class OfficeIntent(str, Enum):
    WEEKLY_BRIEFING = "weekly_briefing"
    REIMBURSEMENT = "reimbursement"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class MainAgentPlan:
    user_query: str
    intent: OfficeIntent
    workflow: str | None
    steps: list[str]
    reason: str
    planner: str = "deterministic_thin_router_v1"

    @property
    def executable(self) -> bool:
        return self.workflow is not None and self.intent is not OfficeIntent.UNSUPPORTED

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["intent"] = self.intent.value
        payload["executable"] = self.executable
        return payload


class ThinMainAgent:
    """Recognize only the two product workflows that LocalDesk can verify."""

    _REIMBURSEMENT_TERMS = (
        "报销", "发票", "支付流水", "reimbursement", "invoice", "expense",
    )
    _WEEKLY_TERMS = (
        "ai 资讯", "ai资讯", "资讯周报", "周报", "ppt", "briefing", "weekly",
    )

    def plan(self, user_query: str) -> MainAgentPlan:
        query = user_query.strip()
        if not query:
            raise ValueError("用户任务不能为空。")
        normalized = query.casefold()
        reimbursement_hits = [term for term in self._REIMBURSEMENT_TERMS if term in normalized]
        weekly_hits = [term for term in self._WEEKLY_TERMS if term in normalized]

        if reimbursement_hits and not weekly_hits:
            return MainAgentPlan(
                user_query=query,
                intent=OfficeIntent.REIMBURSEMENT,
                workflow="reimbursement",
                steps=[
                    "检查支付流水、发票和规则文档是否齐全",
                    "读取规则并核对支付记录与发票",
                    "生成异常清单、PDF 摘要和未发送邮件草稿",
                    "等待人工确认后正式交付",
                ],
                reason=f"识别到报销相关词：{', '.join(reimbursement_hits)}",
            )
        if weekly_hits and not reimbursement_hits:
            return MainAgentPlan(
                user_query=query,
                intent=OfficeIntent.WEEKLY_BRIEFING,
                workflow="weekly_briefing",
                steps=[
                    "确定周报时间窗和三个研究方向",
                    "从冻结的官方来源发现候选资讯并尝试读取原文",
                    "绑定原文证据并完成编辑选择",
                    "生成并检查 PPTX、PDF 和未发送邮件草稿",
                    "等待人工确认后正式交付",
                ],
                reason=f"识别到周报相关词：{', '.join(weekly_hits)}",
            )
        if reimbursement_hits and weekly_hits:
            reason = "任务同时包含周报和报销意图；第一版 Main Agent 不猜测优先级。"
        else:
            reason = "当前只支持 AI 资讯周报和报销核对两类办公任务。"
        return MainAgentPlan(
            user_query=query,
            intent=OfficeIntent.UNSUPPORTED,
            workflow=None,
            steps=["请用户把任务明确为 AI 资讯周报或报销核对"],
            reason=reason,
        )


ResultT = TypeVar("ResultT")


class MainAgentExecutor(Generic[ResultT]):
    def __init__(self, handlers: dict[str, Callable[[MainAgentPlan], ResultT]]) -> None:
        self.handlers = dict(handlers)

    def execute(self, plan: MainAgentPlan) -> ResultT:
        if not plan.executable or plan.workflow is None:
            raise ValueError(plan.reason)
        handler = self.handlers.get(plan.workflow)
        if handler is None:
            raise ValueError(f"Workflow 尚未接入执行器：{plan.workflow}")
        return handler(plan)
