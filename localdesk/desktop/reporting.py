from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from localdesk.desktop.models import ActionKind, Artifact, PlannedAction, Task, TaskStatus
from localdesk.desktop.docx_delivery import DocxRenderer, DocumentDeliverySkill, StagedDocx
from localdesk.desktop.grounded_renderer import GroundedLLMRenderer, GroundedRenderError
from localdesk.desktop.registry import DesktopToolRegistry, create_desktop_registry
from localdesk.desktop.reviewer import DeterministicReviewer
from localdesk.desktop.service import DesktopTaskService, TaskStateError
from localdesk.desktop.skills.document import DocumentSkill, StagedDraft
from localdesk.desktop.skills.knowledge import KnowledgeSkill

if TYPE_CHECKING:
    from localdesk.desktop.browser import BrowserAdapter, WebChunk


class KnowledgeReportWorkflow:
    """将资料检索和 Markdown staging 串入同一条受控任务链。"""

    def __init__(self, service: DesktopTaskService, knowledge: KnowledgeSkill, document: DocumentSkill, registry: DesktopToolRegistry | None = None) -> None:
        self.service = service
        self.knowledge = knowledge
        self.document = document
        self.docx = DocumentDeliverySkill(knowledge.workspace)
        self.registry = registry or create_desktop_registry(service)

    def prepare(
        self,
        task: Task,
        filename: str,
        title: str | None = None,
        browser: "BrowserAdapter | None" = None,
        web_urls: list[str] | None = None,
        docx_filename: str | None = None,
        docx_renderer: DocxRenderer | None = None,
        auto_deliver: bool = False,
    ) -> StagedDraft:
        if task.status != TaskStatus.DRAFT:
            raise TaskStateError("只有 draft 任务可以准备报告")
        search_action = PlannedAction(
            action_id="knowledge-search",
            skill="knowledge.search",
            kind=ActionKind.READ,
            args={"path": str(self.knowledge.workspace.read_roots[0]), "query": task.user_query},
            summary="检索授权的本地资料并返回可定位引用",
        )
        indexed, chunks = self.registry.execute(
            task,
            search_action,
            lambda: (self.knowledge.index(), self.knowledge.search(task.user_query)),
            verify=lambda result: isinstance(result[0], int) and isinstance(result[1], list),
        )
        evidence: list[object] = list(chunks)
        for position, url in enumerate(web_urls or [], start=1):
            if browser is None:
                raise TaskStateError("网页研究需要 Browser adapter")
            web_action = PlannedAction(
                action_id=f"browser-open-{position}",
                skill="browser.open",
                kind=ActionKind.NAVIGATE,
                args={"url": url},
                summary="读取授权域名内的公开网页并保留引用",
            )
            web_chunk = self.registry.execute(
                task,
                web_action,
                lambda url=url: browser.open(url),
                verify=lambda result: self.knowledge.workspace.can_browse(result.url) and bool(result.text and result.accessed_at),
            )
            evidence.append(web_chunk)
            self.service.trace_store.append(task.task_id, "web_evidence_captured", {
                "url": web_chunk.url,
                "accessed_at": web_chunk.accessed_at,
                "content_hash": web_chunk.content_hash,
                "citation_excerpt": web_chunk.excerpt(),
                "discovered_links": list(web_chunk.discovered_links),
            })
        staged_path, _ = self.document.draft_paths(task.task_id, filename)
        stage_action = PlannedAction(
            action_id="stage-markdown",
            skill="document.stage_markdown",
            kind=ActionKind.WRITE,
            args={"destination": str(staged_path)},
            summary="将带引用的 Markdown 草稿写入任务 staging",
        )
        draft = self.registry.execute(
            task,
            stage_action,
            lambda: self.document.stage_markdown(task.task_id, title or "LocalDesk 资料报告草稿", task.user_query, evidence, filename),
            verify=lambda result: Path(result.staged_path).exists() and result.sha256 != "",
        )
        review = DeterministicReviewer().review_markdown(draft.staged_path, evidence)
        self.service.trace_store.append(task.task_id, "review_completed", {"reviewer": "deterministic", "approved": review.approved, "findings": review.findings, "warnings": review.warnings, "blockers": review.blockers})
        if not review.approved:
            self.service.fail(task, "; ".join(review.findings), event_type="review_rejected")
            raise TaskStateError("草稿未通过确定性 Reviewer")
        actions = [PlannedAction(
            action_id="deliver-markdown",
            skill="document.commit_markdown",
            kind=ActionKind.WRITE,
            args={"destination": draft.final_path},
            summary="确认后交付 staging Markdown 草稿到 output 目录",
            preview={
                "staged_path": draft.staged_path,
                "sha256": draft.sha256,
                "citations": draft.source_citations,
                "indexed_chunks": indexed,
            },
        )]
        actions[0].args["auto_deliver"] = auto_deliver
        if docx_filename:
            if docx_renderer is None:
                self.service.fail(task, "DOCX 交付需要可用的渲染检查器", event_type="docx_render_unavailable")
                raise TaskStateError("DOCX 交付需要可用的渲染检查器")
            docx_staged_path = self.knowledge.workspace.task_dir(task.task_id) / "staging" / docx_filename
            stage_docx_action = PlannedAction(
                action_id="stage-docx",
                skill="document.stage_docx",
                kind=ActionKind.WRITE,
                args={"destination": str(docx_staged_path), "source_markdown": draft.staged_path},
                summary="将经过引用审查的 Markdown 转为 DOCX，并完成结构与渲染检查",
            )
            try:
                docx_draft = self.registry.execute(
                    task,
                    stage_docx_action,
                    lambda: self.docx.stage_docx(task.task_id, draft.staged_path, docx_filename, docx_renderer),
                    verify=lambda result: result.structure.approved and result.render.approved and Path(result.staged_path).exists(),
                )
            except Exception as exc:
                self.service.fail(task, str(exc), event_type="docx_staging_failed")
                raise
            self.service.trace_store.append(task.task_id, "docx_structure_verified", docx_draft.structure.__dict__)
            self.service.trace_store.append(task.task_id, "docx_render_verified", docx_draft.render.__dict__)
            actions.append(PlannedAction(
                action_id="deliver-docx",
                skill="document.commit_docx",
                kind=ActionKind.WRITE,
                args={"destination": docx_draft.final_path, "auto_deliver": auto_deliver},
                summary="确认后将已检查的 staging DOCX 交付到 output 目录",
                preview={
                    "staged_path": docx_draft.staged_path,
                    "sha256": docx_draft.sha256,
                    "artifact_kind": "docx",
                    "source_markdown": docx_draft.source_markdown,
                    "structure": docx_draft.structure.__dict__,
                    "render": docx_draft.render.__dict__,
                },
            ))
        self.service.set_plan(task, "检索授权资料并生成 Markdown 草稿；DOCX 需通过结构与渲染检查；按风险策略交付到 output。", actions)
        self.service.trace_store.append(task.task_id, "knowledge_searched", {"query": task.user_query, "indexed_chunks": indexed, "citations": draft.source_citations})
        self.service.trace_store.append(task.task_id, "draft_staged", asdict(draft))
        if auto_deliver:
            self.service.start_low_risk(task, "新建产物写入专属 output_root，不覆盖、不外发")
            self.confirm_and_deliver(task, approved=True)
        return draft

    async def prepare_grounded(self, task: Task, filename: str, renderer: GroundedLLMRenderer) -> StagedDraft:
        if task.status != TaskStatus.DRAFT:
            raise TaskStateError("只有 draft 任务可以准备报告")
        indexed = self.knowledge.index()
        chunks = self.knowledge.search(task.user_query)
        try:
            rendered = await renderer.render(task.user_query, chunks)
            draft = self.document.stage_grounded_markdown(task.task_id, task.user_query, rendered.report, chunks, filename)
        except (GroundedRenderError, ValueError) as exc:
            self.service.fail(task, str(exc), event_type="llm_render_failed")
            raise
        action = PlannedAction(
            action_id="deliver-markdown",
            skill="document.commit_markdown",
            kind=ActionKind.WRITE,
            args={"destination": draft.final_path},
            summary="确认后交付带可验证引用的 LLM Markdown 草稿到 output 目录",
            preview={"staged_path": draft.staged_path, "sha256": draft.sha256, "citations": draft.source_citations, "indexed_chunks": indexed},
        )
        self.service.set_plan(task, "检索授权资料，由 LLM 基于给定片段生成结构化报告；确认后交付到 output。", [action])
        self.service.trace_store.append(task.task_id, "llm_rendered", {"title": rendered.report.title, "sections": [{"heading": item.heading, "citation_ids": item.citation_ids} for item in rendered.report.sections]})
        self.service.trace_store.append(task.task_id, "knowledge_searched", {"query": task.user_query, "indexed_chunks": indexed, "citations": draft.source_citations})
        self.service.trace_store.append(task.task_id, "draft_staged", asdict(draft))
        return draft

    def confirm_and_deliver(self, task: Task, approved: bool) -> None:
        if task.status == TaskStatus.AWAITING_CONFIRMATION:
            self.service.confirm(task, approved)
            if not approved:
                return
        elif task.status != TaskStatus.EXECUTING:
            raise TaskStateError("任务既不在等待确认，也不在低风险自动执行状态")
        actions = self._delivery_actions(task)
        try:
            deliveries = []
            for action in actions:
                preview = action.preview
                draft = StagedDraft(
                    staged_path=preview["staged_path"],
                    final_path=action.args["destination"],
                    sha256=preview["sha256"],
                    source_citations=preview.get("citations", []),
                    summary="确认后的交付",
                )
                self.document.validate_commit(draft)
                deliveries.append((action, draft))
            self.service.trace_store.append(task.task_id, "delivery_preflight_verified", {"artifact_count": len(deliveries)})
            for action, draft in deliveries:
                preview = action.preview
                self.registry.execute(
                    task,
                    action,
                    lambda draft=draft: self.document.commit(draft),
                    verify=lambda _result, draft=draft: Path(draft.final_path).exists(),
                )
                action.status = "succeeded"
                self.service.add_artifact(task, Artifact(
                    kind=preview.get("artifact_kind", "markdown"),
                    staged_path=draft.staged_path,
                    final_path=draft.final_path,
                    sha256=draft.sha256,
                    summary=draft.summary,
                ))
        except Exception as exc:
            self.service.finish(task, error=str(exc))
            raise
        self.service.finish(task)

    @staticmethod
    def _delivery_actions(task: Task) -> list[PlannedAction]:
        actions = [action for action in task.actions if action.action_id in {"deliver-markdown", "deliver-docx"}]
        if not actions:
            raise TaskStateError("任务中不存在可交付动作")
        return actions
