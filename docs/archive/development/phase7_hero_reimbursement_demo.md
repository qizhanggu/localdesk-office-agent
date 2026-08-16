# Final Hero Demo：周五下班前报销核对

## 真实能力

LocalDesk 读取授权的支付流水 XLSX、多张发票 PDF 和规则 DOCX，以确定性规则匹配 `invoice_no` 与 `amount`。它只将确实可证明的问题标记为 `missing_invoice`、`duplicate_invoice`、`amount_mismatch` 或 `unconfirmed`，不会把无法解析的内容写成已匹配。

产物全部先进入 task staging：`flagged_payments.xlsx`、`reimbursement_summary.docx`、经过 LibreOffice 渲染检查的 `reimbursement_summary.pdf`，以及带 XLSX/PDF 附件、但绝不发送的 `reimbursement_review.eml`。Trace 保存来源哈希和逐笔结论。

## 合成 Demo 实测

- 输入：2 笔支付、1 张合成 PDF 发票、1 份合成规则 DOCX。
- 结果：1 笔 `matched`，1 笔 `missing_invoice`。
- XLSX、DOCX、PDF、EML、`task.json` 和 `events.jsonl` 均已生成。
- PDF 为 1 页，已人工检查 PNG；标题、表格和中文问题说明无截断。

## 验证

`tests/test_reimbursement.py` 覆盖缺失/重复/金额不一致、staging XLSX、Task Trace、PDF 和 EML staging。与 Desktop/表格核心回归合并运行：**31 passed，1 skipped**。

## 边界

仅支持文本可提取的 PDF 发票；不做 OCR、不连接财务系统、不发送邮件。PDF 与 XLSX 仍处于 staging，正式交付需要确认，符合当前风险策略。
