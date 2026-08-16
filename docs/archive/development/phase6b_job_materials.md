# Phase 6B：定向求职材料纵向闭环（第一版）

**状态：第一版已完成（2026-07-22）**

## 本阶段解决的问题

项目第一次从“生成通用报告”转向真实用户任务：读取一个明确的公开岗位 JD，检索授权目录中的简历/项目材料，生成有来源的岗位匹配材料，并交付经过质量检查的 DOCX。

```text
指定 JD URL → 受控网页读取/链接发现 → 本地资料检索
            → 匹配与差距分析 → 用户反馈修订
            → Markdown + DOCX 结构/渲染检查
            → 新文件自动交付 → Trace/看板
```

## 关键实现

- `JobMaterialsWorkflow` 负责业务编排，继续复用既有 Workspace、Policy Guard、Registry、Reviewer、Document Skill、DOCX 质量门和 Trace。
- 输出包含岗位摘录、候选人证据、技能匹配/差距、面试表达建议、人工检查项和 Sources。
- `--desktop-feedback` 会把用户反馈应用到一个新版本；已有同名文件仍拒绝覆盖，用户需要显式给出新文件名。
- 第一版使用确定性模板，优点是可测试、不会编造经历；代价是语言润色能力有限，后续可在相同引用约束下接入 LLM Renderer。

## CLI 示例

```powershell
python -m localdesk --desktop `
  --desktop-task "Python Agent RAG 项目岗位匹配" `
  --desktop-job-materials `
  --desktop-company "示例公司" `
  --desktop-role "Agent 开发工程师" `
  --desktop-read-root "D:\your\materials" `
  --desktop-browser-domain "jobs.example.com" `
  --desktop-web-url "https://jobs.example.com/role" `
  --desktop-output-root "D:\your\application-output" `
  --desktop-task-root "D:\your\localdesk-traces" `
  --desktop-report-name "岗位匹配_v1.md" `
  --desktop-docx-name "岗位匹配_v1.docx" `
  --desktop-feedback "突出端到端 Agent 项目"
```

## 测试与真实程度

离线测试覆盖：JD + 本地证据合并、反馈落入新版本、Markdown/DOCX 双产物、Trace 完整性、低风险自动交付和禁止覆盖。Phase 6A 真实 Demo 使用构造数据与真实 LibreOffice，证明文件链路可运行；尚未使用用户真实简历和真实岗位 JD 验收内容质量。

## 尚未完成

- 尚无搜索引擎查询或跨站岗位发现；目前需要用户提供 JD URL。
- 尚未自动打开 Word，也没有通过自然语言多轮编辑现有 DOCX；反馈以“生成新版本”方式进入。
- 尚未创建 Outlook 邮件草稿，更不会自动发送或提交申请。
- 尚未自动归档到公司/岗位子目录；当前通过 `output_root` 指定本次交付目录。

## 下一步与面试价值

下一阶段优先补“搜索/岗位链接发现 → 真实 JD”与“版本化反馈修订”，再考虑 Outlook 草稿。面试时应重点讲：如何把 RAG、Browser、Office、Policy 与 Trace 串成一个业务闭环，以及为什么第一版选择确定性输出而不是直接让 LLM 自由生成简历事实。
