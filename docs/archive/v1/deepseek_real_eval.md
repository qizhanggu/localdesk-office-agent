# 使用 DeepSeek 补跑真实模型评估

DeepSeek 可以用于 LocalDesk 的 Grounded LLM 评估：项目已有 `openai-compat` 客户端，使用 OpenAI Chat Completions 兼容接口，不需要引入新的 SDK 或模型框架。

## 你需要准备什么

只需要一个已开通余额的 **DeepSeek API Key**。请不要把 Key 发到聊天、截图、Git 仓库或任何 Markdown 文件中。

在 Windows PowerShell 的当前窗口设置临时环境变量：

```powershell
$env:OPENAI_API_KEY = "你的 DeepSeek API Key"
```

这只在当前终端窗口生效；关闭窗口后失效，不会写入 Git。

然后在项目根目录新建 `.localdesk/config.local.yaml`（该目录已被 `.gitignore` 忽略），内容如下：

```yaml
providers:
  - name: deepseek-eval
    protocol: openai-compat
    base_url: https://api.deepseek.com
    model: deepseek-v4-flash
    api_key: ${OPENAI_API_KEY}
    thinking: false
    context_window: 128000
    max_output_tokens: 4096
```

这里推荐先用 `deepseek-v4-flash` 控制成本；如果结构化 JSON 稳定性不足，再以相同样例补跑 `deepseek-v4-pro` 对比。DeepSeek 官方当前提供 OpenAI 兼容接口，基础地址为 `https://api.deepseek.com`；模型名称和价格会变化，以其官方文档为准。

## 评估怎么跑

先只选择 `evaluation/evaluation_tasks.json` 中 5–10 条“资料检索 / 引用定位 / 草稿暂存 / 确认交付 / 虚构引用拒绝”相关的无敏感样例，准备对应的构造资料目录。每条正常报告任务均执行两步：

```powershell
# 第一步：只生成 staging 草稿，不能写 output
python -m localdesk --desktop --desktop-task "<任务描述>" --desktop-read-root "<构造资料目录>" --desktop-output-root "<空输出目录>" --desktop-task-root "<任务记录目录>" --desktop-report-name "report.md" --desktop-grounded-llm

# 第二步：人工检查引用和草稿后，才确认交付
python -m localdesk --desktop --desktop-read-root "<构造资料目录>" --desktop-output-root "<空输出目录>" --desktop-task-root "<任务记录目录>" --desktop-confirm-task <task_id>
```

每条任务记录：是否获得可解析结构化输出、所有 citation_id 是否来自本次检索、是否成功 staging、确认后是否交付到 output。汇总三个指标：

- Citation Validity：合法引用数 / 全部引用数；
- Structured Parse Success：通过 JSON/Pydantic/引用校验的任务数 / 总任务数；
- End-to-End Task Success：成功暂存且确认后成功交付的任务数 / 总任务数。

## 两条硬规则

1. 只使用构造的无敏感资料；不要使用华为或任何公司的内部内容。
2. 出现模型错误、超时、虚构引用或无引用结论时，应记录为失败；不要手工修改结果后把它计为成功。

