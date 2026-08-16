# Phase 2 阶段验收报告：带引用资料到受确认 Markdown 交付

> 日期：2026-07-16
> 结论：**通过。Phase 2 到此暂停，不自动进入 Phase 3 文件整理。**

## 1. 改动范围

- 新增 `KnowledgeSkill`：扫描用户授权的 MD、TXT、文本型 PDF；返回稳定的 `文件相对路径 + lines x-y` 或 `文件相对路径 + page n` 引用。
- 新增 `DocumentSkill`：把来源片段渲染为带 `Sources` 的 Markdown，先写入 `<task>/staging/`，记录 SHA-256 与计划交付路径。
- 新增 `KnowledgeReportWorkflow`：`draft -> planned -> awaiting_confirmation -> executing -> succeeded/cancelled/failed`；只有独立的确认命令才会交付到 output。
- CLI 新增 `--desktop-report-name` 与 `--desktop-confirm-task`；第一次调用只 staging，第二次携带 task_id 才交付。
- 新增 `pypdf>=5.0` 依赖并更新 `uv.lock`；新增 7 个 Phase 2 测试。

## 2. 测试命令与结果

```powershell
python -m pytest -q tests/test_desktop_foundation.py tests/test_desktop_reporting.py -p no:cacheprovider --basetemp .pytest-phase2-final
```

结果：**21 passed in 1.10s**。

覆盖：授权资料检索、Markdown 行号引用、真实 PDF 文本页码引用、staging 零 output 副作用、拒绝确认、草稿篡改导致哈希失效、已有 output 不覆盖、两次独立 CLI 调用完成确认交付，以及 Phase 1 的越权/Shell/删除/默认工具隔离规则。

## 3. 已知失败与限制

- 本阶段新增测试无失败。
- 原 Coding Agent 基线仍有 8 个已知失败（Windows `sleep`、时序、测试与代码快照契约不一致），详见 [基线验证](baseline_validation.md)；与本阶段无关。
- PDF 只支持可提取文本；扫描件/OCR、复杂表格/版式理解不在本阶段范围。
- 当前报告是确定性的“引用驱动资料摘要”，尚未接入 LLM 润色/改写；这保证了无 API 的可复现验收，但不是最终的智能写作体验。

## 4. 需要你亲自验证的事项

用**无敏感数据**的两个绝对路径目录（例如 `D:\\demo\\notes`、`D:\\demo\\output`）执行：

```powershell
python -m localdesk --desktop --desktop-task "汇总本周会议纪要" --desktop-read-root "D:\\demo\\notes" --desktop-output-root "D:\\demo\\output" --desktop-task-root "D:\\demo\\localdesk-tasks" --desktop-report-name "weekly.md"
```

检查：output 中尚未出现 `weekly.md`；查看命令输出的 staging 路径和 task_id，确认引用是否符合预期。确认后再运行：

```powershell
python -m localdesk --desktop --desktop-read-root "D:\\demo\\notes" --desktop-output-root "D:\\demo\\output" --desktop-task-root "D:\\demo\\localdesk-tasks" --desktop-confirm-task <task_id>
```

检查：`weekly.md` 才出现在 output，且 `events.jsonl` 含 `knowledge_searched`、`draft_staged`、`confirmation`、`artifact_committed`。

## 5. 下一阶段风险与建议

- 建议先由你完成上面的手工验收，再决定是否进入 Phase 3。
- Phase 3 风险是“文件移动的部分失败和回滚一致性”，建议只在单独的无敏感样例 Downloads 目录开发；继续保持预览、逐条策略检查、禁止覆盖、operation journal 与回滚计划。
- 若优先提升项目展示效果，也可在进入 Phase 3 前先单独评审“LLM 润色报告”的增量；它必须复用本阶段的 staging、哈希和确认机制，不能让模型直写 output。
