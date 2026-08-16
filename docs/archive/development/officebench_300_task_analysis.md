# OfficeBench 300 条任务静态目录分析

> 数据源：[OfficeBench@b978b808](https://github.com/zlwang-cs/OfficeBench/tree/b978b808667c32b52ce19a67ce1def1de9ae02b7)
> 分析类型：固定 commit 的完全离线静态分析。应用、操作和链路是规则推断，不是真实 Agent 工具调用 Trace；LocalDesk 覆盖是保守组件映射，不是 Benchmark 成绩。

## 1. 数据完整性

| 任务层级 | 官方任务数 | 本次读到 |
|---|---:|---:|
| 单应用 | 93 | 93 |
| 双应用 | 95 | 95 |
| 三应用 | 112 | 112 |
| 合计 | 300 | 300 |

任务数来自 task ID 前缀，是官方确定数据。输入类型来自 Git tree 中的 `testbed`；输出类型来自 Evaluator 参数和明确的输出型任务措辞。

## 2. 推断应用频率

| 项目 | 任务出现次数 |
|---|---:|
| `excel` | 168 |
| `pdf` | 109 |
| `word` | 88 |
| `email` | 80 |
| `ocr` | 79 |
| `calendar` | 62 |
| `shell` | 35 |
| `llm` | 29 |

## 3. 推断操作频率

| 项目 | 任务出现次数 |
|---|---:|
| `excel.read_file` | 129 |
| `excel.create_or_update_file` | 91 |
| `shell.command` | 87 |
| `word.create_or_update_file` | 80 |
| `ocr.recognize_file` | 79 |
| `pdf.read_file` | 60 |
| `email.send_email` | 54 |
| `calendar.create_event` | 46 |
| `llm.complete_text` | 29 |
| `email.read_email` | 29 |
| `pdf.create_or_transform` | 23 |
| `calendar.list_events` | 22 |
| `pdf.convert_to_image` | 21 |
| `word.read_file` | 16 |
| `excel.convert_to_pdf` | 10 |
| `word.convert_to_pdf` | 6 |

同一任务可能出现多个应用和多个操作，因此频率之和会超过 300。`create_or_update_file` 是静态分析归一名，不是新增 LocalDesk 产品工具。

## 4. 输入文件与输出产物

### 输入文件类型

| 项目 | 任务出现次数 |
|---|---:|
| `.xlsx` | 129 |
| `.pdf` | 60 |
| `.jpg` | 57 |
| `.eml` | 29 |
| `.ics` | 22 |
| `.png` | 22 |
| `.docx` | 16 |
| `.txt` | 5 |

### 输出产物类型

| 项目 | 任务出现次数 |
|---|---:|
| `.xlsx` | 91 |
| `.docx` | 80 |
| `.txt` | 55 |
| `.eml` | 54 |
| `.ics` | 46 |
| `.pdf` | 39 |
| `.jpg` | 20 |
| `.png` | 1 |

用于验证优先级的组合出现量（输入出现次数 + 输出出现次数）：

- Excel/CSV：**220**
- DOCX/PDF：**195**
- EML/邮件产物：**83**

这三个数字衡量“有多少任务组涉及该类文件”，不是文件总数，也不是成功率。根据全量静态数据，Excel/CSV 与 DOCX/PDF 确实是高频办公边界；邮件也重复出现，但低于文档/表格，因此更适合先做可审计草稿产物而非真实账户发送。

## 5. Evaluator 类型

| 项目 | 任务出现次数 |
|---|---:|
| `evaluate_contain` | 279 |
| `evaluate_file_exist` | 233 |
| `evaluate_excel_cell_value` | 37 |
| `evaluate_not_contain` | 19 |
| `evaluate_exact_match` | 18 |
| `evaluate_calendar_no_overlap` | 6 |
| `evaluate_diff_contain_text` | 6 |
| `evaluate_file_not_exist` | 2 |
| `evaluate_excel_cell_comparator` | 1 |

OfficeBench 的主判定以文件存在、内容包含、精确匹配和 Excel 单元格值等确定性检查为主。后续 Adapter 应原样调用，不用 LocalDesk 自建判断替代。

## 6. 高频静态跨应用链路

| 项目 | 任务出现次数 |
|---|---:|
| `excel -> excel` | 42 |
| `excel -> word` | 21 |
| `excel -> text` | 16 |
| `ocr -> excel` | 11 |
| `pdf -> word` | 10 |
| `email -> text` | 10 |
| `ocr -> text` | 7 |
| `ocr -> email` | 7 |
| `ocr -> pdf` | 6 |
| `excel -> calendar` | 6 |
| `excel -> email+word` | 6 |
| `no_file_input -> calendar` | 5 |
| `pdf -> text` | 5 |
| `email -> excel` | 5 |
| `excel -> calendar+email` | 5 |
| `pdf -> ocr` | 4 |
| `ocr+pdf -> text` | 4 |
| `email -> pdf` | 4 |
| `calendar -> email` | 4 |
| `ocr -> email+excel` | 4 |
| `excel -> excel+word` | 4 |
| `text+word -> word` | 3 |
| `calendar -> calendar` | 3 |
| `email -> email+text` | 3 |
| `pdf -> calendar` | 3 |

链路按“测试床输入应用集合 → Evaluator/任务要求的输出应用集合”归一；它不能表示真实执行顺序，但可以显示高频信息流向。

## 7. LocalDesk 保守覆盖

| 项目 | 任务出现次数 |
|---|---:|
| `unsupported` | 183 |
| `partial` | 107 |
| `near_reusable_not_verified` | 10 |

覆盖规则只承认当前真实能力：

- 可读输入：TXT、Markdown、PDF；
- 可生成正式办公产物：Markdown、DOCX；
- 已有横切能力：Runtime、Policy、staging、Trace、确认与文件移动；
- 不把内部 DOCX 渲染 PDF 当作正式 PDF 产品工具；
- 不把通用 Coding `Bash` 当作 Desktop 产品能力；
- Excel/CSV、邮件、日历、OCR、DOCX 读取均按缺失处理。

因此 `near_reusable_not_verified` 也只表示组件接近，仍然没有 OfficeBench 官方运行结果。

## 8. 数据驱动的优先顺序

1. **Excel/CSV 结构化读写**：表格输入/输出和 Excel Evaluator 均高频，而且 LocalDesk 当前完全缺失，是最明显的通用缺口。
2. **DOCX/PDF 输入与正式转换**：已有 DOCX 生成和渲染基础，补读取/正式 PDF 交付可以复用较多现有代码。
3. **`.eml` 邮件草稿**：任务中反复出现，但应先生成标准草稿和附件，执行真实发送仍需独立确认。
4. **日历/ICS 与 OCR**：有稳定重复需求，但优先级应由频次和前述三项完成后的边际收益决定。

## 9. 真实性边界

- 本报告没有运行 Docker、模型或任何 OfficeBench 任务；
- 没有调用官方 Evaluator；
- 没有运行 3 条冻结 Eval；
- 频率来自静态目录、任务 JSON、Evaluator 配置和确定性规则；
- 机器可读明细位于 `evaluation/officebench/results/task_static_analysis.json` 和 `task_catalog.csv`。
