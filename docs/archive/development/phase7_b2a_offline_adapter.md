# Phase 7 B2A：离线 Benchmark Adapter 基础

> 状态：已完成并暂停；没有进入 B2B。
> 真实性边界：没有安装 Docker、下载 OfficeBench 镜像、调用模型、运行官方 Evaluator 或触碰 3 条冻结 Eval。

## 1. 本阶段解决了什么

B2A 解决的是“我们能否在不执行 Benchmark 的前提下，把官方任务可靠地装进 LocalDesk 的评测入口”，不是增加新的 Office 产品功能。

本阶段完成：

1. 对固定 commit `b978b808667c32b52ce19a67ce1def1de9ae02b7` 下的全部 300 条任务做静态目录分析；
2. 生成逐任务 CSV、完整 JSON 和 Markdown 统计报告；
3. 为 Dev `1-16/0` 建立最薄离线 Adapter；
4. 用自建 fixture 验证 Adapter 契约；
5. 对真实固定快照执行纯 dry-run，确认当前官方环境明确处于 blocked，而不是伪造运行结果。

## 2. 300 条任务统计结论

任务数量校验：

| 层级 | 数量 |
|---|---:|
| 单应用 | 93 |
| 双应用 | 95 |
| 三应用 | 112 |
| 合计 | 300 |

关键静态频率：

| 维度 | 输入任务数 | 输出任务数 | 合计出现量 |
|---|---:|---:|---:|
| Excel/CSV | 129 | 91 | 220 |
| DOCX/PDF | 76 | 119 | 195 |
| EML/邮件 | 29 | 54 | 83 |

应用推断频率前五位为：

- Excel：168；
- PDF：109；
- Word：88；
- Email：80；
- OCR：79。

操作推断频率前五位为：

- `excel.read_file`：129；
- `excel.create_or_update_file`：91；
- `shell.command`：87；
- `word.create_or_update_file`：80；
- `ocr.recognize_file`：79。

Evaluator 频率：

- `evaluate_contain`：279；
- `evaluate_file_exist`：233；
- `evaluate_excel_cell_value`：37；
- `evaluate_not_contain`：19；
- `evaluate_exact_match`：18；
- 其余日历冲突、差异文本、文件不存在和 Excel comparator 合计 15。

高频跨应用信息流包括：

- Excel → Excel：42；
- Excel → Word：21；
- Excel → Text：16；
- OCR → Excel：11；
- PDF → Word：10；
- Email → Text：10。

结论：之前提出的三项能力方向得到了数据支持，但优先级应明确为：

1. Excel/CSV 结构化读写；
2. DOCX/PDF 读取与正式转换；
3. `.eml` 邮件草稿和附件。

其中邮件先做“可审计草稿”，不应直接扩展到真实账户自动发送。

详细方法、规则边界和完整表格见 [`officebench_300_task_analysis.md`](officebench_300_task_analysis.md)。机器可读结果见：

- [`task_static_analysis.json`](../../../evaluation/officebench/results/task_static_analysis.json)；
- [`task_catalog.csv`](../../../evaluation/officebench/results/task_catalog.csv)。

应用、操作和链路是根据官方 Git tree、任务文本和 Evaluator 参数做的确定性静态推断，不是 Runtime 调用 Trace。一个任务可出现多个应用，因此应用频率总和超过 300 是正常现象。

## 3. Adapter 实际完成能力

新增 `evaluation.officebench.adapter`，仅允许 Dev `1-16/0`：

- 加载官方任务 JSON；
- 校验 manifest 中的 pinned commit；
- 校验任务 JSON SHA-256；
- 拒绝其他任务和路径逃逸；
- 为 `inputs/staging/artifacts/trace` 生成彼此隔离的目录约定；
- 转换为 `LocalDeskBenchmarkInput`；
- 暴露窄化的 `RuntimeBridge` Protocol，不绑定模型；
- 探测官方 Evaluator 源码、Docker 和 testbed 是否可用；
- dry-run 只返回计划和 blocked 原因，不创建任务目录、不调用 Runtime；
- local fixture bridge 写入带 `local_contract_test_not_officebench_result` 标记的 Trace。

当前 dry-run 结果：

```text
status = blocked_official_environment
blocked_reasons =
  - docker_command_not_found
  - official_testbed_inputs_not_materialized
runtime_called = false
filesystem_prepared = false
```

原始结果见 [`dev_1-16_0_dry_run.json`](../../../evaluation/officebench/results/dev_1-16_0_dry_run.json)。

## 4. 测试和验证

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_officebench_adapter.py `
  tests\test_desktop_foundation.py `
  tests\test_desktop_reporting.py `
  tests\test_job_materials.py `
  -q
```

结果：**45 passed**，其中 B2A Adapter 新增 **10 passed**。

新增测试覆盖：

- 错误 commit 拒绝；
- 错误任务哈希拒绝；
- task/subtask 路径逃逸拒绝；
- official snapshot 与运行目录重叠拒绝；
- input、staging、artifact 目录隔离；
- OfficeBench 字段到 LocalDesk 输入的转换；
- dry-run 不创建运行目录、不修改正式输出；
- Docker 不存在时返回明确 blocked reason；
- fixture bridge Trace 明确标记为 local contract test；
- 静态规则不会把 TXT 输入误判为输出。

这些测试不是 OfficeBench 官方通过结果。

## 5. Dev `1-16/0` 距离真实运行还缺什么

1. 安装并配置 Docker Desktop/Linux container，并确保数据和镜像放在 D 盘；
2. 获取固定 commit 中 `1-16` 的真实 testbed 文件，目前稀疏快照只展开了任务 JSON；
3. 构建或拉取 OfficeBench 官方环境并记录实际镜像体积；
4. 实现真正的 LocalDesk Runtime bridge，把 TXT 输入交给现有文档闭环；
5. 处理“任意正文 DOCX”与当前“结构化报告 DOCX”之间的模板差异；
6. 把产物映射回 OfficeBench 期望的 `data/random_paragraph.docx`；
7. 在容器初始状态中运行一次 Dev 任务，再原样调用官方 Evaluator；
8. 保存真实 Trace、产物、Evaluator JSONL、版本和成本。

目前上述步骤均未执行，因此不能说 Dev `1-16/0` 已运行或已通过。

## 6. 是否进入 B2B

仍建议进入 B2B，但范围应保持为：

- 只准备 OfficeBench Docker 环境和 `1-16/0` 所需 testbed；
- 所有大文件放 D 盘；
- 安装/下载前先确认预估体积和具体路径；
- 只跑 Dev，不运行冻结 Eval；
- 先验证官方 Evaluator 能否对一个人工构造的正确/错误产物给出稳定结果，再连接 Runtime；
- 不在 B2B 同时开发 Excel、EML 或 PDF 编辑。

若 Docker 环境构建明显超过预估或 Windows 兼容成本过高，应暂停并考虑 WSL2/D 盘虚拟磁盘或远程 Linux，而不是改写 OfficeBench Runtime。

## 7. 面试复盘重点

1. 为什么要把官方确定字段和静态推断字段分开，避免把目录分析冒充真实 Agent Trace；
2. 为什么 Benchmark Adapter 只负责数据/目录/结果桥接，不能反向污染产品 Runtime；
3. 为什么 local contract test、dry-run、官方 Evaluator 结果必须使用不同口径。
