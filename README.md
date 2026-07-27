# LocalDesk Agent

面向用户**明确授权目录与公开域名**的受控 Office Agent：检索本地资料和指定网页，生成带来源的 Markdown/DOCX，按风险分级交付，并用可回放 Trace 记录全过程。当前主业务 Demo 是“岗位 JD + 本地履历 → 定向求职材料”。

## 来源与独立改造范围

本仓库基于 MewCode Python Coding Agent 学习型底座改造。原始代码及来源标注保留，不宣称从零开发。本人独立完成的 LocalDesk 改造集中在 `localdesk/desktop/`：任务状态机、路径授权、deny-first Policy Guard、Trace、资料检索、staging/哈希确认交付、Grounded LLM 渲染约束、文件整理与回滚核心工作流、测试与文档。

## 架构

```text
用户任务
  -> Knowledge Skill（仅 read_roots，返回 citation_id）
  -> Deterministic / Grounded LLM Renderer（只接收检索片段）
  -> Document Skill（task staging + SHA-256）
  -> Policy Guard + 风险分级
  -> 新建本地产物自动交付 / 高风险动作独立确认
  -> output_root + task Trace + 只读看板

managed_roots -> FileOrganizationWorkflow（dry-run + 哈希预览 -> 独立确认 -> journal -> 独立确认 rollback）
```

## 安全模型

| 目录 | 权限 |
|---|---|
| `read_roots` | 仅检索资料 |
| `managed_roots` | 仅确定性整理流程在独立确认后 move；禁止删除、覆盖和越权 |
| `output_root` | 新建且不覆盖的 Markdown / DOCX 可自动交付；覆盖拒绝 |
| `task_root` | task.json、events.jsonl、staging、operation journal |

越权、覆盖、删除、Shell 和未经声明的网络操作直接拒绝。所有文档先写 staging 并复核 SHA-256；新建本地产物可自动交付，批量移动仍需 dry-run 后确认，桌面输入/点击仍需确认，对外发送/提交尚未实现。每个任务都有 task_id、计划、策略决定、执行验证和产物 Trace。

## 当前能力与非目标

- 支持 MD/TXT/DOCX/可提取文本 PDF 的轻量检索，引用定位到行号、段落/表格行或页码。
- 支持 CSV/XLSX 的结构化读取、筛选、稳定排序、去重、列更新、确定性校验与新文件交付；不驱动 Excel GUI。
- 支持 DOCX 正文/标题/表格读取，以及经过 LibreOffice 渲染检查后的正式 PDF 交付；PDF 覆盖仍需确认。
- 支持生成带附件的标准 `.eml` 本地邮件草稿；它不连接邮箱、不登录、不发送邮件。
- 支持确定性带引用 Markdown 草稿和确认交付。
- 支持 Grounded LLM JSON 渲染：每段必须给出本次检索内真实 citation_id；幻觉引用、无引用、解析失败、超时均拒绝暂存。
- 支持受控文件整理 CLI：dry-run 预览、执行前 SHA-256 复核、确认后的串行 move、operation journal、独立确认 rollback；详见 [Phase 4](docs/phase4_file_organization.md)。
- 支持仅面向白名单测试窗口的 Windows UIA Demo：确认后输入构造文本、调用低风险按钮、验证窗口状态；UIA 不稳定时停止并人工接管，详见 [Phase 5](docs/phase5_desktop_computer_use.md)。
- 支持岗位 JD + 本地履历证据的确定性求职材料闭环：匹配/差距、用户反馈新版本、Markdown/DOCX、真实渲染检查、低风险交付和 Trace；详见 [Phase 6B](docs/phase6b_job_materials.md)。
- 支持只读 HTML 任务看板；数据直接来自真实 `task.json` 和 `events.jsonl`。
- 当前网页能力是“受控网页读取 + 页内链接发现”，不是完整 Browser Agent；尚无搜索引擎查询或跨站自动检索岗位。
- 不支持：任意 Shell、删除、覆盖、登录/验证码/支付、邮件自动发送、表单自动提交、任意第三方 GUI、扫描件 OCR。

## Phase 6A 可复现 Demo

```powershell
.\.venv\Scripts\python.exe evaluation\run_phase6a_evaluation.py
.\.venv\Scripts\python.exe evaluation\run_phase6a_demo.py
.\.venv\Scripts\python.exe evaluation\run_real_web_trace.py
```

三条命令分别验证统一离线回归、构造数据 + 真实 LibreOffice 的求职材料闭环，以及真实公开网页 Trace。结果保存在 `evaluation/results/`；Demo 输入均为公开或构造内容。

## 测试与评估

当前 Phase 6A 统一回归结果：**54 passed，1 skipped，0 failed**，真实结果见 [phase6a_baseline.json](evaluation/results/phase6a_baseline.json)。跳过项是当前 Windows 账户无法创建真实 symlink；mock 注入拒绝路径已通过。真实 LibreOffice Demo 与真实公开网页读取也已分别留档，但尚未声称真实求职材料质量、任意网页搜索成功率或第三方 GUI 成功率。

当前重构阶段证据见 [文档入口](docs/README.md)；旧项目材料位于 [v1 历史归档](docs/archive/v1/README.md)，不应与当前能力混用。
