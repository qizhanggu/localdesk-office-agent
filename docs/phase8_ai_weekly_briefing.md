# Phase 8：AI 资讯周报 PPT

## 已完成的真实闭环

LocalDesk 可以创建一项“本周 AI 资讯汇报”Runtime 任务，三个职责隔离的研究模块并发处理“大模型研究、Agent 产品、产业应用”三类来源；编辑器按发布时间排序、按标题去重，并用历史记忆过滤已出现的卡片。输出先留在任务 staging，交付动作停在 `awaiting_confirmation`，不会自动把 PPT、PDF 或邮件发送到外部。

每张资讯卡片包含标题、发布日期、来源 URL、摘要和价值判断。Trace 保存研究职责、编辑选择、来源 URL、访问时间、内容哈希与引用片段。第一版的三个研究模块是确定性职责模块，不宣称调用了三个 LLM 或实现了开放式网页搜索。

## 2026-07-20 至 2026-07-26 演示

最终成功任务：`069f7e95-bc59-4e66-9cc0-d13674a80b52`，产物位于被 Git 忽略的本地 staging：

- `本周AI资讯汇报.pptx`：5 页、可编辑的蓝色企业风格 PPTX；
- `本周AI资讯汇报.pdf`：通过独立 Microsoft PowerPoint COM 实例导出；
- `ppt_render/slide-*.png`：PDF 逐页渲染检查图；
- `AI资讯周报_未发送草稿.eml`：包含 PPTX 和 PDF 两个附件的 RFC 兼容本地草稿；
- `人工确认页面.html`、`news_cards.json`、`source_reads.json`、`review.json` 与 `events.jsonl`。

来源均为公开 Microsoft Blog 页面：

1. [Powering America's Genesis Mission](https://blogs.microsoft.com/blog/2026/07/22/powering-americas-genesis-mission-microsofts-commitment-to-scientific-discovery/)；
2. [Microsoft expands Azure AI and HPC infrastructure with AMD](https://blogs.microsoft.com/blog/2026/07/20/microsoft-expands-azure-ai-and-hpc-infrastructure-with-amd/)。

本机直连 HTTPS 在本次运行中分别出现 403 和 TLS EOF，因此最终演示使用了明确标记为 `manual_public_snapshot` 的公开来源快照；Trace 不把它说成实时抓取成功。正常产品路径仍保留 `HttpBrowserAdapter`，网络条件正常时会将实时只读网页结果写入同一份 Trace schema。

## Reviewer 与 Memory

Reviewer 阻断：日期超出范围、非 HTTPS 来源、空摘要或价值判断、重复标题、少于三个方向、PPTX/PDF 缺失或过小、PPTX 结构检查失败。PPTX 还经 PDF 逐页 PNG 渲染并人工查看；最终版本已消除正文末尾异常换行。

`weekly_briefing_memory.json` 保存已选卡片和用户保留/删除反馈。对同一数据第二次运行时，编辑器过滤掉全部已见卡片，Reviewer 因少于三个方向拒绝交付；这证明 Memory 实际影响选择，而不是仅写入一个无用日志。

## 运行与边界

运行：

```powershell
.\.venv\Scripts\python.exe -m localdesk.desktop.weekly_briefing_demo
```

该命令只产生本地 staging 产物，不发送邮件、不使用华为内部资料、不登录网站，也不进行开放式网络搜索。当前 PDF 导出依赖本机已安装的 Microsoft PowerPoint；若不可用，任务应明确失败而不是伪造 PDF。
