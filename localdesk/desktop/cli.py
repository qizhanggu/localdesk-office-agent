from __future__ import annotations

import asyncio
from argparse import Namespace
from pathlib import Path

from localdesk.desktop.policy import DesktopPolicyGuard
from localdesk.desktop.browser import HttpBrowserAdapter
from localdesk.desktop.docx_delivery import LibreOfficeDocxRenderer
from localdesk.desktop.computer_use import DesktopComputerWorkflow, WindowsUiaAdapter
from localdesk.desktop.dashboard import render_task_board
from localdesk.desktop.file_workflow import FileOrganizationWorkflow
from localdesk.desktop.job_materials import JobMaterialRequest, JobMaterialsWorkflow
from localdesk.desktop.reporting import KnowledgeReportWorkflow
from localdesk.desktop.registry import DesktopToolExecutionError, create_desktop_registry
from localdesk.desktop.service import DesktopTaskService, TaskStateError
from localdesk.desktop.skills.document import DocumentSkill
from localdesk.desktop.skills.files import FileSkill
from localdesk.desktop.skills.knowledge import KnowledgeSkill
from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.workspace import DesktopWorkspace, WorkspaceConfig, WorkspaceError


def run_desktop_foundation(args: Namespace) -> int:
    """运行 Desktop v1 的安全基础入口。

    当前入口只验证用户显式授权的目录、创建 task_id 和 Trace；资料检索、
    文档写入、文件整理会在后续 Skill 注册后接入，不能借此入口绕过策略。
    """
    file_only_request = bool(
        getattr(args, "desktop_file_organize_root", None)
        or getattr(args, "desktop_rollback_task", None)
        or getattr(args, "desktop_confirm_task", None)
        or getattr(args, "desktop_task_board", False)
    )
    if not args.desktop_read_root and not file_only_request:
        print("Desktop mode requires at least one --desktop-read-root", flush=True)
        return 2
    if not args.desktop_output_root or not args.desktop_task_root:
        print("Desktop mode requires --desktop-output-root and --desktop-task-root", flush=True)
        return 2

    try:
        workspace = DesktopWorkspace(
            WorkspaceConfig(
                read_roots=[Path(item) for item in args.desktop_read_root],
                managed_roots=[Path(item) for item in args.desktop_managed_root],
                browser_allowed_domains=list(getattr(args, "desktop_browser_domain", [])),
                desktop_allowed_window_titles=list(getattr(args, "desktop_window_title", [])),
                output_root=Path(args.desktop_output_root),
                task_root=Path(args.desktop_task_root),
            )
        )
    except WorkspaceError as exc:
        print(f"Desktop workspace error: {exc}", flush=True)
        return 2

    trace_store = TaskTraceStore(workspace)
    service = DesktopTaskService(DesktopPolicyGuard(workspace), trace_store)
    registry = create_desktop_registry(service)
    workflow = KnowledgeReportWorkflow(service, KnowledgeSkill(workspace), DocumentSkill(workspace), registry)
    job_workflow = JobMaterialsWorkflow(service, KnowledgeSkill(workspace), DocumentSkill(workspace), registry)
    file_workflow = FileOrganizationWorkflow(service, FileSkill(workspace), registry)
    computer_workflow = DesktopComputerWorkflow(service, WindowsUiaAdapter(), registry)

    if getattr(args, "desktop_task_board", False):
        board = render_task_board(trace_store)
        print(f"LocalDesk task board: {board}")
        return 0

    if getattr(args, "desktop_confirm_task", None):
        try:
            task = trace_store.load_task_object(args.desktop_confirm_task)
            if any(action.skill in {"files.move", "files.rollback_move"} for action in task.actions):
                file_workflow.confirm_and_execute(task, approved=True)
            elif any(action.skill.startswith("desktop.") for action in task.actions):
                computer_workflow.confirm_and_run(task, approved=True)
            else:
                workflow.confirm_and_deliver(task, approved=True)
        except (OSError, ValueError) as exc:
            print(f"Desktop delivery error: {exc}", flush=True)
            return 2
        print(f"LocalDesk task delivered: {task.task_id}")
        print(f"status: {task.status.value}")
        artifact = task.artifacts[-1]
        print(f"artifact: {artifact.final_path or artifact.staged_path}")
        return 0

    if getattr(args, "desktop_rollback_task", None):
        try:
            original = trace_store.load_task_object(args.desktop_rollback_task)
            task = service.create_task(f"回滚文件整理任务 {original.task_id}")
            plan = file_workflow.prepare_rollback(task, original)
        except (OSError, ValueError) as exc:
            print(f"Desktop file rollback error: {exc}", flush=True)
            return 2
        print(f"LocalDesk file rollback staged: {task.task_id}")
        print(f"status: {task.status.value}")
        print(f"operations: {len(plan.operations)}")
        print(f"journal source: {file_workflow.journal_path(original)}")
        print(f"confirm with --desktop-confirm-task {task.task_id}")
        return 0

    if not args.desktop_task:
        print("Desktop mode requires --desktop-task", flush=True)
        return 2
    task = service.create_task(args.desktop_task)
    if getattr(args, "desktop_computer_demo", False):
        titles = list(getattr(args, "desktop_window_title", []))
        if len(titles) != 1:
            print("Desktop computer error: Phase 5 Demo 需要且只接受一个 --desktop-window-title 白名单窗口", flush=True)
            return 2
        try:
            state = computer_workflow.prepare(task, titles[0], getattr(args, "desktop_ui_text", "LocalDesk safe demo"))
        except (DesktopToolExecutionError, TaskStateError, ValueError, RuntimeError) as exc:
            print(f"Desktop computer error: {exc}", flush=True)
            return 2
        print(f"LocalDesk desktop demo staged: {task.task_id}")
        print(f"status: {task.status.value}")
        print(f"window: {state.window_title}")
        print(f"uia controls: {[control.key for control in state.controls]}")
        print(f"confirm with --desktop-confirm-task {task.task_id}")
        return 0
    if getattr(args, "desktop_file_organize_root", None):
        if getattr(args, "desktop_report_name", None):
            print("Desktop file error: 报告交付与文件整理必须创建为两个独立任务、分别确认", flush=True)
            return 2
        try:
            plan = file_workflow.prepare(task, args.desktop_file_organize_root)
        except (DesktopToolExecutionError, TaskStateError, ValueError) as exc:
            print(f"Desktop file error: {exc}", flush=True)
            return 2
        print(f"LocalDesk file organization staged: {task.task_id}")
        print(f"status: {task.status.value}")
        print(f"operations: {len(plan.operations)}")
        print(f"conflicts: {len(plan.conflicts)}")
        for operation in plan.operations:
            print(f"preview: {operation.source} -> {operation.destination}")
        if plan.operations:
            print(f"confirm with --desktop-confirm-task {task.task_id}")
        else:
            print("nothing to move: dry-run produced no file operation")
        return 0
    if getattr(args, "desktop_job_materials", False):
        urls = list(getattr(args, "desktop_web_url", []))
        if len(urls) != 1:
            print("Desktop job materials error: 需要且只接受一个 --desktop-web-url 岗位 JD", flush=True)
            return 2
        if not getattr(args, "desktop_company", None) or not getattr(args, "desktop_role", None):
            print("Desktop job materials error: 需要 --desktop-company 和 --desktop-role", flush=True)
            return 2
        if not getattr(args, "desktop_report_name", None):
            print("Desktop job materials error: 需要 --desktop-report-name", flush=True)
            return 2
        try:
            draft = job_workflow.prepare(
                task,
                JobMaterialRequest(
                    company=args.desktop_company,
                    role=args.desktop_role,
                    jd_url=urls[0],
                    markdown_filename=args.desktop_report_name,
                    docx_filename=getattr(args, "desktop_docx_name", None),
                    feedback=getattr(args, "desktop_feedback", ""),
                ),
                HttpBrowserAdapter(),
                LibreOfficeDocxRenderer() if getattr(args, "desktop_docx_name", None) else None,
                auto_deliver=True,
            )
        except (DesktopToolExecutionError, TaskStateError, ValueError) as exc:
            print(f"Desktop job materials error: {exc}", flush=True)
            return 2
        print(f"LocalDesk job materials delivered: {task.task_id}")
        print(f"status: {task.status.value}")
        print(f"markdown: {draft.final_path}")
        if getattr(args, "desktop_docx_name", None):
            print(f"docx: {workspace.output_root / args.desktop_docx_name}")
        print("risk policy: new local artifacts auto-delivered; overwrite and external submission remain blocked")
        return 0
    if getattr(args, "desktop_report_name", None):
        try:
            if getattr(args, "desktop_web_url", []):
                draft = workflow.prepare(task, args.desktop_report_name, browser=HttpBrowserAdapter(), web_urls=list(args.desktop_web_url), docx_filename=getattr(args, "desktop_docx_name", None), docx_renderer=LibreOfficeDocxRenderer() if getattr(args, "desktop_docx_name", None) else None, auto_deliver=not getattr(args, "desktop_require_confirmation", False))
            elif getattr(args, "desktop_grounded_llm", False):
                if getattr(args, "desktop_docx_name", None):
                    raise ValueError("Grounded LLM 报告暂未接入 DOCX 质量门；请先使用确定性 Markdown → DOCX 交付路径")
                from localdesk.client import create_client
                from localdesk.config import load_config
                from localdesk.desktop.grounded_renderer import GroundedLLMRenderer

                config = load_config()
                if not config.providers:
                    raise ValueError("没有配置可用模型 provider")
                draft = asyncio.run(workflow.prepare_grounded(task, args.desktop_report_name, GroundedLLMRenderer(create_client(config.providers[0]))))
            else:
                draft = workflow.prepare(task, args.desktop_report_name, docx_filename=getattr(args, "desktop_docx_name", None), docx_renderer=LibreOfficeDocxRenderer() if getattr(args, "desktop_docx_name", None) else None, auto_deliver=not getattr(args, "desktop_require_confirmation", False))
        except (DesktopToolExecutionError, TaskStateError, ValueError) as exc:
            print(f"Desktop report error: {exc}", flush=True)
            return 2
        print(f"LocalDesk report staged: {task.task_id}")
        print(f"status: {task.status.value}")
        print(f"staging: {draft.staged_path}")
        print(f"planned output: {draft.final_path}")
        print(f"citations: {len(draft.source_citations)}")
        print(f"renderer: {'grounded-llm' if getattr(args, 'desktop_grounded_llm', False) else 'deterministic'}")
        if task.status.value == "awaiting_confirmation":
            print(f"confirm with --desktop-confirm-task {task.task_id}")
        else:
            print("delivered automatically under low-risk new-artifact policy")
        return 0
    print(f"LocalDesk task created: {task.task_id}")
    print(f"status: {task.status.value}")
    print(f"desktop tools registered: {len(registry.list_tools())}")
    print(f"trace: {workspace.task_dir(task.task_id)}")
    print("Foundation mode only: no file operation has been executed.")
    return 0
