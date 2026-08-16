# Phase 5：Windows Desktop Computer Use

**状态：已完成（2026-07-21）**

## 交付能力

LocalDesk 增加了受控 Windows Desktop Adapter。它只面向用户显式白名单的窗口标题，并把观察、输入、调用、验证与人工接管写回同一个 Task Trace：

```text
窗口白名单 → UIA 观察/控件树 → 用户确认 → 输入/调用 → 状态验证
                                  └→ 状态变化或 UIA 不唯一 → 停止并人工接管
```

视觉 fallback 没有被包装成“万能点击”。它只能在自建测试窗口内使用窗口相对坐标，并且必须同时匹配预览时的窗口边界和 screen hash；任何变化都会拒绝动作。

## 真实验收

使用仓库内的 `evaluation/phase5_test_app.cs` 编译自建 WinForms 测试应用后，已通过 Windows Computer Use 的真实 UIA Tree 验收：

- 唯一识别窗口 `LocalDesk Phase 5 Test App`；
- UIA 定位到 `Task input`、`Submit safe demo` 与状态栏；
- 在输入框写入构造文本 `Orion-safe-demo`；
- 调用本地低风险提交动作；
- UIA 再次读取状态栏，得到 `Status: submitted Orion-safe-demo`。

该应用没有网络、账号、文件读写或外部传输，验收结束后已关闭。

## 工程实现与安全边界

- 新增 `WindowsUiaAdapter`、`DesktopComputerWorkflow`、`ScreenState` 和 `UiControl`；`pywinauto` 作为项目 Windows 依赖，Pillow 用于窗口图像哈希。
- Registry 新增 `desktop.uia.observe`、`desktop.uia.set_text`、`desktop.uia.invoke`、`desktop.visual_fallback`。观察为 R0；输入、调用和 fallback 均须确认。
- `desktop_allowed_window_titles` 是独立授权面：未列入白名单的桌面窗口在任何输入前被 Policy Guard 拒绝。
- 任务设置最大步骤数；窗口不唯一、UIA 控件缺失、状态变化或 fallback 哈希不匹配时写入 `manual_takeover_required`，不盲目重试。
- 当前 demo 仅支持自建测试应用。没有接入公司系统、账号登录、系统设置、Shell、删除或任意桌面应用自动化。

## 回归与评测

运行：

```powershell
.\.venv\Scripts\python.exe evaluation\run_phase5_evaluation.py
```

结果保存到 `evaluation/results/phase5_desktop_computer_use.json`。自动化测试覆盖正常 UIA 流程、白名单、拒绝确认、状态变化后的 fallback 拒绝和人工接管。

## 面试复盘重点

1. UIA 优先于视觉/坐标：控件语义更稳定、可验证；坐标只在严格约束下作为 fallback。
2. 为什么 screen hash 不能单独当“安全证明”：它只是防止旧坐标重放的附加条件，仍需窗口白名单、边界和独立确认。
3. Computer Use 不替代结构化接口：对于已有 API、文件系统能力或受控网页读取，仍优先使用更可审计、更低风险的接口。
