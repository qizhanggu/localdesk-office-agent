"""岗位 JD + 本地履历证据的确定性求职材料纵向工作流。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from localdesk.desktop.browser import BrowserAdapter, WebChunk
from localdesk.desktop.docx_delivery import DocxRenderer, DocumentDeliverySkill
from localdesk.desktop.models import ActionKind, PlannedAction, Task, TaskStatus
from localdesk.desktop.registry import DesktopToolRegistry, create_desktop_registry
from localdesk.desktop.reporting import KnowledgeReportWorkflow
from localdesk.desktop.reviewer import DeterministicReviewer
from localdesk.desktop.service import DesktopTaskService, TaskStateError
from localdesk.desktop.skills.document import DocumentSkill, StagedDraft
from localdesk.desktop.skills.knowledge import KnowledgeSkill, SourceChunk


@dataclass(frozen=True)
class JobMaterialRequest:
    company: str
    role: str
    jd_url: str
    markdown_filename: str
    docx_filename: str | None = None
    feedback: str = ""


class JobMaterialsWorkflow:
    """把公开 JD、本地材料、DOCX 质检、低风险交付与 Trace 串成一条链。"""

    def __init__(
        self,
        service: DesktopTaskService,
        knowledge: KnowledgeSkill,
        document: DocumentSkill,
        registry: DesktopToolRegistry | None = None,
    ) -> None:
        self.service = service
        self.knowledge = knowledge
        self.document = document
        self.registry = registry or create_desktop_registry(service)
        self.docx = DocumentDeliverySkill(knowledge.workspace)
        self.delivery = KnowledgeReportWorkflow(service, knowledge, document, self.registry)

    def prepare(
        self,
        task: Task,
        request: JobMaterialRequest,
        browser: BrowserAdapter,
        docx_renderer: DocxRenderer | None = None,
        auto_deliver: bool = True,
    ) -> StagedDraft:
        if task.status != TaskStatus.DRAFT:
            raise TaskStateError("只有 draft 任务可以准备求职材料")
        if not request.company.strip() or not request.role.strip():
            raise ValueError("公司和岗位不能为空")

        search_action = PlannedAction(
            "job-local-search",
            "knowledge.search",
            ActionKind.READ,
            {"path": str(self.knowledge.workspace.read_roots[0]), "query": task.user_query},
            "检索本地简历与项目材料中的可引用证据",
        )
        indexed, local_chunks = self.registry.execute(
            task,
            search_action,
            lambda: (self.knowledge.index(), self.knowledge.search(task.user_query, limit=8)),
            verify=lambda result: isinstance(result[0], int) and isinstance(result[1], list),
        )
        web_action = PlannedAction(
            "job-jd-open",
            "browser.open",
            ActionKind.NAVIGATE,
            {"url": request.jd_url},
            "读取用户指定且已授权域名内的公开岗位 JD",
        )
        jd = self.registry.execute(
            task,
            web_action,
            lambda: browser.open(request.jd_url),
            verify=lambda result: self.knowledge.workspace.can_browse(result.url) and bool(result.text and result.content_hash),
        )
        self.service.trace_store.append(task.task_id, "web_evidence_captured", {
            "url": jd.url,
            "accessed_at": jd.accessed_at,
            "content_hash": jd.content_hash,
            "citation_excerpt": jd.excerpt(),
            "discovered_links": list(jd.discovered_links),
        })

        evidence: list[SourceChunk | WebChunk] = [*local_chunks, jd]
        content = _render_job_materials(request, local_chunks, jd)
        staged_path, _ = self.document.draft_paths(task.task_id, request.markdown_filename)
        stage_action = PlannedAction(
            "stage-job-materials",
            "document.stage_markdown",
            ActionKind.WRITE,
            {"destination": str(staged_path)},
            "将定向求职材料写入任务 staging",
        )
        draft = self.registry.execute(
            task,
            stage_action,
            lambda: self.document.stage_custom_markdown(
                task.task_id,
                content,
                [item.citation() for item in evidence],
                request.markdown_filename,
                f"基于 {len(local_chunks)} 个本地证据片段与 1 份公开 JD 生成定向求职材料",
            ),
            verify=lambda result: Path(result.staged_path).exists() and bool(result.sha256),
        )
        review = DeterministicReviewer().review_markdown(draft.staged_path, evidence)
        self.service.trace_store.append(task.task_id, "review_completed", {
            "reviewer": "deterministic",
            "approved": review.approved,
            "findings": review.findings,
            "warnings": review.warnings,
            "blockers": review.blockers,
        })
        if not review.approved:
            self.service.fail(task, "; ".join(review.blockers), event_type="review_rejected")
            raise TaskStateError("求职材料触发 Reviewer 阻断项")

        actions = [PlannedAction(
            "deliver-markdown",
            "document.commit_markdown",
            ActionKind.WRITE,
            {"destination": draft.final_path, "auto_deliver": auto_deliver},
            "按风险分级交付新建 Markdown，不覆盖已有文件",
            preview={"staged_path": draft.staged_path, "sha256": draft.sha256, "citations": draft.source_citations, "indexed_chunks": indexed},
        )]
        if request.docx_filename:
            if docx_renderer is None:
                self.service.fail(task, "DOCX 求职材料需要可用的渲染检查器", event_type="docx_render_unavailable")
                raise TaskStateError("DOCX 求职材料需要可用的渲染检查器")
            staged_docx_path = self.knowledge.workspace.task_dir(task.task_id) / "staging" / request.docx_filename
            stage_docx_action = PlannedAction(
                "stage-job-docx",
                "document.stage_docx",
                ActionKind.WRITE,
                {"destination": str(staged_docx_path), "source_markdown": draft.staged_path},
                "生成 DOCX 并执行结构与实际渲染检查",
            )
            try:
                docx_draft = self.registry.execute(
                    task,
                    stage_docx_action,
                    lambda: self.docx.stage_docx(task.task_id, draft.staged_path, request.docx_filename or "job-materials.docx", docx_renderer),
                    verify=lambda result: result.structure.approved and result.render.approved and Path(result.staged_path).exists(),
                )
            except Exception as exc:
                self.service.fail(task, str(exc), event_type="docx_staging_failed")
                raise
            self.service.trace_store.append(task.task_id, "docx_structure_verified", docx_draft.structure.__dict__)
            self.service.trace_store.append(task.task_id, "docx_render_verified", docx_draft.render.__dict__)
            actions.append(PlannedAction(
                "deliver-docx",
                "document.commit_docx",
                ActionKind.WRITE,
                {"destination": docx_draft.final_path, "auto_deliver": auto_deliver},
                "按风险分级交付已检查的新建 DOCX，不覆盖已有文件",
                preview={
                    "staged_path": docx_draft.staged_path,
                    "sha256": docx_draft.sha256,
                    "artifact_kind": "docx",
                    "source_markdown": docx_draft.source_markdown,
                    "structure": docx_draft.structure.__dict__,
                    "render": docx_draft.render.__dict__,
                },
            ))

        self.service.set_plan(task, "读取公开 JD 与本地履历证据，生成定向求职材料；DOCX 通过结构和渲染检查后，按风险分级交付新文件。", actions)
        self.service.trace_store.append(task.task_id, "job_materials_grounded", {
            "company": request.company,
            "role": request.role,
            "local_evidence_count": len(local_chunks),
            "jd_url": jd.url,
            "feedback_applied": bool(request.feedback.strip()),
        })
        self.service.trace_store.append(task.task_id, "draft_staged", asdict(draft))
        if auto_deliver:
            self.service.start_low_risk(task, "仅在 output_root 新建本地求职材料；不覆盖、不发送、不提交")
            self.delivery.confirm_and_deliver(task, approved=True)
        return draft


_SKILLS = ("Python", "Agent", "RAG", "LLM", "FastAPI", "Docker", "SQL", "Java", "LangChain", "MCP")


def _render_job_materials(request: JobMaterialRequest, local_chunks: list[SourceChunk], jd: WebChunk) -> str:
    local_text = " ".join(chunk.text for chunk in local_chunks).lower()
    jd_text = jd.text.lower()
    mentioned = [skill for skill in _SKILLS if skill.lower() in jd_text]
    matched = [skill for skill in mentioned if skill.lower() in local_text]
    gaps = [skill for skill in mentioned if skill.lower() not in local_text]
    lines = [
        f"# {request.company} · {request.role} 定向求职材料",
        "",
        "> 本文由公开岗位 JD 与用户授权的本地履历证据生成；只输出本地草稿，不代表已投递。",
        "",
        "## 岗位要求摘录",
        "",
        jd.excerpt(600),
        "",
        f"来源：`{jd.citation()}`",
        "",
        "## 候选人证据",
        "",
    ]
    if local_chunks:
        for chunk in local_chunks:
            excerpt = " ".join(chunk.text.split())[:360]
            lines.extend([f"- {excerpt}", f"  - 来源：`{chunk.citation()}`"])
    else:
        lines.append("- 当前检索词没有命中本地材料；需要补充或改写检索词后再形成事实性表述。")
    lines.extend([
        "",
        "## 匹配与差距",
        "",
        f"- JD 中识别到的技术关键词：{', '.join(mentioned) if mentioned else '未从预设关键词表中识别到'}",
        f"- 本地材料可直接支撑：{', '.join(matched) if matched else '暂无直接命中'}",
        f"- 建议人工核验或补充：{', '.join(gaps) if gaps else '暂无关键词差距'}",
        "",
        "## 面试表达建议",
        "",
        "- 先讲清任务闭环：输入是什么、Agent 调用了哪些工具、产物如何验证。",
        "- 再讲工程取舍：为什么采用受控读写、风险分级和 Trace，而没有堆叠复杂框架。",
        "- 只陈述上述本地证据能支持的经历；没有证据的技能列为待补充，不编造项目事实。",
        "",
    ])
    if request.feedback.strip():
        lines.extend(["## 用户反馈修订", "", request.feedback.strip(), ""])
    lines.extend([
        "## 下一步人工检查",
        "",
        "- 核对公司名、岗位名、量化指标和时间范围。",
        "- 按真实经历把匹配证据改写成简历 bullet；对外发送前必须再次人工确认。",
        "",
        "## Sources",
        "",
    ])
    lines.extend(f"- `{chunk.citation()}`" for chunk in local_chunks)
    lines.append(f"- `{jd.citation()}`")
    return "\n".join(lines) + "\n"
