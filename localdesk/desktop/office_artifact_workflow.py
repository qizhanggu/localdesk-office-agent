"""把 DOCX-PDF 和 .eml 草稿接入 LocalDesk 的 Runtime、Policy 与 Trace。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from localdesk.desktop.docx_delivery import DocxRenderer
from localdesk.desktop.models import ActionKind, Artifact, PlannedAction, Task, TaskStatus
from localdesk.desktop.registry import DesktopToolRegistry, create_desktop_registry
from localdesk.desktop.service import DesktopTaskService, TaskStateError
from localdesk.desktop.skills.office_artifacts import (
    EmailDraftSkill,
    EmailDraftValidation,
    PdfDeliverySkill,
    PdfValidation,
    StagedEmailDraft,
    StagedPdf,
)
from localdesk.desktop.workspace import DesktopWorkspace


class OfficeArtifactWorkflow:
    """每次只准备一种交付物，确保确认的预览与实际写入严格绑定。"""

    def __init__(self, service: DesktopTaskService, workspace: DesktopWorkspace, registry: DesktopToolRegistry | None = None) -> None:
        self.service = service
        self.workspace = workspace
        self.pdf = PdfDeliverySkill(workspace)
        self.email = EmailDraftSkill(workspace)
        self.registry = registry or create_desktop_registry(service)

    def prepare_pdf(self, task: Task, source_docx: str, output_filename: str, renderer: DocxRenderer) -> StagedPdf:
        self._require_draft(task)
        staged_path = self.workspace.task_dir(task.task_id) / "staging" / output_filename
        draft = self.registry.execute(
            task,
            PlannedAction("pdf-stage", "document.stage_pdf", ActionKind.WRITE, {"destination": str(staged_path), "source_docx": source_docx}, "将授权 DOCX 渲染并验证为正式 PDF 草稿"),
            lambda: self.pdf.stage_pdf(task.task_id, source_docx, output_filename, renderer),
            verify=lambda result: result.validation.approved and Path(result.staged_path).is_file(),
        )
        self.service.set_plan(task, "读取授权 DOCX，完成渲染和 PDF 检查；确认后交付新的正式 PDF。", [
            PlannedAction("pdf-commit", "document.commit_pdf", ActionKind.WRITE, {"destination": draft.final_path}, "确认后交付经检查的正式 PDF", preview={"draft": asdict(draft)})
        ])
        self.service.trace_store.append(task.task_id, "pdf_staged", asdict(draft))
        return draft

    def prepare_email(
        self,
        task: Task,
        output_filename: str,
        recipients: Iterable[str],
        subject: str,
        body: str,
        attachments: Iterable[str] = (),
    ) -> StagedEmailDraft:
        self._require_draft(task)
        recipient_values = list(recipients)
        attachment_values = list(attachments)
        staged_path = self.workspace.task_dir(task.task_id) / "staging" / output_filename
        draft = self.registry.execute(
            task,
            PlannedAction("eml-stage", "mail.stage_eml", ActionKind.WRITE, {"destination": str(staged_path), "recipient_count": len(recipient_values)}, "生成仅本地保存、未发送的标准 EML 草稿"),
            lambda: self.email.stage_draft(task.task_id, output_filename, recipient_values, subject, body, attachment_values),
            verify=lambda result: result.validation.approved and Path(result.staged_path).is_file(),
        )
        self.service.set_plan(task, "生成标准 .eml 邮件草稿；它不会发送邮件，确认后只交付本地草稿文件。", [
            PlannedAction("eml-commit", "mail.commit_eml", ActionKind.WRITE, {"destination": draft.final_path, "auto_deliver": True}, "交付仅本地保存的 .eml 草稿", preview={"draft": asdict(draft)})
        ])
        self.service.trace_store.append(task.task_id, "email_draft_staged", asdict(draft))
        self.service.start_low_risk(task, "新建 .eml 草稿只保存到 LocalDesk output，不会发送邮件")
        self._deliver(task)
        return draft

    def confirm_and_deliver(self, task: Task, approved: bool) -> None:
        if task.status != TaskStatus.AWAITING_CONFIRMATION:
            raise TaskStateError("办公产物任务不在等待确认状态")
        self.service.confirm(task, approved)
        if not approved:
            return
        self._deliver(task)

    def _deliver(self, task: Task) -> None:
        action = task.actions[0]
        try:
            if action.skill == "document.commit_pdf":
                draft = _pdf_draft(action.preview["draft"])
                self.pdf.validate_commit(draft)
                self.registry.execute(task, action, lambda: self.pdf.commit(draft), verify=lambda _: Path(draft.final_path).is_file())
                artifact = Artifact("pdf", draft.staged_path, draft.final_path, draft.sha256, draft.summary)
            elif action.skill == "mail.commit_eml":
                draft = _email_draft(action.preview["draft"])
                self.email.validate_commit(draft)
                self.registry.execute(task, action, lambda: self.email.commit(draft), verify=lambda _: Path(draft.final_path).is_file())
                artifact = Artifact("email_draft", draft.staged_path, draft.final_path, draft.sha256, draft.summary)
            else:
                raise TaskStateError(f"未知办公交付动作: {action.skill}")
            action.status = "succeeded"
            self.service.add_artifact(task, artifact)
            self.service.finish(task)
        except Exception as exc:
            self.service.finish(task, str(exc))
            raise

    @staticmethod
    def _require_draft(task: Task) -> None:
        if task.status != TaskStatus.DRAFT:
            raise TaskStateError("只有 draft 任务可以准备办公交付物")


def _pdf_draft(data: dict) -> StagedPdf:
    return StagedPdf(
        staged_path=data["staged_path"], final_path=data["final_path"], source_docx=data["source_docx"], source_sha256=data["source_sha256"],
        sha256=data["sha256"], validation=PdfValidation(**data["validation"]), render_pdf_path=data["render_pdf_path"],
        render_image_paths=data["render_image_paths"], summary=data["summary"],
    )


def _email_draft(data: dict) -> StagedEmailDraft:
    return StagedEmailDraft(
        staged_path=data["staged_path"], final_path=data["final_path"], sha256=data["sha256"], recipients=data["recipients"],
        subject=data["subject"], attachments=data["attachments"], validation=EmailDraftValidation(**data["validation"]), summary=data["summary"],
    )
