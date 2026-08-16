# LocalDesk Portfolio Release 验收

验收日期：2026-08-16。目标是确认现有 LocalDesk 可以被安装、理解、演示和复核；本轮没有新增 Workflow 或 Agent 能力。

## 发布候选状态

- `main` 是 `rebuild/after-first-meeting` 的祖先，没有 main 独有提交；
- 合并预演没有发现冲突；
- 先前未推送的 3 个提交已推到远端开发分支；
- 最终 release 收尾提交和 main 合并状态以本轮完成后的 Git 记录为准。

## 实际执行结果

| 检查 | 命令或方式 | 结果 | 边界 |
|---|---|---|---|
| 冻结依赖安装 | `uv sync --frozen --cache-dir .uv-cache` | 通过 | 首次下载需要访问 PyPI |
| 核心链路 | 6 个主线测试文件 | 28 passed | 覆盖 Main Agent、周报、研究、报销、UI、人审工具 |
| 全量测试 | `python -m pytest -q --basetemp ...` | 646 passed，3 skipped，8 failed | 8 个为保留的历史 baseline failure，见下文 |
| 冻结产品评测 | `evaluation/run_product_evaluation.py` | 18/18 | 自建工程评测，不是公共 Benchmark |
| 三路研究并发 | 同一 controlled I/O fixture | release 重跑 2.912× | 仓库锁定参考值为 2.999×；均非公网提速 |
| Demo 生成 | `demo/run_showcase.cmd` | 通过，2 个真实历史任务、57 条 Trace | recorded showcase 不冒充实时执行 |
| Demo 浏览器检查 | AI 周报首页、报销 Tab、控制台错误 | 两个 Tab 可切换，0 条页面错误 | 静态只读 UI，不在页面内执行动作 |
| Python / JS 语法 | `compileall`、模板 `new Function` | 通过 | 不替代行为测试 |
| README 本地链接 | 自动检查 README 与 docs 入口 | 19/19 存在 | 外部站点可用性不由本地检查保证 |
| 截图 | 浏览器全页截图并重新读取 | 正常 | 取自 recorded showcase |
| 公开安全扫描 | 用户名、绝对路径、常见 Token 前缀、URL 凭据 | 未发现待公开敏感值 | 测试中的短 dummy key 和 `example.com` 为构造数据 |

## 保留的 8 个历史失败

- `test_stop_cancel`：异步取消时序断言；
- `test_timeout`：测试依赖 Unix `sleep`，当前 Windows 环境没有该命令；
- `test_no_files_returns_empty`：仓库内 basetemp 会向上发现根目录 `LOCALDESK.md`；
- 5 个 `replacement_state` 测试：测试仍按旧的双返回值接口解包。

这些失败不在两个 Hero Demo、Controlled Runtime 或冻结产品评测的主链路中。本轮没有为了 release 数字好看而删除测试或改成功标准。

## Demo 与安全结论

README 截图能同时看到 User Task、Plan、Approval、Artifacts 和 Trace Timeline。录制快照中的本机根路径已替换为 `<recorded-run-N>`；历史文档中的用户名路径已匿名化；周报 Office 工具运行时通过 PATH 或 `LOCALDESK_NODE` / `LOCALDESK_ARTIFACT_PYTHON` 配置，不再绑定某台开发机。

## Tag 建议

暂不建议创建 `v0.1.0`：`pyproject.toml` 的当前项目版本已经是 `0.2.0`，仓库历史中还存在旧标签 `localdesk-v1.0.0`。完成 main 合并后，更一致的候选是 `v0.2.0`；GitHub Release 仍需用户确认后再创建。
