# LocalDesk 托管冲刺交接（2026-08-10）

## 五分钟大白话

冲刺前，LocalDesk 已经能生成周报和报销文件，Runtime 也比较完整，但周报的资讯、摘要和价值判断主要是预置内容；用户自然语言还不能统一进入产品；评测也没有把这些能力放进同一套冻结任务。

冲刺后，系统增加了一层很薄的 Main Agent，把自然语言映射到短计划和既有 Workflow；周报可以从冻结官方 RSS/网页发现资讯并保存证据，失败时不会换成预置答案；周报和报销都改成“一次确认、三份产物、交付前复核”；同时建立 18 条冻结产品评测和面试讲解材料。

仍然没有真实 LLM Research Agent、开放式 Deep Research、持续追踪、任意 GUI 或自动发邮件。

## Before / After

```text
Before
用户 -> 固定 Demo -> 预置资讯/确定性核对 -> Office 文件

After
用户 -> Thin Main Agent -> 短计划 -> 周报/报销 Workflow
     -> Controlled Runtime -> Approval -> Verification -> Artifact + Trace
```

周报内部从“预置卡片并发处理”变成：

```text
冻结 RSS/时间窗/规则
-> 三路职责发现
-> URL/引用/访问时间/内容哈希
-> Editor + Memory
-> 证据 Reviewer
-> PPTX/PDF/EML
-> 人工确认与 Trace
```

## 关键设计决策

1. Main Agent 保持极薄：当前真实问题是办公链路，不是长链规划；代价是只支持周报和报销两种 intent。
2. 正文失败允许官方 RSS 摘要回退：比“全部失败”更实用，但必须明确区分 RSS 证据和正文证据。
3. Editor 用保守事件指纹而非 embedding：零 API 成本、可解释；代价是复杂改写仍可能漏合并。
4. 先冻结 18 条确定性任务：避免把时间花在大而全评分器；语义质量仍需人工抽查。
5. 多产物先统一预检再交付：能发现确认后的篡改；但不是跨文件系统事务，极端磁盘故障仍可能部分交付。

## 真实验证

| 层级 | 实际执行 | 结果 | 能证明什么 | 不能证明什么 |
|---|---|---|---|---|
| 静态检查 | `compileall`、`git diff --check` | 通过 | Python 语法、补丁格式 | 真实业务行为 |
| 核心测试 | 周报、Research、Main Agent、报销、Runtime 基础 | 33/33；最终组合 18/18 | 本轮相关逻辑没有回归 | 外部网络与 Office 稳定性 |
| 冻结评测 | `product_tasks_v2.json` | 18/18；受控并行 2.999× | 固定工程行为和相对延迟 | 公网速度、用户成功率 |
| 完整测试 | 全仓库 pytest | 636 通过、3 跳过、9 失败；其中 1 个临时文件失败单独重跑通过 | 本轮没有新增稳定失败 | 8 个历史失败仍未解决 |
| 真实周报 | 官方 RSS + Office | 1 次成功交付；1 次 TLS 超时诚实失败 | 真实公开来源读取与完整交付 | 稳定联网成功率 |
| 真实报销 | LibreOffice + 合成材料 | Main Agent 路由后成功交付 3 份产物 | 辅助 Demo 可端到端运行 | 复杂自然语言规则与 OCR |
| 视觉检查 | 成功周报 6 张渲染图 | 无溢出；发现页码总数写成 5 | 真实渲染能暴露结构检查看不到的问题 | 修复后本机 Office 会话暂时无法再次渲染 |

## 最有价值的失败历史

- 首版评测只数“配置了几个角色”，没有数“实际产出了几类卡片”。修正比较器、版本升级为 v2，并全量重跑。
- 成功联网任务的卡片明细写着 RSS 回退，但汇总 Trace 笼统写成正文模式。代码改为记录实际 mode、正文成功数和 RSS 回退数；历史 Trace 不篡改。
- 修正 Trace 后正式重跑遇到 TLS 握手超时。系统三次尝试后失败，证据保留，没有使用离线答案。
- 视觉检查发现 6 页 PPT 的页脚写成 `/5`。已修成动态 `cards.length + 3`，并从新 PPTX 内部确认页码为 2/6 至 6/6；当前 Office 会话启动失败，未获得修复后的新 PNG。

## 建议阅读顺序

1. `localdesk/desktop/main_agent.py`：先看任务怎样进入系统。
2. `localdesk/desktop/weekly_research.py`：看来源、证据和失败规则。
3. `localdesk/desktop/weekly_briefing.py`：看 Editor、Memory、Reviewer 和 Office 闭环。
4. `localdesk/desktop/artifact_bundle.py`：看确认、哈希复核和正式交付。
5. `evaluation/run_product_evaluation.py`：看指标是怎么真实算出来的。

## 下一步最值得做的实验

人审表导出与统计工具已经补齐，但目前只有 3 张真实卡片且没有用户填写，因此人工指标仍为 `null`。下一步应先累计并真实评审 10～20 张资讯卡片，记录删除、修改、误合并和漏合并。若有可用 LLM API 和预算，再固定同一证据集对比 1～2 个模型的有证据摘要质量、Token、成本和延迟。
