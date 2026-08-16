# 求职材料：LocalDesk Agent

## 简历项目描述

1. 基于既有 Python Agent 底座独立改造 LocalDesk Agent，设计 task_id 状态机、授权目录模型与 deny-first Policy Guard，将模型决策与文件系统执行解耦。
2. 实现本地 MD/TXT/PDF 可追溯检索与 staging Markdown 交付链路：引用定位到行号/页码，确认前零 output 副作用，确认时以 SHA-256 防篡改并持久化 JSONL Trace。
3. 实现受控文件整理/回滚核心工作流，dry-run 展示精确变更，串行执行记录 operation journal；覆盖越权、覆盖、symlink、中途失败、取消和回滚等 9 类测试场景。

## 90 秒介绍

我把一个学习型 Coding Agent 底座改造成了 LocalDesk Agent，目标不是让模型随意控制电脑，而是让它在用户授权目录中完成可解释的本地任务。架构上，检索、模型渲染、策略和执行分层：Knowledge Skill 只返回带 citation_id 的资料片段；Grounded LLM 只能基于这些片段返回结构化 JSON，每段必须引用真实 citation；Document Skill 只能先写 task staging，用户独立确认后才以哈希校验交付到 output。文件整理模块同样先 dry-run，确认后串行 move，并记录 journal；出现中途失败会停止，回滚只针对已成功操作且需要第二次确认。项目有 34 条确定性测试通过，真实模型指标尚待配置 provider 后补跑，我会如实说明这一点。

## 高频深挖

1. 为什么不让 LLM 直接调用文件工具？答：模型输出不可信且难审计；LLM 只负责受限结构化文本，路径与副作用由 Policy Guard 和执行层控制。
2. 如何避免引用幻觉？答：每次检索生成稳定 citation_id；Pydantic 校验结构后，渲染层再次验证每个 ID 属于本次检索集合，否则不 staging。
3. 为什么 staging 和哈希都需要？答：staging 让确认前无 output 副作用；哈希防止确认展示后草稿被替换。
4. 中途文件失败怎么办？答：每项成功/失败立即写 journal，首个失败停止后续操作；回滚计划只读取成功记录并反向生成。
5. 文件整理为什么不是 CLI 功能？答：当前完成的是受控核心工作流和测试，尚未接入面向用户的 CLI 入口；简历和 README 不把它描述成已交付入口。
