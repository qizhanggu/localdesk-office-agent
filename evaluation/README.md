# LocalDesk Evaluation

## 当前冻结产品评测 v2

这一层直接回答“LocalDesk 现在能否按预定规则完成关键产品行为”。18 条任务在运行前固定输入、期望状态或产物和确定性检查项，不因为失败临时换题。

```powershell
.\.venv\Scripts\python.exe evaluation\run_product_evaluation.py `
  --manifest evaluation\product_tasks_v2.json `
  --output evaluation\results\product_eval_v2.json
```

2026-08-10 最终全量重跑结果为 18/18。详细口径见 [产品评测报告 v2](../docs/product_eval_report_v2.md)。其中的 2.999 倍并行加速来自 40 ms 延迟夹具，不是公网速度；100% 证据支持率来自构造证据，不是真实资讯质量；本轮没有 LLM 调用，Token 和成本为 0，未开展真实用户修改统计。

第一版 `product_tasks_v1.json` / `product_eval_v1.json` 因研究覆盖比较器只统计配置角色而存在设计缺陷，保留用于实验追溯，不作为最终结果。

### 人工抽查记录

[human_review_protocol_v1.json](human_review_protocol_v1.json) 冻结了 10～20 张资讯卡片的抽查规则。脚本只负责生成空白表和统计真实填写结果，不代替人做判断：

```powershell
.\.venv\Scripts\python.exe evaluation\weekly_human_review.py export `
  --cards <TASK_DIR>\staging\news_cards.json `
  --output .localdesk\human-review\weekly-review.csv

.\.venv\Scripts\python.exe evaluation\weekly_human_review.py summarize `
  --review .localdesk\human-review\weekly-review.csv `
  --output .localdesk\human-review\weekly-review-summary.json
```

评审人只能填写 `keep`、`delete` 或 `modify`；已评审行必须填写评审人和 ISO 时间，`modify` 还必须提供不同的新摘要。没有真实填写时，人工删除/修改数保持 `null`。脚本只能校验记录格式，不能验证 `reviewer` 身份，因此正式报告还需要保存实际评审流程说明。

评测分为两层：

1. **回归基线**：`run_baseline.py` 离线运行稳定核心测试，并保存真实结果；它证明已有受控闭环没有回归。
2. **任务评估**：`evaluation_tasks.json` 记录逐阶段扩展的任务场景。只有具备对应可执行 adapter 与验收脚本后，才统计端到端任务成功率、引用有效率等指标。

运行 Phase 0 基线：

```powershell
python evaluation/run_baseline.py
```

默认结果写入 `evaluation/results/phase0_core_baseline.json`。该结果不会声称真实模型、浏览器或 Windows Desktop Computer Use 的效果；这些能力将在对应阶段有可复现脚本后再纳入指标。

## Phase 2：受控网页研究与确定性 Reviewer

```powershell
python evaluation/run_phase2_evaluation.py
```

该脚本运行 `tests/test_desktop_foundation.py` 与 `tests/test_desktop_reporting.py`，并将结果写入 `evaluation/results/phase2_controlled_research.json`。它使用 `FakeBrowserAdapter` 和 `httpx.MockTransport` 覆盖白名单、重定向、页面体积、网页脚本文本和 Reviewer 拒绝路径；不访问真实网站，也不把离线测试当作联网任务成功率。

## Phase 3：DOCX 交付与质量门

```powershell
python evaluation/run_phase3_evaluation.py
```

该结果记录 DOCX staging、结构检查、渲染检查编排和双产物交付预检的离线回归。它使用 `FakeDocxRenderer`，因此不会声称真实 PDF/PNG 渲染质量已经验收；真实 LibreOffice 渲染是单独、必须完成的阶段验收门槛。

真实渲染验收（仅使用构造资料）：

```powershell
python evaluation/run_phase3_real_render_demo.py
```

该脚本要求可用的 LibreOffice，实际运行 Markdown → DOCX → PDF → PNG → 确认交付，并保存 Trace、结构与页面数量摘要；它不使用或上传任何真实个人/公司资料。

## Phase 4：受控文件整理与独立回滚

```powershell
python evaluation/run_phase4_evaluation.py
```

该脚本覆盖 `managed_roots` 内的 dry-run、单独确认移动、预览后源文件/目标变化拒绝、失败 journal、独立 rollback Task 和真实 CLI 串联。结果写入 `evaluation/results/phase4_file_organization.json`。测试只创建临时的无敏感样例文件；它不代表项目可以管理任意本机目录。

## Phase 5：Windows UIA 与受限视觉 fallback

```powershell
.\.venv\Scripts\python.exe evaluation\run_phase5_evaluation.py
```

该脚本记录 UIA workflow 的离线回归：窗口白名单、确认绑定、状态变化时停止并人工接管，以及 state-bound fallback。真实验收使用仓库自建的 WinForms 测试窗口和构造文本完成，不访问外部系统；历史详情见 `docs/archive/development/phase5_desktop_computer_use.md`。

## Phase 6A：基线冻结、真实 Office Demo 与公网 Trace

```powershell
.\.venv\Scripts\python.exe evaluation\run_phase6a_evaluation.py
.\.venv\Scripts\python.exe evaluation\run_phase6a_demo.py
.\.venv\Scripts\python.exe evaluation\run_real_web_trace.py
```

第一条生成统一离线回归结果；第二条使用构造 JD/履历和真实 LibreOffice 验收求职材料 DOCX；第三条只读访问一个真实公开 HTTPS 页面，并在 Trace 中保存 URL、访问时间、内容哈希、引用片段和发现链接。三类证据分开记录，不能用离线 fake adapter 的通过率代替真实联网或真实渲染结果。

## Phase 7 B0+B1：公共 Benchmark 元数据

- `officebench/pilot_manifest.json` 固定 OfficeBench 官方 commit、2 条开发任务和 3 条冻结评测任务及其 SHA-256。
- `theagentcompany/task_shortlist.json` 保存 8 条产品相近任务的系统、产物、验证方式和能力缺口。
- 当前状态仅为任务盘点与可行性调研：没有 OfficeBench Adapter、没有运行官方任务、没有官方通过结果，也没有部署 TheAgentCompany。
- 3 条冻结评测任务只属于接入可行性 Pilot，不能作为完整 Benchmark 成绩或简历指标。

## Phase 7 B2A：离线 OfficeBench Adapter

生成固定 commit 的 300 条任务静态统计：

```powershell
.\.venv\Scripts\python.exe -m evaluation.officebench.analyze_tasks `
  --snapshot .localdesk\benchmark-sources\OfficeBench
```

执行 Dev `1-16/0` dry-run：

```powershell
.\.venv\Scripts\python.exe -m evaluation.officebench.adapter `
  --snapshot .localdesk\benchmark-sources\OfficeBench `
  --manifest evaluation\officebench\pilot_manifest.json `
  --run-root .localdesk\benchmark-runs `
  --output evaluation\officebench\results\dev_1-16_0_dry_run.json
```

dry-run 只校验 commit、任务哈希、字段转换、目录约定和官方环境可用性；不会创建运行目录、调用 Runtime/模型或执行官方 Evaluator。`tests/test_officebench_adapter.py` 使用自建 fixture 验证 Adapter 契约，不能解释为 OfficeBench 任务通过。

## Final Sprint 1：Excel/CSV 产品工具

`SpreadsheetSkill` 和 `SpreadsheetWorkflow` 提供授权目录内的 CSV/XLSX 读取、筛选、稳定排序、去重、列更新、staging、哈希复核、确定性输出校验和确认交付。它是通用产品能力，不依赖 OfficeBench。

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_spreadsheet.py -q
```

详细的用户能力、测试与 Docker/WSL2 历史环境状态见 [`docs/archive/development/phase7_sprint1_excel_environment.md`](../docs/archive/development/phase7_sprint1_excel_environment.md)。
