# LocalDesk Office Agent 文档入口

这里仅保留本轮 LocalDesk Office Agent 重构的当前文档。阅读时以根目录的[计划.md](../计划.md)为总路线，以本目录中的阶段总结为实施证据；不要把 `archive/v1/` 中的旧文档当作当前能力说明。

| 文档 | 用途 | 当前状态 |
|---|---|---|
| [Phase 0：重建基线](phase0_rebaseline.md) | 品牌迁移、核心回归、评测基线 | 已完成 |
| [Phase 1：统一受控 Runtime](phase1_runtime.md) | 本地检索 → Markdown staging → 确认交付 → Trace 闭环 | 已完成 |
| [Phase 2：受控公开网页研究](phase2_controlled_research.md) | 网页白名单读取、确定性 Reviewer 与本地/网页资料合并交付 | 已完成 |
| [Phase 3：DOCX 交付与质量检查](phase3_docx_delivery.md) | Markdown 到 DOCX、结构检查、渲染检查与确认交付 | 已完成 |
| [Phase 4：受控文件整理与独立回滚](phase4_file_organization.md) | dry-run、独立确认、journal、哈希复核与独立 rollback | 已完成 |
| [Phase 5：Windows Desktop Computer Use](phase5_desktop_computer_use.md) | UIA、状态验证、人工接管与受限视觉 fallback | 已完成 |
| [Phase 6A：工程基线冻结](phase6a_baseline.md) | 统一评测、真实 Demo、README 与只读 Trace 看板 | 已完成 |
| [Phase 6B：定向求职材料闭环](phase6b_job_materials.md) | JD + 本地履历 → 匹配材料 → DOCX → 低风险交付 → Trace | 第一版已完成 |
| [Phase 7 B0+B1：公共 Benchmark 可行性](benchmark_feasibility.md) | OfficeBench 任务冻结、能力映射、Windows Spike 与 TheAgentCompany 调研 | B0+B1 已完成，B2 待审批 |
| [Phase 7 B2A：离线 Adapter 基础](phase7_b2a_offline_adapter.md) | 300 条静态统计、Dev 1-16/0 Adapter 契约与 dry-run | 已完成，B2B 待审批 |
| [OfficeBench 300 条任务统计](officebench_300_task_analysis.md) | 固定 commit 的应用、操作、文件、Evaluator 与链路频率 | 离线静态分析 |
| [Final Sprint 1：Excel/CSV 与环境检查](phase7_sprint1_excel_environment.md) | 结构化表格工具、测试证据与 OfficeBench B2B 环境阻塞 | Excel 已完成，环境待重启恢复 |
| [评测说明](../evaluation/README.md) | 评测集、运行方式与结果口径 | 持续积累 |
| [重构总计划](../计划.md) | 阶段路线、验收标准和决策依据 | 当前有效 |
| [v1 历史归档](archive/v1/README.md) | 改造前的设计、验收和展示材料 | 仅供追溯 |

## 阶段文档规则

每个阶段验收完成时，同步新增一份 `phaseN_*.md`，固定记录：用户现在能运行什么、关键代码改动、测试和评测结果、Demo 路径、已知边界、下一阶段原因，以及面试复盘重点。未完成的阶段不写成“已交付”。
