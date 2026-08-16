# Phase 0：LocalDesk 重命名后基线与评测起点

> 状态：进行中。本文记录本轮 LocalDesk Office Agent 改造的出发点；历史 `baseline_validation.md` 仍用于说明更早的 MewCode 基线，不应混作同一次测试结果。

## 已确认的运行时命名

- Python 包与模块入口：`localdesk`
- CLI：`python -m localdesk`
- 安装命令：`localdesk`
- 本地配置与运行数据：`.localdesk/`
- GitHub remote：`https://github.com/qizhanggu/localdesk-office-agent.git`

`MewCode` 仅保留在上游来源说明、历史 Git tag 和原仓库链接中。

## 回归门槛

第一道回归门槛不是全量 Coding Agent 测试，而是当前 LocalDesk 已有的确定性核心闭环测试：

```powershell
python evaluation/run_baseline.py
```

它运行资料检索、Markdown staging/确认交付、Grounded Renderer 与文件工作流相关测试，并将真实摘要保存到 `evaluation/results/phase0_core_baseline.json`。

该脚本明确不测真实模型、Browser、Windows UIA 或完整任务成功率；没有对应可执行证据时，不填写这些指标。

## 全量测试的处理方式

重命名后的一次全量运行结果为 `573 passed, 2 skipped, 11 failed`。失败涉及 Windows 路径权限、时序、旧的返回值契约和 Team/Hook 测试；目前尚未完成与更早 `542 passed, 8 failed, 1 skipped` 记录的一一对照。因此在 Phase 0 结束前，不把这 11 项全部归因于环境，也不把它们当作 LocalDesk Runtime 的已解决问题。

后续原则：

- LocalDesk 新代码必须保持核心回归门槛通过；
- 全量失败逐项归档、复现和修复，不与功能改造混在同一个结论里；
- 每阶段新增的任务与指标追加到 `evaluation/`，并保留历史结果。
