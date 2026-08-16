# 当前代码架构审计（MewCode 基线）

> 审计日期：2026-07-16
> 基线：Git tag `baseline-mewcode-original`（commit `eafa4a0`）
> 目的：说明当前 Coding Agent 如何工作，为 LocalDesk Agent 改造建立事实依据。本文不代表新增功能已经实现。

## 1. 当前产品形态

当前代码是 Python 3.11 的终端 Coding Agent。它以 Textual 终端界面为主，同时支持 `-p` 非交互命令和 `--remote` WebSocket 远程模式。

它的默认工具面向代码仓库：读文件、写文件、编辑文件、Glob、Grep 和 Bash；还可装配 MCP、Skill、子 Agent、Team 与 Git Worktree。因此它不是一个可直接安全操作个人目录的 Desktop Agent。

## 2. 一次任务的真实调用链

```text
python -m localdesk / localdesk CLI
  -> __main__.py: load_config()、PermissionChecker、create_default_registry()
  -> app.py: LocalDeskApp（Textual 输入、会话、确认弹窗、事件渲染）
  -> ConversationManager: 维护用户消息和工具结果
  -> Agent.run(): 调用 LLM，流式接收文本/ToolUse，循环推进
  -> ToolRegistry: 根据工具名取 Tool，校验 Pydantic 参数
  -> PermissionChecker: 规则、危险命令、路径沙箱、人工确认
  -> Tool.execute(): 文件/命令/搜索等实际执行
  -> ToolResultEvent / PermissionRequest: 结果或确认请求回到 UI
  -> session / context / filehistory: 保存会话、上下文和编辑备份
```

核心循环位于 `localdesk/agent.py::Agent.run()`：模型提出工具调用，Agent 先经过权限检查，再执行工具，并将结果追加回对话；模型根据结果继续决策，直到完成或出错。这个“模型—工具—结果回流”的循环可以复用。

## 3. 主要模块及改造判断

| 模块 | 当前职责 | LocalDesk 处理 |
|---|---|---|
| `agent.py` | LLM 流式循环、工具调用、确认事件、上下文压缩 | 保留，Desktop Runtime 通过适配层使用它，避免把新逻辑塞入该大文件 |
| `client.py`、`conversation.py`、`serialization.py` | 模型协议适配与对话序列化 | 保留 |
| `tools/base.py`、`tools/__init__.py` | Tool 协议、参数 schema、注册表 | 保留；新增 Desktop 专属 Registry |
| `app.py`、`permission_dialog.py` | Textual 输入、展示、人工确认 | 保留；后续只增补任务状态与确认预览 |
| `context/`、`memory/session.py` | 长会话压缩、会话恢复 | 保留；不可替代本地资料检索与任务审计 |
| `permissions/rules.py`、`dangerous.py` | 权限规则、危险命令识别 | 可借鉴；Desktop 另建硬策略层 |
| `permissions/sandbox.py` | 项目根目录/临时目录范围检查 | 不可直接复用为最终边界，需改为多授权根的 deny-first 校验 |
| `filehistory/` | 编辑文件前的备份与历史 | 可借鉴备份思路；不能表达移动、重命名、确认与产物 |
| `mcp/`、`skills/`、`hooks/` | 外部扩展与钩子 | v1 不改动，作为未来扩展点 |
| `worktree/`、`teams/`、`agents/` | Coding 并行任务、团队协作、Git 工作树 | v1 冻结，不删除，不装配进 Desktop 模式 |
| `tools/bash.py` | 任意字符串 Shell | Desktop v1 永不注册 |

## 4. 当前安全边界的不足

1. `PathSandbox` 对超出根目录的文件路径返回的是“ask”；用户可继续批准。LocalDesk 的越权访问必须直接 `deny`，不能留人工放行通道。
2. 现有规则提取通常面向单一文件参数；移动/重命名含源、目标两条路径，必须逐条检查。
3. `Bash` 使用 `asyncio.create_subprocess_shell()`，工作目录限制并不能约束绝对路径、重定向、子进程和网络。
4. `TraceManager` 服务于子 Agent 执行图；`FileHistory` 服务于编辑回退。两者均不是可持久化、可回放的个人任务审计日志。

## 5. 当前入口和配置边界

- 入口：`localdesk/__main__.py`；重命名后 CLI 名、描述和运行数据目录均使用 `localdesk` / `.localdesk`。
- 配置：`localdesk/config.py` 读取用户目录和工作目录下的 `.localdesk` 配置。
- UI：`localdesk/app.py::LocalDeskApp` 在运行期装配默认 Registry、MCP、Team、Worktree 等能力。

结论：本审计记录的是 MewCode 基线。LocalDesk 在后续重构中已完成用户可见名称、包名、CLI 和配置目录的统一迁移；Git 标签和来源说明仍保留 MewCode，以准确说明上游边界。
