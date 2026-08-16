# Phase 1 Foundation 交付记录

> 日期：2026-07-16
> 范围：任务状态、授权工作区、强制策略、Trace 和最小 CLI 入口。
> 非范围：资料检索、报告生成、真实文件移动、Textual 任务面板；这些留给后续小步实现。

## 新增边界

`localdesk/desktop/` 是与原 Coding Agent 并存的新包：

- `models.py`：Task、Action、Artifact、TraceEvent 和受限状态机。
- `workspace.py`：绝对路径、资料只读根、可整理目录、产物输出目录、任务 Trace 目录。
- `policy.py`：deny-first；拒绝越权、覆盖、删除、Shell、网络；写入/移动/重命名返回 `ask`，必须确认。
- `trace_store.py`：每个 task 写入 `task.json` 与 `events.jsonl`，任务状态和确认决定可回放。
- `service.py`：计划审查、状态流转、确认和结束；被策略拒绝的计划不能进入执行。
- `registry.py`：Desktop Registry 当前为空，明确不泄漏 `Bash`、`WriteFile`、`EditFile`、Team 等旧工具。
- `cli.py`：最小 `--desktop` 入口，只创建任务/Trace，不执行文件操作。

“资料目录”和“可整理目录”是不同能力：前者只能读取，后者才允许在用户确认后移动或重命名。这避免 Agent 以“我能读到”为理由改动任意资料。

## 当前可运行命令

```powershell
python -m localdesk --desktop `
  --desktop-task "汇总会议纪要" `
  --desktop-read-root "D:\\demo\\notes" `
  --desktop-output-root "D:\\demo\\output" `
  --desktop-task-root "D:\\demo\\localdesk-tasks"
```

此命令当前只会验证绝对授权路径并创建 `task_id` 与 Trace；输出会明确提示 `desktop tools registered: 0` 和“没有执行文件操作”。它不是可交付的报告功能，不能夸大为完整 Desktop Agent。

## 验证

```powershell
python -m pytest -q tests/test_desktop_foundation.py -p no:cacheprovider --basetemp .pytest-desktop-foundation-v3
```

结果：**14 passed**。

覆盖点：相对路径拒绝、授权根读写边界、越权拒绝、覆盖拒绝、删除/Shell/网络拒绝、移动确认、状态机、Trace 回放、被拒绝计划不可确认、默认 Coding 工具不泄漏、Desktop CLI 零副作用。
