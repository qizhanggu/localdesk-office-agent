# Phase 4 最终验收报告：评估、README、Demo 与求职叙事

> 结论：通过。未新增工具权限、Shell、浏览器、MCP、多 Agent 或 Electron；项目功能范围到此停止。

## 交付

- `evaluation/evaluation_tasks.json`：25 条无敏感评估样例，覆盖检索、引用、staging、确认/拒绝、越权、Grounded LLM 拒绝、文件 dry-run/冲突/回滚与安全拒绝。
- README：来源、独立改造范围、架构、安全模型、状态/确认/Trace/staging/哈希、能力边界、Demo 和真实评估状态。
- [报告 Demo](report_demo.md)：可复现的本地资料到确认交付 Demo。
- [求职材料](job_materials.md)：3 条简历描述、90 秒介绍、5 个深挖问题真实回答要点。

## 可复现结果

```powershell
python -m pytest -q tests/test_file_workflow.py tests/test_desktop_foundation.py tests/test_desktop_reporting.py tests/test_grounded_renderer.py -p no:cacheprovider --basetemp .pytest-phase4-final
```

结果：**34 passed，1 skipped，4.81s**。这是 deterministic/fake LLM 测试结果，不是真实模型指标。skip 为 Windows 无创建 symlink 权限；mock symlink 拒绝测试已实际通过。

## 真实 LLM 评估边界

本机仍无 `.localdesk/config.yaml` provider，真实模型 5–10 条样例尚未运行。因此 Citation Validity、结构化解析成功率、端到端成功率均明确为待补，未填写任何虚假数值。配置已有 provider 后按 `phase25_acceptance.md` 补跑。

## 文件整理边界

文件整理与回滚为**已实现并通过测试的受控核心工作流模块**，不是已完成的 CLI 用户入口；README、Demo 和求职材料均保持此表述。

## 建议的最终人工验收

使用构造的无敏感 notes/Downloads 样例：运行报告 Demo，检查确认前 output 为空；再以测试或架构演示展示文件 dry-run、journal 和 rollback。不要使用真实个人下载目录或公司资料。
