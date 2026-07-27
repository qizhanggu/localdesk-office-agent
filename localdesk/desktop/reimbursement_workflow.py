"""将确定性报销核对接入 Task Trace；产物仍停留在 staging，等待统一交付。"""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from docx import Document
from localdesk.desktop.docx_delivery import DocxRenderer
from localdesk.desktop.skills.office_artifacts import EmailDraftSkill, PdfDeliverySkill, StagedEmailDraft, StagedPdf
from localdesk.desktop.models import ActionKind, PlannedAction, Task, TaskStatus
from localdesk.desktop.registry import DesktopToolRegistry, create_desktop_registry
from localdesk.desktop.service import DesktopTaskService, TaskStateError
from localdesk.desktop.skills.reimbursement import ReimbursementResult, ReimbursementSkill

class ReimbursementWorkflow:
    def __init__(self, service: DesktopTaskService, skill: ReimbursementSkill, registry: DesktopToolRegistry | None = None) -> None:
        self.service, self.skill = service, skill; self.registry = registry or create_desktop_registry(service)

    def prepare(self, task: Task, payments_xlsx: str, invoice_pdfs: list[str], rules_docx: str, output_name: str = "flagged_payments.xlsx") -> tuple[ReimbursementResult, Path]:
        if task.status != TaskStatus.DRAFT: raise TaskStateError("只有 draft 任务可准备报销核对")
        result = self.skill.analyze(payments_xlsx, invoice_pdfs, rules_docx)
        staged = self.skill.write_flagged_xlsx(task.task_id, output_name, result)
        action = PlannedAction("deliver-flagged-payments", "spreadsheet.commit", ActionKind.WRITE, {"destination": str(self.skill.workspace.output_root / staged.name)}, "确认后交付问题支付清单", preview={"staged_path": str(staged), "analysis": asdict(result)})
        self.service.set_plan(task, "核对支付流水与发票；保守标记异常项，确认后交付问题清单。", [action])
        self.service.trace_store.append(task.task_id, "reimbursement_analyzed", {"matched_count": result.matched_count, "flagged_count": result.flagged_count, "source_hashes": result.source_hashes, "findings": [asdict(x) for x in result.findings]})
        self.service.trace_store.append(task.task_id, "reimbursement_xlsx_staged", {"path": str(staged)})
        return result, staged

    def stage_summary_and_email(self, task: Task, result: ReimbursementResult, flagged_xlsx: Path, renderer: DocxRenderer, recipient: str) -> tuple[Path, StagedPdf, StagedEmailDraft]:
        """生成可审阅 DOCX、经渲染验证的 PDF 和未发送 EML；均留在 staging。"""
        if task.status not in {TaskStatus.AWAITING_CONFIRMATION, TaskStatus.DRAFT}: raise TaskStateError("报销任务状态不允许追加交付物")
        summary = self.skill.workspace.task_dir(task.task_id) / "staging" / "reimbursement_summary.docx"
        doc = Document(); doc.add_heading("Reimbursement reconciliation summary", 0)
        doc.add_paragraph(f"Matched: {result.matched_count}; flagged: {result.flagged_count}.")
        table = doc.add_table(rows=1, cols=4); table.style = "Table Grid"
        for cell, value in zip(table.rows[0].cells, ["Payment", "Invoice", "Status", "Detail"]): cell.text = value
        for item in result.findings:
            if item.status != "matched":
                row = table.add_row().cells
                for cell, value in zip(row, [item.payment_id, item.invoice_no, item.status, item.detail]): cell.text = value
        doc.save(summary)
        pdf = PdfDeliverySkill(self.skill.workspace).stage_pdf(task.task_id, summary, "reimbursement_summary.pdf", renderer)
        email = EmailDraftSkill(self.skill.workspace).stage_draft(task.task_id, "reimbursement_review.eml", [recipient], "Reimbursement reconciliation draft", f"{result.flagged_count} payments require review. This is a local draft and was not sent.", [flagged_xlsx, pdf.staged_path])
        self.service.trace_store.append(task.task_id, "reimbursement_summary_staged", {"docx": str(summary), "pdf": asdict(pdf), "email": asdict(email)})
        return summary, pdf, email
