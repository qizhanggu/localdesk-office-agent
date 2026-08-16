# 原始基线验证记录

> 日期：2026-07-16
> 代码基线：`baseline-mewcode-original`（`eafa4a0`）
> 说明：本记录在任何 LocalDesk 业务代码写入前生成，用于区分原始问题与后续改造回归。

## 环境

- Windows；受限检查环境显示 Python 3.11.9，但实际安装依赖、运行测试和 CLI 验证使用 Python 3.12.7。两者环境隔离，后续必须建立项目专用虚拟环境。
- 项目以 editable 方式安装；运行依赖来自 `pyproject.toml`
- 开发依赖：pytest 9.1.1、pytest-asyncio 1.4.0
- `uv` 未安装。项目把测试依赖放在 `dependency-groups.dev`，这不是 pip 的 extra；因此当前验证使用 pip 单独安装 pytest 两项依赖。

> 注意：安装项目依赖时，pip 报告本机已有 Streamlit 与新版 `rich` 的版本冲突。该冲突不阻塞本仓库测试，但后续 LocalDesk 开发应切换到独立虚拟环境，避免污染 Anaconda 全局环境。

## 执行命令

第一次运行：

```powershell
python -m pytest -q -p no:cacheprovider
```

测试框架没有权限写入系统临时目录 `<SYSTEM_TEMP>/pytest-of-<USER>`，导致 126 个 setup error；这不是项目断言失败。

为隔离环境目录权限后，使用：

```powershell
python -m pytest -q -p no:cacheprovider --basetemp .pytest-basetemp
```

结果：**542 passed, 8 failed, 1 skipped**。

## 8 个原始失败的分类

| 分类 | 用例 | 结论 |
|---|---|---|
| 取消时序 | `tests/test_agent.py::test_stop_cancel` | 测试假定 0.15 秒内至少完成一次 turn；当前机器调度/依赖版本下未满足该时序，属于脆弱测试。 |
| Windows 命令差异 | `tests/test_hooks.py::TestCommandExecutor::test_timeout` | 用例调用 Unix 命令 `sleep 10`，Windows 中不存在该命令，未真正覆盖 timeout。 |
| 测试目录层级假设 | `tests/test_memory.py::TestLoadInstructions::test_no_files_returns_empty` | 基于仓库内临时目录运行时，向上查找命中了仓库根的 `LOCALDESK.md`；测试假定临时目录不在项目树下。 |
| 返回值契约不一致 | `tests/test_replacement_state.py` 的 5 个用例 | 测试按 `(api_conversation, records)` 解包，当前 `apply_tool_result_budget()` 返回记录列表，属于代码与测试快照未同步。 |

## 可作为后续回归门槛的结论

1. 暂以 `542 passed` 作为“未触碰原始模块时不得降低”的可观测基线；8 个已知失败在单独 issue/提交中处理，不夹带进 Desktop 功能开发。
2. Desktop 新增测试一律使用仓库内受控 `--basetemp` 或 pytest fixture，不依赖系统临时目录权限。
3. M1 之前建立 `.venv` 或 uv 环境；不能继续把全局 Anaconda 当作项目可复现环境。

## 非交互启动与工具快照

在主机 Python 3.12.7 环境执行：

```powershell
python -m localdesk --help
python -c "from localdesk.tools import create_default_registry; ..."
```

结果：CLI 帮助可正常输出；当前默认 Registry 为
`ReadFile, WriteFile, EditFile, Bash, Glob, Grep`。

这不是 LocalDesk 的安全工具集合。后续必须新建 Desktop Registry，而不是对这个默认集合做零散 disable。
