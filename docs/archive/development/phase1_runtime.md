# Phase 1：统一受控 Runtime 的纵向闭环

**状态：已完成（2026-07-21）**

## 这一阶段解决了什么

原有的检索、Markdown 生成和交付能力可以各自工作，但它们需要由同一条受控链路管理，避免后续接入更多工具后出现“有些操作绕过权限或审计”的问题。本阶段将最核心、最适合展示的链路先做成真实可运行的闭环：

```text
本地资料检索 → 生成 Markdown staging → 用户确认 → 写入 output → Trace 可追溯
```

用户现在可以在明确授权的本地目录中检索资料，先得到暂存的 Markdown；在未确认前，交付目录不会被修改。确认时会复核草稿哈希，成功后才交付，并保留任务事件记录。

## 关键改动

- 新增 `DesktopToolRegistry`：将 `knowledge.search`、`document.stage_markdown`、`document.commit_markdown` 纳入统一注册、参数校验、Policy、审批状态和执行后验证流程。
- 将 `KnowledgeReportWorkflow` 接入 Registry，而非让工作流直接绕过安全检查调用底层实现。
- 明确目录职责：`read_roots` 只读，`task_root/staging` 可写草稿，`output_root` 只能在确认后交付。
- 为每个工具调用记录 `tool_requested`、`tool_policy_decided`、`tool_completed`、`tool_verified` 等 Trace 事件，形成可检查的执行证据。
- 补齐未授权、确认前零副作用、草稿内容变化、交付成功和 Trace 链路的回归测试。

## 验证结果

运行的核心回归命令：

```powershell
python -m pytest -q tests/test_desktop_foundation.py tests/test_desktop_reporting.py tests/test_file_workflow.py tests/test_grounded_renderer.py -p no:cacheprovider --basetemp .pytest-desktop-final
```

结果：**35 passed, 1 skipped**。`skipped` 是环境相关的既有跳过项，不是本阶段失败。

Phase 0 的评测脚本也继续保留并可重复运行；它使用 25 条无敏感任务描述和上述核心测试作为基线，不把尚未完成的端到端模型能力包装成评测成绩。

## 现在真实可以演示什么

1. 准备一个仅包含构造资料的 `read_roots` 目录和一个空的 `output_root` 目录。
2. 运行本地资料检索与报告准备命令，得到任务 staging 中的 Markdown 草稿和 Trace。
3. 检查输出目录仍为空；确认任务后，系统复核草稿哈希并把同一份内容交付到输出目录。
4. 查看任务事件，能够解释每一步是否通过 Policy、是否等待确认、最终交付了什么。

## 已知边界

- 尚未引入 SQLite、暂停恢复或通用的复杂任务编排；当前优先保证单条关键链路可解释、可测试。
- 文件整理工作流仍是独立的确定性核心模块，尚未注册为 Runtime 的正式工具。
- 不允许任意 Shell、删除、覆盖写入或未经授权的路径访问。
- Phase 2 的公开网页资料能力正在推进，尚未以“阶段完成”对外表述。

## 下一步为什么是 Phase 2

接下来在不破坏这条闭环的前提下，补充受域名白名单约束的公开网页读取，并用**确定性 Reviewer**校验引用与交付质量。第一版不引入 Reviewer Role Agent：规则校验更稳定、更容易测试，也更符合当前项目先完成闭环再扩展复杂度的原则。

## 面试复盘重点

- LLM 或工作流只能提出操作意图；真正决定是否执行的是 Runtime 中的 Schema、Policy、Approval 与 Verification 管道。
- 为什么要先 staging、确认时再校验 SHA-256：它避免“用户确认的是 A，最终交付却变成 B”的内容替换问题。
