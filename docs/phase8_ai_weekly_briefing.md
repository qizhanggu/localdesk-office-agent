# Phase 8：AI 资讯周报 Hero Demo

## 用户现在能做什么

用户可以让 LocalDesk 在冻结时间窗内读取白名单官方 RSS/网页，整理“大模型、Agent 产品、产业应用”三类资讯，生成可编辑 PPTX、PDF、逐页渲染图、人工确认页和未发送邮件草稿。所有正式产物先留在 staging，Reviewer 通过后才进入人工确认；确认时重新检查路径、SHA-256 和文件结构，再一次性交付三份文件。

## 真实研究链路

运行前冻结 [来源配置 v3](../evaluation/frozen_weekly_sources_v3.json)，每个研究职责保存自己的来源、关键词、时间窗和步骤。系统会：

1. 读取官方 RSS，并保存 URL、访问时间和原始内容哈希；
2. 按冻结时间窗和关键词筛选；
3. 尝试读取官方正文；
4. 正文失败时，仅在官方 RSS 自带足够摘要的情况下回退，并标记 `official_rss_item_fallback`；
5. 任一方向没有合格结果时，整个研究任务失败并保留证据，不改来源、不套预置答案。

三路研究是确定性并发职责模块，不是三个调用 LLM 的 Agent。摘要来自原始证据的确定性截取，当前没有模型 Token 和成本。

## Editor、Memory 和 Reviewer

- Editor：用保守事件指纹、标题相似度和 URL 合并跨来源标题变体，再按证据状态、日期和反馈偏好选择；不是通用语义去重。
- Memory：保存 `card_id`、事件指纹、历史 URL、用户 keep/delete 反馈和分类偏好，用于跨周过滤；尚未实现定时“持续追踪”。
- Reviewer：保留时间窗、HTTPS、字段、三类覆盖、PPTX/PDF 结构和逐页渲染检查；新增引用片段、访问时间、内容哈希，以及标题/摘要能否在证据中找到的确定性检查。它不是完整事实核查器。

## 真实运行证据

2026-08-10 的成功任务 `32c52de1-bee6-496e-a46b-e0eac4527c50`：

- 真实读取 `https://openai.com/news/rss.xml`，访问时间为 `2026-08-10T06:55:59.402886+00:00`，内容哈希为 `ca28c410...d709990`；
- 三个方向各选择 1 条资讯，三张卡片都保存发布日期、文章 URL、引用片段、访问时间、内容哈希和来源模式；
- 三个正文页均返回 403，因此三张卡片都明确标记为 `official_rss_item_fallback`，没有冒充原文读取成功；
- Reviewer 通过，生成 6 页 PPT/PDF 和 6 张逐页渲染图；
- 人工确认后任务状态为 `succeeded`，正式交付 PPTX、PDF 和未发送 EML 草稿。

本地证据位于 Git 忽略目录：

`.localdesk/weekly-live-v3-final-20260810`

可提交的审计摘要见 [live_weekly_hero_v3_audit.json](../evaluation/results/live_weekly_hero_v3_audit.json)。

随后发现汇总 Trace 把这次运行笼统写成了 `official_rss_plus_live_html`，与明细中的三个 RSS 回退不一致。代码已修正为分别记录 `live_html_count`、`rss_fallback_count` 和实际 `source_modes`。修正后的一次重跑遇到 RSS TLS 握手超时，任务按设计失败并保留三次尝试的错误，没有回退到离线预置数据。这个失败任务为 `6026002d-dc7c-453f-b055-fb1b340c97a5`。

## 运行方式

真实来源版：

```powershell
.\.venv\Scripts\python.exe -m localdesk.desktop.weekly_briefing_live_demo `
  --root .localdesk\weekly-live `
  --start 2026-07-20 `
  --end 2026-08-10
```

命令输出 `task_id`。检查确认页、PPTX、PDF 后执行：

```powershell
.\.venv\Scripts\python.exe -m localdesk.desktop.weekly_briefing_live_demo `
  --root .localdesk\weekly-live `
  --confirm <TASK_ID>
```

离线回退版：

```powershell
.\.venv\Scripts\python.exe -m localdesk.desktop.weekly_briefing_demo --root .localdesk\weekly-offline
```

离线版始终标记为 `manual_public_snapshot`，不能作为实时研究证据。

## 当前没有做的事

- 没有 Deep Research、开放搜索或复杂多 Agent 框架；
- 没有真实 LLM 摘要或价值判断；
- 没有自动发送邮件；
- 没有把一次联网成功说成稳定成功率；
- 没有完整结论—证据语义事实核查。
