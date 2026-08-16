# Final Sprint 1：Excel/CSV 工具与 OfficeBench 环境检查

> 状态：Excel/CSV 产品能力已完成；OfficeBench B2B 环境因 Windows 重启前置条件暂停。

## 用户现在能使用的 Excel/CSV 能力

LocalDesk 新增了受控的结构化表格能力，完全通过 Python 与文件接口工作，不操作 Excel GUI：

1. 读取授权目录中的 `.csv` 和 `.xlsx`；
2. 查看工作表、表头、行列数量和单元格样本；
3. 按列筛选、稳定排序、按指定列去重；
4. 新增或按条件更新列；
5. 保留 XLSX 中的数值、文本、空单元格和未修改工作表；
6. 只写入 task staging，生成修改摘要和输出哈希；
7. 在确认交付前复核输入哈希、staging 哈希和目标冲突；
8. 通过确定性规则复读输出工作簿，确认表头、行数、单元格值和数据类型没有偏差；
9. 交付后在 Trace 中保留读取、staging、校验和产物事件。

核心代码：

- `localdesk/desktop/skills/spreadsheet.py`：文件格式、转换、哈希和确定性校验；
- `localdesk/desktop/spreadsheet_workflow.py`：接入 Task、Policy、Confirmation 和 Trace；
- `localdesk/desktop/registry.py`：注册 `spreadsheet.inspect`、`spreadsheet.stage_transform`、`spreadsheet.commit`。

## 验证结果

本轮相关核心回归：**53 passed**。

完整仓库回归另有 **615 passed、2 skipped**；存在 7 个未处理失败，均位于本次未修改的 hooks、memory 和 replacement-state 模块。它们不是 Excel/CSV 工具的验收结果，也没有为本 Sprint 修改无关代码。

新增测试覆盖中文表头、空单元格、数字/文本混合、稳定排序、重复行、多工作表、CSV、输入不覆盖、哈希变化拒绝、路径逃逸、错误扩展名、确认交付和 Trace。

这是真实产品能力，不依赖 OfficeBench 的任务名称、答案或私有目录结构。

## OfficeBench B2B 环境结论

已完成只读检查，未安装 Docker、未下载镜像、未修改或迁移已有 WSL 发行版。

| 项目 | 观察结果 |
|---|---|
| Windows | Windows 10 Pro |
| WSL | 已安装 WSL 2.7.11；已有 `Ubuntu`，版本 2，原状态为 Stopped |
| 固件虚拟化 | `systeminfo` 显示 `Virtualization Enabled In Firmware: Yes` |
| WSL 实际启动 | `wsl --distribution Ubuntu --exec uname -a` 返回 `HCS_E_SERVICE_NOT_AVAILABLE` |
| Docker | `docker` 命令和 Docker Desktop 均未发现 |
| D 盘 | 可用约 124.9 GiB，空间足够进行小规模 OfficeBench Spike |

准确的阻塞点是 Windows 的 WSL/Hyper-V 宿主计算服务不可用，而不是仓库、OfficeBench commit 或 D 盘空间。启用/修复相应 Windows 功能通常需要管理员权限与重启；根据项目规则，当前已暂停安装流程，未自行执行该操作。

重启完成后，B2B 的最小恢复顺序是：

1. 先运行 `wsl --distribution Ubuntu --exec uname -a`，确认现有发行版恢复；
2. 再确认 Docker Desktop 可启动并将数据目录放在 D 盘；
3. 固定 OfficeBench commit，记录实际镜像和磁盘占用；
4. 先跑官方原生最小链路；
5. 最后才连接 LocalDesk Dev `1-16/0`，调用官方 Evaluator。

在上述前置条件满足前，不能声称 OfficeBench Dev 已运行或通过。

## 下一步

Sprint 1 已形成一个可提交 checkpoint。环境恢复后继续 B2B；如果环境在规定时间内仍无法恢复，先推进 Sprint 2 的 DOCX 读取、正式 PDF 交付和 `.eml` 草稿能力，不用 Docker 阻塞产品冲刺。
