# Phase 2：受控公开网页研究与确定性 Reviewer

**状态：已完成（2026-07-21）**

## 这一阶段解决了什么

Phase 1 已能将本地资料变成经确认后交付的 Markdown。本阶段把“公开网页资料”作为第二类只读证据接入同一条链路：

```text
本地资料 + 用户显式授权的 HTTPS 网页
  → Markdown staging
  → 确定性 Reviewer
  → 用户确认
  → Markdown 交付 + Trace
```

这不是通用浏览器自动化。它只读取公开文本页面，不登录、不提交表单、不上传、不下载，也不允许网页内容改变工具权限或指挥系统执行操作。

用户侧统一称它为**受控网页读取**；`browser.open` 只是当前代码中的工具标识，不代表已经具备搜索、链接发现、动态交互或完整 Browser Agent 能力。后续只有补齐搜索或链接发现后，才能讨论“自动检索岗位”。

## 关键实现与取舍

- 新增 `browser.open` 受控工具，风险等级为只读 `R1`，与本地检索、staging 和交付一样经过 Registry、Policy、Trace 与后置验证。
- 仅接受用户通过 `--desktop-browser-domain` 显式授权的 HTTPS 域名；HTTP、空域名、越权域名都会在发起网页读取前被 Policy 拒绝。
- `HttpBrowserAdapter` 仅提取 HTML 或纯文本正文，忽略 `script`、`style`、`noscript`、`template` 内容，并限制响应体最大为 1 MB、提取文本最大为 30,000 字符。
- 自动重定向被刻意拒绝，而不是悄悄跟随。这样最终地址必须由用户再次明确提供并通过白名单检查，避免“批准 A 却访问 B”。
- 新增确定性 `DeterministicReviewer`：草稿必须非空、含 `## Sources`、包含每条本地或网页证据的引用，且不能出现 API Key、Bearer Token、密码赋值等敏感字段模式。
- 第一版没有引入 Reviewer Role Agent。这里需要的是稳定、可解释的交付前规则校验；使用 LLM 反而会让验收不稳定，也没有当前阶段的必要收益。

## 实际可运行的 Demo

准备一个只含构造资料的目录，例如 `D:\demo\source`，再准备空的 `D:\demo\output` 和 `D:\demo\tasks`。选择你愿意授权的一条公开 HTTPS 页面，将它的域名和完整 URL 分别传入：

```powershell
python -m localdesk --desktop `
  --desktop-read-root D:\demo\source `
  --desktop-output-root D:\demo\output `
  --desktop-task-root D:\demo\tasks `
  --desktop-browser-domain example.org `
  --desktop-web-url https://example.org/ `
  --desktop-task "结合本地资料和公开页面整理一份求职研究摘要" `
  --desktop-report-name job-research.md
```

第一次命令只会生成 staging 和 Trace，并打印 `task_id`；`D:\demo\output` 仍然为空。检查草稿与来源后，再执行：

```powershell
python -m localdesk --desktop `
  --desktop-read-root D:\demo\source `
  --desktop-output-root D:\demo\output `
  --desktop-task-root D:\demo\tasks `
  --desktop-confirm-task <task_id>
```

第二次才会复核草稿 SHA-256 并交付到 `output`。若网页跳转、超过体积限制、域名未授权或 Reviewer 不通过，任务会失败且不会写入输出目录。

`example.org` 只用于说明命令形状；真实演示应由你选择并明确授权实际要读取的公开页面。联网页面会变化，因此它不是自动化评测成绩的来源。

## 测试与评测证据

Phase 2 新增了离线 `FakeBrowserAdapter` 和 `httpx.MockTransport` 测试，覆盖：

- 授权网页引用与 Reviewer 通过；
- 越权域名在调用浏览器前被阻止；
- 重定向不访问最终站点；
- 页面脚本文本被忽略，过大响应被拒绝；
- 缺失引用或疑似敏感字段的草稿被 Reviewer 拒绝；
- CLI 将越权网页请求以安全错误返回，而不是异常崩溃。

运行：

```powershell
python evaluation/run_phase2_evaluation.py
```

本次结果写入 [`evaluation/results/phase2_controlled_research.json`](../../../evaluation/results/phase2_controlled_research.json)：**27 passed, 0 failed, 0 skipped**，测试级回归通过率为 **1.0**。它只证明离线、确定性的受控链路没有回归；没有测量真实互联网任务成功率、检索质量、网页事实正确性、延迟、模型效果或成本。

## 已知边界

- 没有搜索引擎发现能力：用户必须提供完整 URL。这是为了先把已授权页面读取做稳，避免过早引入爬取和排序的不确定性。
- 不支持登录、Cookie、验证码、表单提交、下载、网页写操作、动态浏览器交互或桌面 GUI 自动化。
- 自动重定向暂不支持；若用户需要目标页面，必须把最终 HTTPS URL 与其域名显式加入授权参数后重新运行。
- Reviewer 检查“引用存在和交付结构”，不替代人工对网页内容真伪、时效性和结论合理性的判断。

## 下一步

下一阶段应优先做结构化办公文档交付（Markdown → DOCX，PDF 作为可选导出）和质量检查，继续复用 staging、确认与 Trace，而不是立刻堆叠 Memory、Scheduler 或 Multi-Agent。这样能把现在真实可跑的求职研究闭环变成更有展示价值的办公交付成果。

## 面试复盘重点

- 网页读取虽然是“只读”，仍然需要域名白名单、协议限制、体积限制、重定向策略和 Trace；不能因为不写文件就跳过安全设计。
- 为什么确定性 Reviewer 比 Role Agent 更适合第一版：规则可复现、测试稳定、失败原因清楚，且不会获得新的工具权限。
