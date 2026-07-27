# Final Sprint 2：DOCX/PDF 正式交付与本地邮件草稿

**完成日期**：2026-07-27
**对应基线**：`f83daff` 之后的 Sprint 2 实现

## 这一阶段解决了什么

Sprint 1 已能生成和安全交付 Excel/CSV；本阶段补齐了办公产物的另外三块基础能力：读取 DOCX 内容、把 DOCX 经过真实渲染后作为正式 PDF 交付，以及生成带附件的标准 `.eml` 邮件草稿。

这不是“邮件发送能力”。`.eml` 是一个本地文件，可以被 Outlook 等客户端打开查看；LocalDesk 没有 SMTP、Outlook 自动化或真实发送接口。

## 当前真实可运行能力

1. **DOCX 读取**：读取授权目录内普通 `.docx` 文件的正文段落、Heading 层级和表格行列；本地检索也已将 DOCX 段落与表格行纳入可引用的 source chunk。
2. **正式 PDF 交付**：从授权 DOCX 生成任务 staging PDF，要求 LibreOffice 真实转换成功、`pypdf` 可重开、页数和每页文本可校验、并保存逐页 PNG 渲染证据；确认后才复制到 `output_root`。
3. **标准 EML 草稿**：生成 RFC 兼容的 To/Subject/body/attachment `.eml` 文件。草稿写入本地 output 可以自动完成，因为它不触发网络外发；覆盖、Bcc、头注入、越权附件和附件变化都会被拒绝。

## 关键代码变化

| 模块 | 作用 |
|---|---|
| `localdesk/desktop/skills/office_artifacts.py` | DOCX 读取、PDF staging/哈希校验、EML 生成与重新解析校验；不包含发送实现。 |
| `localdesk/desktop/office_artifact_workflow.py` | 将 PDF/EML 能力接入 Task 状态机、Policy Guard、Registry、Artifact 和 Trace。 |
| `localdesk/desktop/skills/knowledge.py` | 将 `.docx` 加入本地检索，引用定位到 paragraph 或 table row。 |
| `localdesk/desktop/registry.py` | 新增 `document.inspect_docx`、`document.stage_pdf`、`document.commit_pdf`、`mail.stage_eml`、`mail.commit_eml`。 |
| `localdesk/desktop/policy.py` | 新建 `.eml` 草稿允许低风险自动交付；PDF 仍需确认，任何覆盖仍拒绝。 |

## 验证结果

### 自动化回归

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_office_artifacts.py tests/test_desktop_foundation.py tests/test_desktop_reporting.py -q --basetemp <workspace>\.localdesk\pytest-sprint2-rerun -p no:cacheprovider
```

结果：**37 passed，1 skipped**。跳过项是 Windows 当前账户不允许测试创建真实 symlink；核心越权路径/普通文件校验仍有其他回归覆盖。

覆盖点包括：DOCX 正文/标题/表格读取、DOCX 进入本地检索、PDF staging/确认交付、来源 DOCX 变化时阻断、EML 收件人/主题/附件解析、头注入拒绝、符号链接附件拒绝，以及既有 Runtime 与 DOCX 报告回归。

进一步把 Excel/CSV、求职材料和 OfficeBench Adapter 回归合并运行后，结果为 **58 passed，1 skipped**。

完整仓库测试的当前结果为 **615 passed，3 skipped，12 failed**。12 个失败均未修改，且不属于本阶段改动范围：其中 3 个依赖当前 Windows sandbox 对 `%TEMP%`、`/tmp`、`C:\Users\Admin\.localdesk` 或 `.ssh` 的访问权限，1 个依赖 Unix `sleep`，1 个是既有异步时序断言，另有 5 个为既有 `replacement_state` 返回值接口不一致，2 个为既有 team coordinator 文件权限/状态问题。Sprint 2 新增测试和相关核心回归均通过。

### 真实 LibreOffice PDF Smoke Test

使用本机 `D:\Apps\LibreOffice\program\soffice.exe` 实际运行 DOCX -> PDF：

- Task 状态：`succeeded`
- 正式 PDF：`.localdesk/sprint2-real/output/brief.pdf`
- PDF 页数：1
- PNG 渲染页数：1
- 已逐页人工查看 PNG：标题、正文、边距和字体均正常，无截断或重叠。

该 smoke test 只使用合成文本，不使用用户或公司资料。它证明的是转换与交付链路，不是任何 OfficeBench 官方成绩。

## 一条交付 Trace 的逻辑

```text
授权 DOCX
  -> document.stage_pdf (task staging)
  -> LibreOffice PDF + page PNG
  -> PDF 页数/文本/渲染证据确定性校验
  -> 用户确认
  -> document.commit_pdf (output)
  -> Artifact + Trace
```

EML 草稿的差别在最后一步：它只写入新的本地 `.eml` 文件，因此可走低风险自动交付；它没有“发送”这一步。

## 已知边界

- DOCX 读取目前覆盖正文、基础标题和表格，不解析批注、修订、复杂嵌入对象或扫描件 OCR。
- PDF 交付依赖 LibreOffice；缺少 renderer 时会明确失败，不能把文件后缀伪装成正式交付。
- `.eml` 附件保持二进制内容和哈希，但不负责邮件客户端兼容性、发送、登录或外部邮箱状态。
- OfficeBench Docker/WSL2 环境仍被 Windows Host Compute Service 阻塞；本阶段没有安装 Docker、没有下载镜像、没有运行官方 Evaluator。

## 下一步

优先执行 Sprint 3 的“透明、冻结的 OfficeBench capability-aligned pilot”，但前提是用户完成 Windows 重启后的 WSL/Docker 恢复验证。随后以 Excel/CSV、DOCX/PDF、EML 三类已完成的通用能力，选择并冻结 15 个任务；第一次 Pilot 跑完后，不因语义失败调整策略。

同时，最终 Hero Demo 可以把已具备的 Excel、PDF、EML 串成“周五下班前报销核对”，而不是再扩展 PPT、真实邮箱或任意 GUI。

## 面试复盘重点

1. 为什么 PDF 不是“转换成功就算完成”：结构可打开、文本页数、渲染页图和最终交付哈希分别覆盖不同风险。
2. 为什么 `.eml` 可以自动创建而真实发送必须人工接管：前者是本地可撤销文件产物，后者会产生不可逆的外部影响。
