# Phase 3：DOCX 交付与质量检查

**状态：已完成（2026-07-21）**

## 目标

Markdown 继续是可审阅、可追溯的源产物。DOCX 不是简单“另存为”后的文件，而是第二份需要独立验证的交付物：

```text
已审阅 Markdown → DOCX staging → 结构检查 → 实际渲染为 PDF/PNG → 用户确认 → Markdown + DOCX 交付
```

## 已实现

- 新增 `document.stage_docx` 与 `document.commit_docx` 两个受控工具；前者只能写入 task staging，后者仍需要用户确认。
- DOCX 以 `standard_business_brief` 的基础排版生成：标题、层级标题、正文、列表、来源区和页脚都使用 Word 原生结构，而不是把 Markdown 文本直接塞进文件。
- 结构检查会确认 DOCX 可打开、有正文、有标题层级、有 `Sources` 和来源条目、没有残留模板占位符。
- 真实渲染检查器使用 LibreOffice 转 PDF，再用项目依赖 `PyMuPDF` 生成逐页 PNG；检查 PDF 非空、页数正确、每页可提取文本、每张 PNG 非空。
- 一次确认涉及 Markdown 与 DOCX 两份产物时，会先对所有 staging 文件的 SHA-256 和目标冲突做预检；任一文件被篡改或目标被占用时，两份产物都不会写入 output。
- Trace 新增 `docx_structure_verified`、`docx_render_verified`、`delivery_preflight_verified`，可解释文件是如何通过质量门槛的。

## 离线验证

`FakeDocxRenderer` 只用于自动化测试中的流程验证，不会被当作真实渲染证据。当前覆盖：

- Markdown 与 DOCX 同时 staging、确认后同时交付；
- DOCX 结构中确实存在标题与 Sources；
- 渲染检查失败时任务在确认前失败；
- DOCX 被篡改时，确认后的预检阻止 Markdown 和 DOCX 两份产物的任何交付。

## 真实渲染验收

LibreOffice 已通过本机 `soffice` 实际运行。项目自身的 `LibreOfficeDocxRenderer` 已使用构造资料跑通完整 Runtime：

- 任务状态为 `succeeded`，确认后同时交付 Markdown 与 DOCX；
- DOCX 结构检查通过；
- LibreOffice 实际生成 1 页 PDF，`PyMuPDF` 生成 1 页 PNG；
- 人工检查 PNG：标题、层级、来源列表和页脚均正常，没有截断、重叠或字体缺失；
- Trace 包含 `docx_structure_verified`、`docx_render_verified`、`delivery_preflight_verified` 和两次 `artifact_committed`。

用以下脚本可重复运行这一份仅含构造资料的真实验收：

```powershell
python evaluation/run_phase3_real_render_demo.py
```

安装 LibreOffice 后，使用：

```powershell
python -m localdesk --desktop `
  --desktop-read-root D:\demo\source `
  --desktop-output-root D:\demo\output `
  --desktop-task-root D:\demo\tasks `
  --desktop-task "将本地资料整理成一份可交付报告" `
  --desktop-report-name report.md `
  --desktop-docx-name report.docx
```

只有控制台显示 staging 成功、Trace 记录结构与渲染检查通过后，才执行 `--desktop-confirm-task <task_id>` 交付。

## 后续边界

- 当前真实验收使用构造资料，未使用真实简历、公司资料或受限网页内容。
- `--desktop-docx-name` 需要本机可用 LibreOffice；缺失时 Runtime 会拒绝跳过渲染质量门。
- 后续真实网页最终评测仍需补一条公开页面证据，并在 Trace 保存 URL、访问时间、内容哈希和引用片段。
