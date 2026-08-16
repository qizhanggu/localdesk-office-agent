from pathlib import Path
from argparse import Namespace
import pytest
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig, WorkspaceError
from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.service import DesktopTaskService, TaskStateError
from localdesk.desktop.skills.files import FileSkill
from localdesk.desktop.file_workflow import FileOrganizationWorkflow
from localdesk.desktop.registry import DesktopToolExecutionError
from localdesk.desktop.cli import run_desktop_foundation

@pytest.fixture
def setup(tmp_path):
    managed, source, out, tasks = tmp_path/'downloads', tmp_path/'source', tmp_path/'out', tmp_path/'tasks'
    for p in (managed, source, out, tasks): p.mkdir()
    ws=DesktopWorkspace(WorkspaceConfig(read_roots=[source], managed_roots=[managed], output_root=out, task_root=tasks))
    svc=DesktopTaskService(DesktopPolicyGuard(ws), TaskTraceStore(ws)); return ws,svc,FileOrganizationWorkflow(svc, FileSkill(ws))

def test_dry_run_confirm_and_rollback(setup):
    ws,svc,wf=setup
    for n in ('a.pdf','b.png','c.zip','d.txt'): (ws.managed_roots[0]/n).write_text(n)
    task=svc.create_task('整理下载目录'); plan=wf.prepare(task,str(ws.managed_roots[0]))
    assert len(plan.operations)==4 and task.status.value=='awaiting_confirmation'
    assert (ws.managed_roots[0]/'a.pdf').exists() # dry-run zero side effect
    wf.confirm_and_execute(task,True)
    assert task.status.value=='succeeded' and (ws.managed_roots[0]/'PDF'/'a.pdf').exists()
    assert len(wf.journal_path(task).read_text(encoding='utf-8').splitlines())==4
    rollback=svc.create_task('回滚'); rplan=wf.prepare_rollback(rollback,task)
    assert len(rplan.operations)==4 and rollback.status.value=='awaiting_confirmation'
    wf.confirm_and_execute(rollback,True)
    assert (ws.managed_roots[0]/'a.pdf').exists()

def test_no_confirmation_or_conflict_has_no_move(setup):
    ws,svc,wf=setup; (ws.managed_roots[0]/'a.pdf').write_text('x')
    task=svc.create_task('整理'); wf.prepare(task,str(ws.managed_roots[0])); wf.confirm_and_execute(task,False)
    assert (ws.managed_roots[0]/'a.pdf').exists()
    (ws.managed_roots[0]/'PDF').mkdir(); (ws.managed_roots[0]/'PDF'/'a.pdf').write_text('exists')
    task2=svc.create_task('整理');
    with pytest.raises(TaskStateError): wf.prepare(task2,str(ws.managed_roots[0]))
    assert (ws.managed_roots[0]/'a.pdf').exists()

def test_outside_and_symlink_rejected(setup, tmp_path):
    ws,svc,wf=setup
    with pytest.raises(DesktopToolExecutionError, match='授权范围'): wf.prepare(svc.create_task('x'),str(tmp_path))
    target=tmp_path/'outside.txt'; target.write_text('x'); link=ws.managed_roots[0]/'escape.pdf'
    try: link.symlink_to(target)
    except OSError: pytest.skip('symlink unavailable')
    plan=wf.files.dry_run(ws.managed_roots[0]); assert not plan.operations and plan.conflicts

def test_mocked_symlink_is_rejected_without_platform_permission(setup):
    ws,svc,_=setup; suspect=ws.managed_roots[0]/'fake.pdf'; suspect.write_text('x')
    skill=FileSkill(ws,is_symlink=lambda path: path == suspect)
    plan=skill.dry_run(ws.managed_roots[0])
    assert not plan.operations and '符号链接拒绝' in plan.conflicts[0] and suspect.exists()

def test_partial_failure_journals_successes_and_stops(setup):
    ws,svc,_=setup
    for n in ('1.pdf','2.pdf','3.pdf','4.pdf','5.pdf'): (ws.managed_roots[0]/n).write_text(n)
    count={'n':0}
    def mover(src,dst):
        count['n']+=1
        if count['n']==4: raise OSError('simulated disk error')
        import shutil; return shutil.move(src,dst)
    wf=FileOrganizationWorkflow(svc,FileSkill(ws,mover=mover)); task=svc.create_task('整理'); wf.prepare(task,str(ws.managed_roots[0]))
    with pytest.raises(WorkspaceError,match='停止'): wf.confirm_and_execute(task,True)
    rows=[__import__('json').loads(x) for x in wf.journal_path(task).read_text(encoding='utf-8').splitlines()]
    assert [x['status'] for x in rows]==['succeeded']*3+['failed']
    assert task.status.value=='failed' and (ws.managed_roots[0]/'5.pdf').exists()
    rollback=svc.create_task('回滚'); assert len(wf.prepare_rollback(rollback,task).operations)==3

def test_cancelled_task_does_not_execute_unstarted_operations(setup):
    ws,svc,wf=setup
    for n in ('a.pdf','b.pdf'): (ws.managed_roots[0]/n).write_text(n)
    task=svc.create_task('整理'); wf.prepare(task,str(ws.managed_roots[0])); wf.confirm_and_execute(task,False)
    assert task.status.value=='cancelled' and (ws.managed_roots[0]/'a.pdf').exists() and not wf.journal_path(task).exists()

def test_rollback_preview_has_zero_side_effect(setup):
    ws,svc,wf=setup; (ws.managed_roots[0]/'a.pdf').write_text('x')
    task=svc.create_task('整理'); wf.prepare(task,str(ws.managed_roots[0])); wf.confirm_and_execute(task,True)
    rollback=svc.create_task('回滚'); wf.prepare_rollback(rollback,task)
    assert (ws.managed_roots[0]/'PDF'/'a.pdf').exists() and not (ws.managed_roots[0]/'a.pdf').exists()

def test_target_created_after_preview_is_rejected_and_journaled(setup):
    ws,svc,wf=setup; (ws.managed_roots[0]/'a.pdf').write_text('x')
    task=svc.create_task('整理'); wf.prepare(task,str(ws.managed_roots[0]))
    (ws.managed_roots[0]/'PDF').mkdir(); (ws.managed_roots[0]/'PDF'/'a.pdf').write_text('race')
    with pytest.raises(WorkspaceError,match='覆盖'): wf.confirm_and_execute(task,True)
    rows=wf.journal_path(task).read_text(encoding='utf-8').splitlines()
    assert len(rows)==1 and 'failed' in rows[0] and (ws.managed_roots[0]/'a.pdf').exists()

def test_read_and_output_roots_are_never_manageable(setup):
    ws,svc,wf=setup
    for root in (ws.read_roots[0],ws.output_root):
        (root/'a.pdf').write_text('x')
        with pytest.raises(WorkspaceError): wf.prepare(svc.create_task('非法整理'),str(root))


def test_changed_source_after_preview_is_rejected_before_move(setup):
    ws, svc, wf = setup
    source = ws.managed_roots[0] / 'a.pdf'
    source.write_text('before', encoding='utf-8')
    task = svc.create_task('整理')
    wf.prepare(task, str(ws.managed_roots[0]))
    source.write_text('after', encoding='utf-8')

    with pytest.raises(WorkspaceError, match='重新 dry-run'):
        wf.confirm_and_execute(task, True)

    assert source.read_text(encoding='utf-8') == 'after'
    assert not (ws.managed_roots[0] / 'PDF' / 'a.pdf').exists()


def test_cli_file_dry_run_confirm_and_separately_confirmed_rollback(tmp_path, capsys):
    managed, output, tasks = tmp_path / 'downloads', tmp_path / 'output', tmp_path / 'tasks'
    for directory in (managed, output, tasks):
        directory.mkdir()
    (managed / 'a.pdf').write_text('pdf', encoding='utf-8')
    common = {
        'desktop_read_root': [],
        'desktop_managed_root': [str(managed)],
        'desktop_output_root': str(output),
        'desktop_task_root': str(tasks),
        'desktop_report_name': None,
        'desktop_web_url': [],
        'desktop_browser_domain': [],
        'desktop_docx_name': None,
        'desktop_grounded_llm': False,
    }

    assert run_desktop_foundation(Namespace(**common, desktop_task='整理样例目录', desktop_file_organize_root=str(managed), desktop_rollback_task=None, desktop_confirm_task=None)) == 0
    original_id = next(tasks.iterdir()).name
    assert (managed / 'a.pdf').exists()
    assert run_desktop_foundation(Namespace(**common, desktop_task=None, desktop_file_organize_root=None, desktop_rollback_task=None, desktop_confirm_task=original_id)) == 0
    assert (managed / 'PDF' / 'a.pdf').exists()

    assert run_desktop_foundation(Namespace(**common, desktop_task=None, desktop_file_organize_root=None, desktop_rollback_task=original_id, desktop_confirm_task=None)) == 0
    rollback_id = max(tasks.iterdir(), key=lambda path: path.stat().st_mtime_ns).name
    assert (managed / 'PDF' / 'a.pdf').exists()
    assert run_desktop_foundation(Namespace(**common, desktop_task=None, desktop_file_organize_root=None, desktop_rollback_task=None, desktop_confirm_task=rollback_id)) == 0
    assert (managed / 'a.pdf').exists()

    output_text = capsys.readouterr().out
    assert 'file organization staged' in output_text
    assert 'file rollback staged' in output_text
