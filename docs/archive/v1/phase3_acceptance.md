# Phase 3 验收报告：安全文件整理与可逆执行

> 结论：通过。完成后暂停，不进入 Phase 4。

## 改动范围

- 新增确定性 `FileSkill`：只在 managed_roots 内按扩展名生成 PDF、Images、Archives、Text、Other 分类的 dry-run 精确清单。
- 确认后串行 move；每项成功或失败均写 `operations.jsonl`。遇到第一个错误即停止，未开始操作不执行。
- 新增 `FileOrganizationWorkflow`：复用 Task、Policy Guard、Trace、确认状态机；dry-run 有冲突时不能进入确认。
- 回滚由独立 rollback task 完成：仅从原任务 journal 的 `succeeded` 记录反向生成计划，回滚同样需要独立确认。
- symlink 校验抽为可注入函数；mock 测试不依赖 Windows 的创建 symlink 权限。

## 测试命令与结果

```powershell
python -m pytest -q tests/test_file_workflow.py tests/test_desktop_foundation.py tests/test_desktop_reporting.py tests/test_grounded_renderer.py -p no:cacheprovider --basetemp .pytest-phase3-final
```

结果：**34 passed，1 skipped，6.23s**；Phase 3 自身 9 条测试。

覆盖：dry-run 零副作用、拒绝确认零副作用、正常整理和 journal、已有目标拒绝、越权、真实 symlink（平台跳过）与 mock symlink 拒绝、中途第 4 项失败时 3 成功+1 失败 journal 且后续停止、取消零执行、回滚预览零副作用、确认回滚、计划后目标冲突、read/output 根拒绝。

## 已知失败与需要手工验证

- 当前 Windows 环境无权限创建真实 symlink，故该用例跳过；但 mock 注入已实际断言 symlink 拒绝和零副作用。
- 请使用专门构造、无敏感的 Downloads 样例目录（PDF、图片、压缩包、文本）演示：预览计划 → 确认整理 → 查看 operations.jsonl/Trace → 预览 rollback → 确认 rollback。不要使用真实下载目录。

## 下一阶段风险与建议

Phase 4 应只做评估集、README、Demo 与简历叙事；不要扩大工具权限。Phase 2.5 的真实模型评估仍待 provider 配置，需单独补跑并如实记录指标。
