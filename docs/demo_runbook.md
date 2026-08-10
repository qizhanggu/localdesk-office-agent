# LocalDesk 稳定演示手册

## 推荐演示方式

先展示录制回放，再按面试官兴趣运行真实命令。录制回放来自两次已经完成的真实 Task Trace，不依赖当时的公网、Office 进程或临时目录，因此最稳定；界面会明确显示 `Recorded real run`，不会冒充实时执行。

```powershell
.\demo\run_showcase.cmd
```

命令会生成 `.localdesk\demo-ui\index.html`。用浏览器打开后，可以切换：

- AI 资讯周报：30 条 Trace，展示官方 RSS 研究、三路职责、Editor、Reviewer、人工确认和三份产物；
- 报销核对：27 条 Trace，展示 XLSX/PDF/DOCX 输入、异常核对、人工确认和三份产物。

## 5 分钟讲解顺序

1. 用首页一句话说明产品：LocalDesk 能真正交付 Office 文件，所有正式动作都经过确认、验证和留痕。
2. 切到 AI 资讯周报，先看 Main Agent 的短计划，再沿六个阶段讲完整闭环。
3. 打开 Trace 的 Agent / Workflow 过滤器，说明真实读取了官方 RSS；正文页 403 后明确回退到 RSS 摘要。
4. 打开 Runtime 过滤器，说明用户确认前不正式交付，确认后还会复核路径、哈希和文件结构。
5. 切到报销核对，证明这套 Runtime 不是只为 PPT 写的，同样能交付 XLSX、PDF 和未发送 EML。
6. 最后指出顶部 18/18 是自建冻结工程评测，不是公开 Benchmark 或真实用户成功率。

## 现场运行选项

只展示自然语言理解和短计划，不生成文件：

```powershell
.\.venv\Scripts\python.exe -m localdesk.desktop.main_agent_demo `
  --task "帮我整理本周 AI 资讯并生成 PPT" `
  --plan-only
```

重新跑报销 Demo：

```powershell
.\.venv\Scripts\python.exe -m localdesk.desktop.reimbursement_demo --root .localdesk\reimbursement-live
```

第一条命令会返回 Task ID。检查确认页后，再执行：

```powershell
.\.venv\Scripts\python.exe -m localdesk.desktop.reimbursement_demo `
  --root .localdesk\reimbursement-live `
  --confirm <TASK_ID>
```

真实周报依赖公网，适合网络稳定时运行：

```powershell
.\.venv\Scripts\python.exe -m localdesk.desktop.weekly_briefing_live_demo `
  --root .localdesk\weekly-live `
  --start 2026-07-20 `
  --end 2026-08-10
```

若公网失败，应直接展示失败 Trace，不切换成“假实时”数据。离线 `manual_public_snapshot` 只能作为明确标注的回退。

## 演示前检查

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_dashboard.py `
  tests\test_main_agent.py `
  tests\test_weekly_briefing.py `
  tests\test_reimbursement_workflow.py `
  tests\test_weekly_human_review.py `
  -q
```

如果时间很短，只运行 `tests\test_dashboard.py`，并重新生成录制 UI。录制文件不包含本机仓库绝对路径。

## 诚实边界

- UI 是只读执行控制台，不会在页面里伪造工具执行或审批；
- 周报三路 Research 是确定性并发职责模块，不是三个 LLM；
- 报销 Demo 使用合成输入，规则范围目前只有金额上限和金额容差；
- 录制回放用于稳定展示历史真实 Trace，不代表此刻正在联网或生成文件；
- 系统只生成未发送邮件草稿，不会自动外发。
