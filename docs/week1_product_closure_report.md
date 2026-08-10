# LocalDesk 第一周：产品闭环收尾报告

日期：2026-08-10

## 用户新增了什么能力

1. AI 资讯周报不再只停在 staging。Reviewer 通过后会请求一次人工确认，确认后正式交付 PPTX、PDF 和未发送 EML。
2. 报销核对新增完整 Demo 命令：读取 XLSX、发票 PDF 和规则 DOCX，生成 XLSX、DOCX/PDF、确认页和未发送 EML；确认后正式交付 XLSX、PDF、EML。
3. 报销规则 DOCX 不再只是被校验路径和计算哈希。当前支持读取：
   - `max_payment_amount` / `单笔报销金额上限`；
   - `amount_tolerance` / `金额容差`。
4. 两个 Workflow 复用同一个 bundle 交付模块。正式交付前会检查路径、SHA-256 和 Office/PDF/EML 文件结构，再通过 Registry、Policy、Verification 和 Trace 执行。

## 为什么现在做

之前两个 Demo 已经能生成真实 Office 文件，但 Runtime 任务仍停在 `awaiting_confirmation`，`artifacts` 为空，用户无法完成最后一步。报销规则 DOCX 也没有真正影响判断。它们会让面试官继续追问“到底交付了吗”“规则文件真的用了吗”，而旧版本无法给出有证据的肯定回答。

本次改动优先补产品闭环，没有新增 Main Agent、复杂规划框架或更多安全模块。

## 我怎么运行并验证

### 报销核对

```powershell
.\.venv\Scripts\python.exe -m localdesk.desktop.reimbursement_demo --root .localdesk\reimbursement-demo-v2
.\.venv\Scripts\python.exe -m localdesk.desktop.reimbursement_demo --root .localdesk\reimbursement-demo-v2 --confirm <TASK_ID>
```

2026-08-10 真实任务：`508bc30c-2eac-494f-833f-171bfbae035d`。

验证结果：1 项匹配、2 项待复核；其中一项因为 100 元超过 DOCX 中的 80 元上限被标记为 `policy_limit_exceeded`。LibreOffice 实际生成 1 页 PDF；最终交付 XLSX、PDF、EML 三个文件，任务状态为 `succeeded`。

### AI 资讯周报

见 [Phase 8](phase8_ai_weekly_briefing.md)。2026-08-10 真实任务：`dba67255-c9a6-4663-bddd-2d02d5a995fc`，最终交付 3 个文件，任务状态为 `succeeded`。

### 自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_desktop_foundation.py tests\test_weekly_briefing.py tests\test_reimbursement.py -p no:cacheprovider
```

本次定向结果：`21 passed`。

全量回归结果：`625 passed, 3 skipped, 8 failed`。8 个失败属于本次改动之外的既有 Windows/接口回归问题（取消时序、Windows `sleep` 命令、指令发现和旧 replacement-state 接口），尚未宣称修复。

## 当前边界

- 周报仍是预置摘要和价值判断，真实来源读取仍为明确标注的离线快照；
- 周报研究模块还不是真 LLM Agent，Reviewer 还不做结论—证据一致性判断；
- 报销规则只支持两个明确字段，不是通用自然语言规则引擎；
- Main Agent、18 条冻结评测和 UI 升级尚未开始；
- 没有自动发送邮件，也没有修改源文件。
