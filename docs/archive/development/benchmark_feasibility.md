# Phase 7 B0+B1：公共 Benchmark 可行性调研

> 状态：B0+B1 已完成；B2 尚未获批、未实施。
> 调研日期：2026-07-23。所有判断绑定到官方 commit 和任务文件哈希，不代表已经跑通公共 Benchmark。

## 1. 结论先行

1. **OfficeBench 适合作为近期主 Benchmark，但当前 Windows 环境还不能直接运行官方链路。** 官方入口会构建 Linux Docker 镜像；本机当前 Python 为 3.11.9，命令行未发现 Docker，而官方 README 推荐 Python 3.10。
2. **LocalDesk 当前对 5 条代表任务的官方通过数是“未测”，不是 0/5，也不是已覆盖。** 其中 2 条具有较高组件复用度，但缺少 OfficeBench Adapter、测试床文件映射和官方 Evaluator 实跑证据。
3. **最高优先级的通用缺口是结构化表格读写。** Excel/CSV 在两个 Benchmark 的办公任务中反复出现，比继续扩建任意 GUI、Role Agent 或更多安全抽象更值得。
4. **TheAgentCompany 更适合作为后续产品叙事验证，不适合作为近期主 Benchmark。** 它与“数字实习生”定位高度一致，但 175 个任务依赖 GitLab、Plane、ownCloud、RocketChat、Docker 和 30GB+ 磁盘，当前接入成本显著高于 OfficeBench。
5. **产品定位成立，但需要收窄表述。** 推荐定位为：
   “一个可审计的数字实习生 Runtime，在用户授权范围内，跨本地资料、公开网页、文件和办公产物完成中等长度的临时工作任务；对外发送、覆盖和删除等高风险动作保留确认与 Trace。”

## 2. B0：官方格式与运行链路

### 2.1 OfficeBench

- 固定版本：[OfficeBench@b978b80](https://github.com/zlwang-cs/OfficeBench/tree/b978b808667c32b52ce19a67ce1def1de9ae02b7)。
- 官方任务共 300 条：单应用 93、双应用 95、三应用 112。
- 每条任务位于 `tasks/{task_id}/subtasks/{subtask_id}.json`，包含 `username/date/time/task/evaluation`。`evaluation` 是确定性函数及参数列表。
- Agent 入口 `agent_interact.py` 会构建 Docker、准备测试床、循环调用 Policy 生成结构化 action，再由 `OfficeAgentEnv.step()` 执行。
- 应用操作是 OfficeBench 自己的模拟接口，如 `excel.read_file`、`word.read_file`、`pdf.read_file`、`email.send_email`；它们不是 Windows Office COM/UIA 接口。
- 官方 `evaluation.py` 在每个任务输出目录中调用 `evaluate_contain`、`evaluate_file_exist`、`evaluate_exact_match`、Excel 单元格比较、日历冲突等函数，写出 `{task_id, subtask_id, is_pass}` JSONL，并汇总单/双/三应用通过率。
- Dockerfile 基于 `ubuntu:latest`，安装 LibreOffice、Tesseract、Python 与文档/表格依赖，并在镜像内初始化 Git 以比较文件变化。

### 2.2 TheAgentCompany

- 固定版本：[TheAgentCompany@98b68ef](https://github.com/TheAgentCompany/TheAgentCompany/tree/98b68ef82a47690c316f42fddb05baafaab56851)。
- 官方 1.0.0 包含 175 个任务镜像。每个任务提供 `/instruction/task.md`、依赖服务、初始化脚本和加密的结果 Evaluator。
- 环境服务包括 GitLab、Plane、ownCloud 和 RocketChat；官方 Windows 说明要求 Docker、host networking 和 30GB+ 可用空间。
- 评分以最终系统状态/产物为主，同时提供 checkpoint 部分分；既有确定性 Evaluator，也有 LLM Evaluator 和由 LLM 驱动的同事 NPC。
- 本轮只稀疏读取约 0.84 MB 文本元数据，没有安装 Docker、拉取镜像或运行服务。

## 3. B1：OfficeBench 代表任务与能力映射

完整 split、官方 commit 和 SHA-256 见 [`evaluation/officebench/pilot_manifest.json`](../../../evaluation/officebench/pilot_manifest.json)。

| Split | 官方任务 | 要求与产物 | 官方成功判定 | LocalDesk 可复用 | 主要缺口 | 接入判断 |
|---|---|---|---|---|---|---|
| Dev | `1-16/0` | TXT → `random_paragraph.docx` | 文件存在 + DOCX 包含指定正文 | TXT 检索、Markdown/DOCX 生成、结构/渲染检查、Trace | OfficeBench 路径桥接；当前生成器偏“报告”结构 | 低难度，适合作为 Adapter 冒烟任务 |
| Dev | `2-38/0` | PDF → `notification.eml` | Alice 邮箱中邮件包含日期、地点等关键词 | PDF 文本提取、确定性内容检查、风险分级 | `.eml` 生成、附件/收件人模型、对外发送确认语义 | 中等；用于发现通用邮件边界，不进入冻结评测 |
| Eval | `1-11/0` | Excel 排序 → `sorted_score.xlsx` | 与参考 XLSX 精确匹配 | Runtime、Policy、Trace、文件交付 | Excel 读写与稳定排序、工作簿保真 | 中高；暴露高价值通用能力缺口 |
| Eval | `2-26/1` | PDF 文本 → `market_analysis.docx` | DOCX 包含 7 个关键词 | PDF 提取、DOCX 生成和质量检查 | Adapter、任意正文的 DOCX 模式、测试床映射 | 低到中；最可能复用现有闭环 |
| Eval | `3-3/0` | DOCX → PDF → Alice 邮件 | PDF 存在且含关键词，邮件含关键词 | DOCX 渲染链、风险分级、Trace | DOCX 内容读取、正式 PDF 产物、`.eml`/附件交付 | 中高；能检验跨产物流转而非单点生成 |

这里的“可复用”只是代码组件判断：

- 官方通过数：**未测**；
- 端到端官方验证覆盖：**0/5 已验证**；
- 预计较高复用度：`1-16/0`、`2-26/1` 两条；
- 其余三条均缺少至少一个关键产品工具，不能用 Runtime/Trace 已存在来代替任务完成。

### 数据隔离与实验纪律

- 2 条 Dev 任务可用于调试 Adapter；3 条 Eval 任务已经按单/双/三应用冻结。
- 3 条 Eval 仅是 **OfficeBench 接入可行性 Pilot**，样本太小，不能称为完整 Benchmark 成绩，也不能直接写入简历。
- Eval 首次运行后不得因语义失败修改 Prompt、Policy、策略或业务规则。
- 只允许修复坐标转换、参数/路径映射、Adapter 或 Evaluator 调用等机械性 Bug；每次必须记录根因、升级实验版本、恢复初始状态并从头重跑全部 3 条。

## 4. Windows 环境可行性

| 项目 | 本机实测/官方要求 | 判断 |
|---|---|---|
| Python | 当时隔离解释器为 3.11.9；OfficeBench 推荐 3.10 | 不建议污染现有环境；若进 B2，建立隔离 3.10 环境 |
| Docker | `docker` / `docker-compose` 命令未发现 | 当前不能运行官方容器链路 |
| D 盘 | 总计 276.83 GB，可用 127.23 GB | 空间满足后续小规模 Spike，但下载前仍需确认 |
| OfficeBench 源元数据 | 稀疏展开约 0.33 MB | 已完成，不含任务大文件和镜像 |
| OfficeBench 镜像 | 官方未公布体积；Dockerfile 含 Ubuntu、LibreOffice、Tesseract、科学计算和文档库 | 只能先估为 **2–5 GB 级**，这是工程估算而非实测；B2 前应先做 layer 体积预估/限额 |
| TheAgentCompany | 官方要求 30GB+，本轮仅约 0.84 MB 元数据 | 本轮明确不部署 |

因此，“能否在当前 Windows 环境运行”的准确答案是：**架构上可以通过 Docker Desktop 的 Linux container 尝试，但当前机器未安装/暴露 Docker，本轮也未获准安装，所以尚未验证可运行。**

## 5. TheAgentCompany 相近任务

机器可读清单见 [`evaluation/theagentcompany/task_shortlist.json`](../../../evaluation/theagentcompany/task_shortlist.json)。

| 任务 | 系统与产物 | 官方验证 | 当前覆盖与缺口 | 是否值得 |
|---|---|---|---|---|
| `admin-arrange-meeting-rooms` | 本地计算 + `ans.txt` + RocketChat | 文件内容、聊天记录 | 可完成计算/文件；缺 RocketChat 与外发确认 | 值得，短而完整 |
| `admin-check-employees-budget-and-reply-and-record` | RocketChat + ownCloud PDF + `result.txt` | 访问、聊天、语义和文件 checkpoints | 本地 PDF/计算可复用；缺登录系统和多轮同事交互 | 很符合定位，但环境重 |
| `admin-employee-info-reconciliation` | CSV + RocketChat → 更新 CSV | 精确 CSV 值、联系人数量 | 缺 CSV 编辑和聊天连接器 | 值得，通用性高 |
| `admin-get-best-vendor-quote` | 聊天、PDF、CSV、云上传、分享链接 | 聊天、云文件、链接、CSV | 缺 ownCloud/聊天/CSV/公开分享策略 | 产品价值高，接入成本高 |
| `admin-make-spreadsheet` | ownCloud PDF → CSV | 确定性类别和计数 | PDF 可读；缺 ownCloud 与 CSV 编辑 | 很值得，适合验证表格能力 |
| `admin-read-survey-and-summarise` | ownCloud PDF → RocketChat | 聊天内容确定性检查 | 检索/总结可复用；缺登录和聊天 | 值得，典型“收集后交付” |
| `admin-remove-pages-pdf` | ownCloud PDF → 缩短 PDF | 存在、页数、逐页文本 | 缺 PDF 页编辑和 ownCloud | 值得，Evaluator 清晰 |
| `finance-invoice-matching` | ownCloud Excel + 多个 PDF → XLSX | 表头、问题项、精确总额 | 缺 Excel/ownCloud/结构化发票抽取 | 很符合数字实习生，但应后置 |

## 6. 下一批通用能力与不值得做的补丁

按公共任务重复频率和产品价值排序：

1. **Excel/CSV Tool**：结构化读取、筛选、排序、公式/值写入、新文件生成和确定性校验；优先 API/CLI，不先做 Excel GUI。
2. **通用 Office 输入/转换**：读取 DOCX、把已验证的 DOCX/PDF 作为正式产物，而不只把 PDF 当渲染中间件。
3. **Benchmark I/O Adapter**：只负责加载官方任务、映射隔离工作目录、调用现有 Runtime、保存 Trace 和原样调用官方 Evaluator。
4. **邮件草稿产物**：先支持标准 `.eml` 草稿和附件，生成可自动、发送必须确认；不要在本阶段接真实账户。
5. **后续才考虑登录系统 Connector**：ownCloud/RocketChat 只有在 TheAgentCompany 成为主方向后再做。

不值得实现：

- 为每个 OfficeBench action 复制一套 LocalDesk 工具或重写 Runtime；
- 针对 5 条任务写固定文件名、关键词、答案或特殊 Prompt；
- 为 Linux 模拟环境引入坐标点击/视觉 Agent，结构化接口更稳定；
- 为追求分数实现 OfficeBench 私有日历/邮件格式怪癖，却没有真实产品场景；
- 现在就部署 TheAgentCompany 全套服务，或同步开发 PPT、任意 GUI、搜索引擎和多个 Connector。

## 7. 主 Benchmark、产品定位与暂停点

- **推荐主 Benchmark：OfficeBench。** 原因是任务规模明确、单/双/三应用分层、确定性 Evaluator 较多，且能用最薄 Adapter 检验 LocalDesk 的规划和产物流转。
- **TheAgentCompany：后续补充 Benchmark。** 它更能支撑“数字实习生”叙事，但环境和外部系统成本高，现阶段只用任务分布校准产品路线。
- **自建安全评测继续保留。** 权限、确认、敏感字段、rollback、窗口变化接管、Trace 和 DOCX 真实渲染不是公共 Benchmark 的替代项，也不能被公共分数替代。
- **当前暂停点：B0+B1。** 未进入 B2；未安装 Docker；未下载大型镜像；未运行官方任务；未产生任何公共 Benchmark 成绩。

若获批进入 B2，最小范围应只有：读取 2 条 Dev 任务、隔离工作目录映射、LocalDesk 调用桥、官方 Evaluator 原样调用和结果/Trace 保存。先证明 `1-16/0` 的 Dev 冒烟链路，再决定是否准备冻结 Eval 的一次性运行。
