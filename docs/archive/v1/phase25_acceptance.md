# Phase 2.5 验收报告：Grounded LLM Report Rendering

> 日期：2026-07-16
> 状态：**工程验收通过；真实模型评估被本机缺少 provider 配置阻塞，未伪造指标。Phase 3 未启动。**

## 改动范围

- `GroundedLLMRenderer` 复用现有 `LLMClient.stream()` 和 `ConversationManager`；调用时不传 tools，模型只接收本次 Knowledge Skill 返回的 `{citation_id, text}` 片段。
- 模型被强制输出 JSON：`title`、`sections[]`、每段 `heading/content/citation_ids`；Pydantic 禁止额外字段、空 sections 与空 citation_ids。
- 渲染层二次校验每个 citation_id 都存在于本次检索结果；格式错误、工具调用、虚构 citation、无引用、超时或模型异常均写入 `llm_render_failed` Trace，且不创建 staging/output 草稿。
- 合法结构化输出仍通过既有 `DocumentSkill` 写 staging、记录 SHA-256，并复用 Phase 2 的独立确认和 output 交付。
- CLI 新增 `--desktop-grounded-llm`：仅在该显式开关下使用现有 `load_config() + create_client()`；未新增 SDK、HTTP 客户端或模型框架。

## 测试命令与结果

```powershell
python -m pytest -q tests/test_grounded_renderer.py tests/test_desktop_foundation.py tests/test_desktop_reporting.py -p no:cacheprovider --basetemp .pytest-phase25-final
```

结果：**26 passed in 3.89s**。

新增 fake LLM 覆盖：合法输出带引用交付、虚构 citation 拒绝、无引用结论拒绝、超时失败、用户拒绝确认零 output、副本篡改后哈希交付失败。日常测试不依赖真实 API。

## 已知失败与真实模型评估

真实评估门槛尚未完成：运行 `load_config()` 返回 `ConfigError: No config file found`，当前项目目录和用户目录均没有 `.localdesk/config.yaml`，所以不存在可调用的 provider/API key。故以下真实模型指标均为**待补跑**，而非 0 或成功：引用有效率、结构化解析成功率、5–10 条任务成功率。

补跑方式：配置好 LocalDesk provider 后，使用 Phase 2 的两步命令并在第一步附加 `--desktop-grounded-llm`；使用 5–10 条无敏感样例任务，人工核验每段引用，再统计：

- Citation Validity = 合法 citation 引用数 / 全部 citation 引用数；
- Structured Parse Success = 成功通过 Pydantic 与 citation 校验的任务数 / 总任务数；
- Task Success = staging 成功且确认后 output 交付成功的任务数 / 总任务数。

## 需要你亲自验证的事项

1. 在不提交 API key 到 Git 的前提下，配置现有 `.localdesk/config.yaml` 或环境变量。
2. 用无敏感样例运行 `--desktop-grounded-llm`，检查第一次命令仅产生 staging 和 task_id；第二次 `--desktop-confirm-task` 才写 output。
3. 留意生成报告每个 section 的 citation_id 是否真实、是否能在 Sources 中定位。

## 下一阶段风险与建议

建议先补跑真实模型评估并把指标写回本报告，再讨论 Phase 3。Phase 3 的文件移动/回滚风险与本阶段无关，不能因为 LLM 能写报告就放宽路径、确认、哈希或 Trace 边界。
