# LocalDesk Agent v1 — 教师查看入口

> 版本：[`localdesk-v1.0.0`](https://github.com/qizhanggu/mewcode-agent-review/tree/localdesk-v1.0.0)  
> 仓库：[qizhanggu/mewcode-agent-review](https://github.com/qizhanggu/mewcode-agent-review)

## 30 秒了解项目

LocalDesk Agent 是一个受控的本地资料与文件任务 Agent。它不让模型任意控制电脑，而是把“检索资料、生成报告、写入交付物、整理文件”拆开，并在模型与真实文件系统之间设置路径授权、确认和可追溯记录。

当前可演示主路径：**授权资料目录 → 检索带引用片段 → 生成 Markdown 草稿 → 用户确认 → 写入 output**。

## 已完成的可信证据

| 能力 | 实现边界 | 证据 |
|---|---|---|
| 本地资料检索 | 只读取 `read_roots` 内的 MD/TXT/可提取文本的 PDF；返回稳定 `citation_id`，定位到行号或页码 | [Phase 2 验收](phase2_acceptance.md) |
| Grounded LLM 报告 | LLM 只接收本次检索片段；必须返回结构化 JSON 和真实引用；虚构/无引用/超时均拒绝暂存 | [Phase 2.5 验收](phase25_acceptance.md) |
| 安全交付 | 先写 task staging；确认时复核 SHA-256；确认前 output 零副作用；全过程写 JSONL Trace | [无敏感报告 Demo](report_demo.md) |
| 文件整理核心工作流 | dry-run 展示精确移动清单；确认后串行 move、记录 journal；中途失败停止；回滚须独立确认 | [Phase 3 验收](phase3_acceptance.md) |
| 自动化验证 | 25 条无敏感评估任务；当前确定性测试为 **34 passed, 1 skipped** | [Phase 4 验收](phase4_acceptance.md) |

## 已知边界（如实说明）

- 文件整理是“已实现并测试的受控核心工作流模块”，**不是**已经完成的 CLI 用户入口。
- 真实 LLM 的 5–10 条样例评估尚未运行：项目当前没有本地 provider/API Key 配置，不能把 fake LLM 单测当作真实模型效果。
- 不支持任意 Shell、删除、覆盖写入、浏览器、MCP、多 Agent、Electron 或鼠标键盘自动化。

## 希望获得的建议

下一步准备将通用能力收敛为一个可展示的真实场景，候选为：

1. **求职资料工作台**：基于简历、岗位描述、项目材料和面试笔记，生成有引用的岗位匹配分析、项目表述优化和面试复盘；
2. **科研/实习资料助手**：基于构造的会议纪要、需求文档和技术资料，生成周报、风险清单与任务摘要。

希望从 Agent 岗位面试的辨识度角度判断优先方向，以及是否应优先补齐“固定任务模板 + 无敏感 Demo 数据 + 真实模型评估”，而非继续增加浏览器、日历等通用工具。
