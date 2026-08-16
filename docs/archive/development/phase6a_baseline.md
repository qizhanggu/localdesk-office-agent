# Phase 6A：可运行工程基线冻结

**状态：已完成（2026-07-22）**

## 本阶段解决的问题

Phase 6A 不再增加 Runtime 抽象，而是把 Phase 0～5 的能力整理成“能运行、能演示、能解释、能复现”的基线：统一评测脚本、真实 Demo、诚实 README，以及直接读取 Task Trace 的简洁看板。

## 当前可运行能力

- `evaluation/run_phase6a_evaluation.py` 一次运行受控 Desktop Runtime 核心回归。
- `evaluation/run_phase6a_demo.py` 使用构造 JD 和构造履历，真实运行 Markdown → DOCX → LibreOffice PDF/PNG 检查 → 自动交付 → Trace。
- `--desktop-task-board` 从 `task.json` 和 `events.jsonl` 生成只读 HTML 看板，只展示真实任务状态、动作、最后事件和产物。
- 新建且不覆盖的本地产物可按低风险策略自动交付；覆盖、移动、删除和外部提交没有因此放宽。

## 测试与真机验收

统一回归结果保存在 `evaluation/results/phase6a_baseline.json`：**54 passed，1 skipped，0 failed**。skipped 是 Windows 当前账户不能创建真实 symlink 的既有环境限制；对应拒绝路径已有 mock 测试覆盖。

真实 Demo 结果保存在 `evaluation/results/phase6a_demo.json`：Task `4f3df4d0-654a-4f0a-938d-d50a559c872b` 状态为 `succeeded`，交付 Markdown 和 DOCX，并生成只读任务看板；DOCX 真实经过 LibreOffice 转 PDF、逐页 PNG 和结构检查。Demo 只使用构造数据，不包含个人或公司敏感资料。

真实公网证据保存在 `evaluation/results/real_public_web_trace.json`：Task `4d16d0cb-f8e2-4814-aee6-e7da953af83e` 成功读取 `https://example.org/`，Trace 保存访问时间、正文 SHA-256、引用片段及页面中发现的链接。该能力仍称为“受控网页读取 + 链接发现”，不是自动搜索岗位的完整 Browser Agent。

## 已知边界

- 看板是静态只读 HTML，不提供任务控制按钮。
- Reviewer 只做确定性结构和敏感字段检查；普通引用缺失给 warning，敏感字段才 block。
- 尚未测量真实求职材料质量、任意网站搜索成功率、外部提交成功率或任意第三方 GUI 成功率。
- 不支持自动发送邮件、提交表单、登录、支付或验证码处理。

## 面试复盘重点

1. 为什么评测要把离线确定性回归、真实公网读取和真实 Office 渲染拆开记录。
2. 风险分级的核心不是“少弹确认框”，而是用目标是否存在、是否外发、是否可恢复来决定确认强度。
3. 看板为什么直接消费 Trace，而没有另建一套容易与 Runtime 状态漂移的数据库。
