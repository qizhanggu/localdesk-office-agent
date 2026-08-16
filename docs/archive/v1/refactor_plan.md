# LocalDesk Agent 重构设计与验证计划

> 状态：Phase 2 已完成并暂停验收；资料检索、staging Markdown 与确认交付已经实现，尚未进入文件整理。本文约束后续改造顺序；任何超出 v1 范围的能力须另行评审。

## 1. 目标与非目标

LocalDesk Agent 是一个面向**用户明确授权目录**的本地任务 Agent。v1 的目标是完成“资料检索 → Markdown 交付物”与“文件整理预览 → 用户确认 → 可追溯执行”两个闭环。

v1 不做：任意 Shell、删除、覆盖写入、鼠标键盘自动化、浏览器自动化、Electron、邮件日历、云盘、Multi-Agent 团队、复杂 RAG 或 DOCX 解析。

## 2. 改造策略

采用“并行新增、默认隔离”的方式：保留原 Coding Agent 原样可运行；新增 Desktop Runtime 和 Registry。Desktop 模式只注册经过 Policy Guard 约束的新工具，绝不通过禁用列表去“碰巧避开”旧的 Bash/编辑工具。

```text
CLI / Textual UI
  -> DesktopTaskService
      -> Planner（只产生结构化计划，不操作文件）
      -> DesktopPolicyGuard（独立、deny-first）
      -> DesktopToolRegistry
          -> Knowledge Skill
          -> Document Skill
          -> File Skill
      -> TaskTraceStore
```

建议新增目录：

```text
localdesk/desktop/
  models.py        # Task、Action、Artifact、TraceEvent、状态枚举
  workspace.py     # 授权根、Windows 路径规范化、路径归属
  policy.py        # 多路径检查、风险判定、确认令牌
  trace_store.py   # task.json + events.jsonl，原子写入/恢复
  service.py       # 状态机与执行编排
  planner.py       # 计划 schema、LLM 输出校验
  skills/
    knowledge.py   # MD/TXT/文本型 PDF、分块、词法检索、引用
    document.py    # Markdown staging、预览、提交产物
    files.py       # 扫描、dry-run、move/rename、回滚清单
```

## 3. 模块清单与验证方式

| 类型 | 模块 | 具体动作 | 验证 |
|---|---|---|---|
| 保留 | Agent / Client / Conversation / Tool 基类 | 不改变原有行为 | 原有单测 + Registry 快照 |
| 保留后适配 | Textual 确认界面 | 展示 Desktop 计划、预览和批准/拒绝 | UI 事件的单元/集成测试 |
| 冻结 | Bash、EditFile、WriteFile、Worktree、Teams、AgentTool | Desktop Registry 不导入、不注册 | 断言 Desktop 工具列表不含它们 |
| 新增 | Workspace + Policy Guard | 多授权根、真实路径检查、禁止越权/覆盖/删除/Shell | `..`、符号链接、双路径移动、覆盖用例 |
| 新增 | Task + Trace Store | 状态机、计划、确认、事件、产物 | 重启恢复、无确认零副作用、事件顺序 |
| 新增 | Knowledge Skill | 资料解析、轻量检索、来源定位 | 命中路径/页码/片段稳定且可读 |
| 新增 | Document Skill | staging、哈希、确认后提交 Markdown | 未确认 output 为空；确认后产物和 trace 一致 |
| 新增 | File Skill | 预览、受控移动/重命名、journal | 不覆盖；执行结果匹配计划；回滚清单可用 |

## 4. 不可突破的安全规则

1. 只读只能访问资料根目录与任务 staging；写入只能访问 staging 与 output 根目录。
2. 每条源路径和目标路径必须在 `resolve()` 后独立检查；越权和符号链接逃逸直接拒绝。
3. 所有写入、移动、重命名都先生成预览，并要求与该预览绑定的一次性确认。
4. v1 禁止 Shell、删除、网络访问和覆盖同名目标；这四类请求直接失败并写 Trace。
5. 模型提供的是计划草案，不能跳过 Policy Guard 直接触发文件系统调用。

## 5. 里程碑

### M0：基线与审计（当前）

- 基线标签、当前架构文档、重构计划、开发依赖与测试结果。
- 完成条件：文档可解释现有链路和每类模块的去向；原代码未被业务改动。

### M1：安全任务骨架

- `Task` 状态机：`draft -> planned -> awaiting_confirmation -> executing -> succeeded | failed | cancelled`。
- Workspace、Policy Guard、Trace Store 与 Desktop Registry。
- 完成条件：无 LLM 也能以测试证明越权、覆盖、Shell、删除均被拒绝。

实现记录：已交付 `localdesk/desktop/` Foundation 和 `--desktop` 零副作用入口；验证结果见 [`phase1_foundation.md`](phase1_foundation.md)。Textual 状态展示将在首个可执行 Skill 接入时补充，避免先做无业务数据的 UI。

### M2：资料到 Markdown

- MD/TXT/PDF 文本提取、词法检索、带来源引用的 Markdown staging/commit。
- 完成条件：未确认不写 output；确认后产物、哈希、引用都可从 Trace 验证。

实现记录：已完成，验收结论、测试结果、手工验证步骤与已知限制见 [`phase2_acceptance.md`](phase2_acceptance.md)。

### M3：文件整理

- 扫描、分类计划、确认、移动/重命名和回滚清单。
- 完成条件：零覆盖；结果完全符合预览；越权目标拒绝率 100%。

### M4：评估与展示

- 20–30 条固定任务、fake LLM 测试、README、演示视频。
- 完成条件：输出成功率、引用有效率、确认合规率、危险操作拦截率等指标。

## 6. 提交纪律

每个里程碑至少一个聚焦提交：

```text
docs(audit): document MewCode baseline and LocalDesk refactor boundary
feat(desktop): add task workspace policy and trace foundation
feat(desktop): add knowledge to markdown delivery workflow
feat(desktop): add confirmed file organization workflow
docs(showcase): add evaluation results and LocalDesk demos
```

只有已新增或实质改造的模块才作为个人工作成果描述；README 必须保留底座来源和独立改造范围说明。
