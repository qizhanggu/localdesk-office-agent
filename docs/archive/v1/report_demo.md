# 无敏感报告 Demo

准备 `D:\\demo\\notes`，放入构造的 `meeting.md`：`Orion milestone is Friday; risk is API delay.`，并创建空的 `output` 与 `tasks` 目录。

```powershell
python -m localdesk --desktop --desktop-task "总结 Orion 进展和风险" --desktop-read-root "D:\\demo\\notes" --desktop-output-root "D:\\demo\\output" --desktop-task-root "D:\\demo\\tasks" --desktop-report-name "orion.md"
```

此时只检查 staging、引用和 task_id；output 必须为空。确认内容无误后：

```powershell
python -m localdesk --desktop --desktop-read-root "D:\\demo\\notes" --desktop-output-root "D:\\demo\\output" --desktop-task-root "D:\\demo\\tasks" --desktop-confirm-task <task_id>
```

检查 output 出现 Markdown，`events.jsonl` 含 `knowledge_searched`、`draft_staged`、`confirmation`、`artifact_committed`。不要使用真实个人或公司资料。
