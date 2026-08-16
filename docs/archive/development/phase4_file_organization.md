# Phase 4：受控文件整理与独立回滚

**状态：已完成（2026-07-21）**

## 用户现在能运行什么

LocalDesk 现在提供一条真实 CLI 文件整理闭环。它只作用于用户显式声明的 `managed_roots`，不读取或整理其它目录：

```text
扫描授权目录 → 展示精确移动清单与文件哈希 → 独立确认 → 串行移动 + journal
                                                       ↓
                           新建 rollback 任务 → 再次独立确认 → 按 journal 逆序恢复
```

报告交付和文件整理是两个不同的 Task。即使一份报告已经确认交付，也不会让 LocalDesk 自动移动任何本地文件。

## 关键实现

- Registry 新增 `files.scan`（R0）、`files.move`（R3）和 `files.rollback_move`（R3）；所有文件操作与资料检索、文档交付共用同一个 Policy Guard、Task 状态机和 Trace。
- `--desktop-file-organize-root` 只创建 dry-run。控制台会打印每一条 `source -> destination`；确认前，目录中的文件不变。
- `--desktop-confirm-task <task_id>` 执行已经批准的移动。每一条动作都会在执行前复核 `managed_roots` 边界、普通文件属性、目标不存在、文件大小和 SHA-256；随后串行写入 `operations.jsonl`。
- `--desktop-rollback-task <original_task_id>` 只创建回滚预览；它不执行移动。回滚 Task 必须再次通过 `--desktop-confirm-task` 确认，且按成功 journal 的逆序恢复。
- 不允许覆盖、删除、Shell 或越权目录。符号链接与 Windows junction 会被拒绝；测试还覆盖了预览后目标被抢占、源文件被修改、中途 I/O 失败和只回滚已成功动作。
- Trace 除 `file_dry_run`、`file_operations_completed`、`rollback_dry_run` 外，还保留每个 `files.*` 工具的请求、策略决策、执行与后置验证事件。journal 被登记为任务 Artifact，便于定位和解释。

## 无敏感 Demo

请只用手工构造的样例目录，不要对真实 Downloads、简历或公司资料直接演示。

```powershell
# 准备 D:\demo\downloads，放入 a.pdf、b.png、c.zip、d.txt 等构造文件。
python -m localdesk --desktop `
  --desktop-managed-root D:\demo\downloads `
  --desktop-output-root D:\demo\output `
  --desktop-task-root D:\demo\tasks `
  --desktop-task "按文件类型整理样例下载目录" `
  --desktop-file-organize-root D:\demo\downloads

# 观察 preview 后，复制第一步输出的 task_id；这一步才会真的移动文件。
python -m localdesk --desktop `
  --desktop-managed-root D:\demo\downloads `
  --desktop-output-root D:\demo\output `
  --desktop-task-root D:\demo\tasks `
  --desktop-confirm-task <organize_task_id>

# 下面仅创建回滚预览；仍不会移动文件。
python -m localdesk --desktop `
  --desktop-managed-root D:\demo\downloads `
  --desktop-output-root D:\demo\output `
  --desktop-task-root D:\demo\tasks `
  --desktop-rollback-task <organize_task_id>

# 复制上一步新产生的 rollback task_id 后，单独确认才真正恢复。
python -m localdesk --desktop `
  --desktop-managed-root D:\demo\downloads `
  --desktop-output-root D:\demo\output `
  --desktop-task-root D:\demo\tasks `
  --desktop-confirm-task <rollback_task_id>
```

## 测试与评测

`evaluation/run_phase4_evaluation.py` 会运行受控文件 workflow、Desktop Runtime、报告和 Grounded Renderer 的核心回归，并将真实结果写入 `evaluation/results/phase4_file_organization.json`。其中包括一条真实 CLI 的“dry-run → 确认移动 → 新建回滚 Task → 再确认恢复”测试。

## 已知边界

- 分类规则目前仅是确定性扩展名映射（PDF、Images、Archives、Text、Other），不让模型决定删除、重命名或目录权限。
- 不支持覆盖同名文件；发生冲突时必须由用户在 LocalDesk 外自行处理，再重新 dry-run。
- Windows 当前账户没有创建真实 symlink 的权限，因此该测试会跳过；mock 注入的拒绝路径已回归通过。junction 同样会在运行时被拒绝。
- 这不是任意文件管理器，也不应对真实敏感目录直接运行。

## 下一步为什么是 Phase 5

核心办公工作流现在包括资料检索、受控网页读取、Markdown/DOCX 交付和可逆文件整理，且都已进入同一 Runtime。下一步才具备讨论 Windows Desktop Computer Use 的条件：它必须在自建测试应用上采用 UIA 优先、视觉 fallback 和人工接管，不能借由 GUI 绕开现有授权与确认边界。

## 面试复盘重点

1. 为什么 dry-run 和执行前哈希复核同时需要：前者给用户可读预览，后者解决预览到执行之间的 TOCTOU 变化。
2. 为什么 rollback 也要单独建 Task、单独确认：恢复动作本身也是有副作用的文件移动，不能把“可撤销”误解为“可自动执行”。
3. 为什么 journal 只记录成功和失败的实际动作：当中途失败时，系统只为已成功部分生成可解释的恢复计划，而不是声称整批操作具有不存在的原子性。
