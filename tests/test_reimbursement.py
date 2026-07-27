from pathlib import Path
import fitz
from docx import Document
from openpyxl import Workbook, load_workbook
from localdesk.desktop.skills.reimbursement import ReimbursementSkill
from localdesk.desktop.reimbursement_workflow import ReimbursementWorkflow
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.docx_delivery import RenderCheck
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig

def test_invoice_matching_flags_missing_duplicate_and_mismatch(tmp_path: Path):
    sources, output, tasks = tmp_path/'sources', tmp_path/'out', tmp_path/'tasks'
    for p in (sources, output, tasks): p.mkdir()
    ws=DesktopWorkspace(WorkspaceConfig(read_roots=[sources],output_root=output,task_root=tasks)); (tasks/'t').mkdir()
    book=Workbook(); s=book.active; s.append(['payment_id','invoice_no','amount']); s.append(['p1','INV-1',100]); s.append(['p2','MISS',20]); s.append(['p3','DUP',30]); s.append(['p4','INV-2',50]); book.save(sources/'payments.xlsx')
    Document().save(sources/'rules.docx')
    def invoice(name,text):
        pdf=fitz.open(); page=pdf.new_page(); page.insert_text((72,72),text); pdf.save(sources/name); pdf.close()
    invoice('one.pdf','Invoice No: INV-1\nTotal: 100.00'); invoice('two.pdf','Invoice No: INV-2\nTotal: 49.00'); invoice('three.pdf','Invoice No: DUP\nTotal: 30.00'); invoice('four.pdf','Invoice No: DUP\nTotal: 30.00')
    skill=ReimbursementSkill(ws); result=skill.analyze(sources/'payments.xlsx',[sources/'one.pdf',sources/'two.pdf',sources/'three.pdf',sources/'four.pdf'],sources/'rules.docx')
    assert result.matched_count==1 and result.flagged_count==3
    assert [x.status for x in result.findings]==['matched','missing_invoice','duplicate_invoice','amount_mismatch']
    out=skill.write_flagged_xlsx('t','flagged_payments.xlsx',result)
    check=load_workbook(out,read_only=True); assert check.active.max_row==4; check.close()

def test_reimbursement_workflow_records_trace(tmp_path: Path):
    # Workflow plumbing is covered separately; analysis logic above remains deterministic.
    sources, output, tasks = tmp_path/'s', tmp_path/'o', tmp_path/'t'
    for p in (sources,output,tasks): p.mkdir()
    ws=DesktopWorkspace(WorkspaceConfig(read_roots=[sources],output_root=output,task_root=tasks)); service=DesktopTaskService(DesktopPolicyGuard(ws),TaskTraceStore(ws)); task=service.create_task('reconcile')
    wb=Workbook(); wsht=wb.active; wsht.append(['payment_id','invoice_no','amount']); wsht.append(['x','NONE',1]); wb.save(sources/'p.xlsx'); Document().save(sources/'r.docx')
    pdf=fitz.open(); pdf.new_page().insert_text((72,72),'Invoice No: OTHER\nTotal: 1'); pdf.save(sources/'i.pdf'); pdf.close()
    result, staged=ReimbursementWorkflow(service,ReimbursementSkill(ws)).prepare(task,str(sources/'p.xlsx'),[str(sources/'i.pdf')],str(sources/'r.docx'))
    assert result.flagged_count==1 and staged.exists() and task.status.value=='awaiting_confirmation'
    assert 'reimbursement_analyzed' in [e['event_type'] for e in service.trace_store.load_events(task.task_id)]

def test_summary_pdf_and_local_email_are_staged(tmp_path: Path):
    sources, output, tasks = tmp_path/'s', tmp_path/'o', tmp_path/'t'
    for p in (sources,output,tasks): p.mkdir()
    ws=DesktopWorkspace(WorkspaceConfig(read_roots=[sources],output_root=output,task_root=tasks)); service=DesktopTaskService(DesktopPolicyGuard(ws),TaskTraceStore(ws)); task=service.create_task('reconcile')
    wb=Workbook(); sh=wb.active; sh.append(['payment_id','invoice_no','amount']); sh.append(['x','NONE',1]); wb.save(sources/'p.xlsx'); Document().save(sources/'r.docx')
    raw=fitz.open(); raw.new_page().insert_text((72,72),'Invoice No: OTHER\nTotal: 1'); raw.save(sources/'i.pdf'); raw.close()
    flow=ReimbursementWorkflow(service,ReimbursementSkill(ws)); result, flagged=flow.prepare(task,str(sources/'p.xlsx'),[str(sources/'i.pdf')],str(sources/'r.docx'))
    docx, pdf, email=flow.stage_summary_and_email(task,result,flagged,FakeRenderer(),'finance@example.com')
    assert docx.exists() and Path(pdf.staged_path).exists() and Path(email.staged_path).exists()
    assert 'reimbursement_summary_staged' in [e['event_type'] for e in service.trace_store.load_events(task.task_id)]

class FakeRenderer:
    def render(self, _docx, out):
        out.mkdir(parents=True,exist_ok=True); p=out/'summary.pdf'; d=fitz.open(); d.new_page().insert_text((72,72),'summary'); d.save(p); d.close(); image=out/'page-1.png'; image.write_bytes(b'png'); return RenderCheck(True,[],str(p),[str(image)],1)
