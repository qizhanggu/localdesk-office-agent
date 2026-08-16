from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PINNED_COMMIT = "b978b808667c32b52ce19a67ce1def1de9ae02b7"
EXPECTED_TASK_COUNTS = {"1": 93, "2": 95, "3": 112}

TYPE_TO_APP = {
    ".ics": "calendar",
    ".csv": "excel",
    ".xls": "excel",
    ".xlsx": "excel",
    ".eml": "email",
    ".doc": "word",
    ".docx": "word",
    ".pdf": "pdf",
    ".png": "ocr",
    ".jpg": "ocr",
    ".jpeg": "ocr",
    ".bmp": "ocr",
    ".tif": "ocr",
    ".tiff": "ocr",
}
DOC_TYPE_TO_SUFFIX = {
    "ics": ".ics",
    "calendar": ".ics",
    "csv": ".csv",
    "xls": ".xls",
    "xlsx": ".xlsx",
    "excel": ".xlsx",
    "email": ".eml",
    "eml": ".eml",
    "doc": ".docx",
    "docx": ".docx",
    "word": ".docx",
    "pdf": ".pdf",
    "png": ".png",
    "jpg": ".jpg",
    "jpeg": ".jpeg",
    "txt": ".txt",
}
FILE_SUFFIX_RE = re.compile(
    r"(?i)(?<![\w])(?:[\w .{}'-]+?)"
    r"(\.docx|\.doc|\.xlsx|\.xls|\.csv|\.pdf|\.eml|\.ics|\.png|\.jpg|\.jpeg|\.txt|\.md)\b"
)


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    subtask_id: str
    declared_app_count: int
    input_types: list[str]
    output_types: list[str]
    inferred_apps: list[str]
    inferred_operations: list[str]
    evaluator_types: list[str]
    inferred_chain: str
    conservative_coverage: str
    coverage_gaps: list[str]
    task_file_sha256: str


class StaticAnalysisError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise StaticAnalysisError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def verify_snapshot(snapshot: Path, expected_commit: str = PINNED_COMMIT) -> None:
    actual = _git(snapshot, "rev-parse", "HEAD")
    if actual != expected_commit:
        raise StaticAnalysisError(
            f"OfficeBench commit mismatch: expected {expected_commit}, got {actual}"
        )


def tracked_task_paths(snapshot: Path) -> list[str]:
    return [
        line
        for line in _git(snapshot, "ls-tree", "-r", "--name-only", "HEAD", "tasks").splitlines()
        if line
    ]


def _normalize_suffix(value: str | None) -> str | None:
    if not value:
        return None
    suffix = Path(str(value).replace("\\", "/")).suffix.lower()
    return suffix if suffix else None


def _task_group(path: str) -> str | None:
    parts = Path(path).parts
    return parts[1] if len(parts) > 2 and parts[0] == "tasks" else None


def group_input_types(paths: Iterable[str]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for value in paths:
        normalized = value.replace("\\", "/")
        if "/testbed/" not in normalized:
            continue
        group = _task_group(normalized)
        suffix = _normalize_suffix(normalized)
        if group and suffix and suffix != ".json":
            grouped.setdefault(group, set()).add(suffix)
    return grouped


def _walk_values(value: object) -> Iterable[tuple[str, object]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)


def evaluator_output_types(evaluation: list[dict[str, object]]) -> set[str]:
    output_types: set[str] = set()
    for item in evaluation:
        args = item.get("args", {})
        if isinstance(args, dict):
            doc_type = str(args.get("doc_type", "")).lower()
            if doc_type in DOC_TYPE_TO_SUFFIX:
                output_types.add(DOC_TYPE_TO_SUFFIX[doc_type])
            if "username" in args and doc_type == "email":
                output_types.add(".eml")
            for key in ("file", "result_file", "filepath", "file_path"):
                raw = args.get(key)
                if isinstance(raw, str) and "/reference/" not in raw.replace("\\", "/"):
                    suffix = _normalize_suffix(raw)
                    if suffix:
                        output_types.add(suffix)
    return output_types


def mentioned_file_types(task: str) -> set[str]:
    return {match.group(1).lower() for match in FILE_SUFFIX_RE.finditer(task)}


def infer_output_types(task: str, evaluation: list[dict[str, object]]) -> set[str]:
    outputs = evaluator_output_types(evaluation)
    text = task.lower()
    mentioned = mentioned_file_types(task)
    for suffix in mentioned:
        marker = suffix.lstrip(".")
        if re.search(
            rf"(?i)(save|create|generate|write|convert|export|rename|email|send)"
            rf".{{0,48}}{re.escape(marker)}",
            text,
        ):
            outputs.add(suffix)
    if "send email" in text or "send an email" in text or "email to" in text:
        outputs.add(".eml")
    if ("calendar event" in text or "add event" in text) and (
        "save" in text or "create" in text or "add" in text
    ):
        outputs.add(".ics")
    return outputs


def infer_apps(
    task: str,
    input_types: set[str],
    output_types: set[str],
    evaluators: list[str],
) -> set[str]:
    text = task.lower()
    apps = {
        TYPE_TO_APP[suffix] for suffix in input_types if suffix in TYPE_TO_APP
    }
    for suffix in output_types:
        if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
            apps.add("pdf")
        elif suffix in TYPE_TO_APP:
            apps.add(TYPE_TO_APP[suffix])
    keyword_rules = {
        "calendar": ("calendar", "schedule a meeting", "schedule meeting", "event"),
        "email": ("email", "mail to", "send to"),
        "excel": ("excel", "spreadsheet", "worksheet"),
        "word": ("word file", "word document", "docx"),
        "pdf": ("pdf",),
        "ocr": ("ocr", "scan ", "scanned", "handwritten", "extract text from image"),
        "shell": (
            "rename ",
            "move ",
            "folder",
            "directory",
            "delete file",
            "duplicate ",
        ),
        "llm": (
            "summarize",
            "analyse",
            "analyze",
            "suggest",
            "prediction",
            "write a report",
            "generate a report",
        ),
    }
    for app, needles in keyword_rules.items():
        if any(needle in text for needle in needles):
            apps.add(app)
    if any(name == "evaluate_calendar_no_overlap" for name in evaluators):
        apps.add("calendar")
    return apps


def infer_operations(
    task: str, input_types: set[str], output_types: set[str], apps: set[str]
) -> set[str]:
    text = task.lower()
    operations: set[str] = set()
    for suffix in input_types:
        app = TYPE_TO_APP.get(suffix)
        if app in {"excel", "word", "pdf"}:
            operations.add(f"{app}.read_file")
        elif app == "email":
            operations.add("email.read_email")
        elif app == "calendar":
            operations.add("calendar.list_events")
        elif app == "ocr":
            operations.add("ocr.recognize_file")
        elif suffix in {".txt", ".md"}:
            operations.add("shell.command")
    for suffix in output_types:
        app = TYPE_TO_APP.get(suffix)
        if app == "excel":
            operations.add("excel.create_or_update_file")
        elif app == "word":
            operations.add("word.create_or_update_file")
        elif app == "pdf":
            source_apps = {TYPE_TO_APP.get(item) for item in input_types}
            if "word" in source_apps:
                operations.add("word.convert_to_pdf")
            elif "excel" in source_apps:
                operations.add("excel.convert_to_pdf")
            else:
                operations.add("pdf.create_or_transform")
        elif app == "email":
            operations.add("email.send_email")
        elif app == "calendar":
            operations.add("calendar.create_event")
        elif app == "ocr":
            operations.add("pdf.convert_to_image")
        else:
            operations.add("shell.command")
    if "delete event" in text:
        operations.add("calendar.delete_event")
    if any(term in text for term in ("rename ", "move ", "delete file", "folder", "directory")):
        operations.add("shell.command")
    if "ocr" in apps and any(
        term in text for term in ("scan ", "scanned", "handwritten", "extract text")
    ):
        operations.add("ocr.recognize_file")
    if "llm" in apps:
        operations.add("llm.complete_text")
    return operations


def infer_chain(input_types: set[str], output_types: set[str]) -> str:
    input_apps = sorted(
        {TYPE_TO_APP.get(suffix, "text") for suffix in input_types}
    )
    output_apps = sorted(
        {TYPE_TO_APP.get(suffix, "text") for suffix in output_types}
    )
    left = "+".join(input_apps) if input_apps else "no_file_input"
    right = "+".join(output_apps) if output_apps else "answer_or_in_place"
    return f"{left} -> {right}"


def conservative_coverage(
    input_types: set[str], output_types: set[str], operations: set[str]
) -> tuple[str, list[str]]:
    readable = {".txt", ".md", ".pdf"}
    producible = {".md", ".docx"}
    gaps: set[str] = set()
    for suffix in input_types:
        if suffix not in readable:
            gaps.add(f"read:{suffix}")
    for suffix in output_types:
        if suffix not in producible:
            gaps.add(f"write:{suffix}")
    unsupported_operations = {
        "calendar.create_event",
        "calendar.delete_event",
        "calendar.list_events",
        "email.read_email",
        "email.send_email",
        "excel.create_or_update_file",
        "excel.convert_to_pdf",
        "excel.read_file",
        "ocr.recognize_file",
        "pdf.convert_to_image",
        "pdf.create_or_transform",
        "word.convert_to_pdf",
        "word.read_file",
    }
    gaps.update(f"operation:{op}" for op in operations & unsupported_operations)
    if not gaps and output_types:
        return "near_reusable_not_verified", []
    has_reuse = bool(input_types & readable or output_types & producible)
    return ("partial" if has_reuse else "unsupported"), sorted(gaps)


def load_records(
    snapshot: Path, tracked_paths: list[str]
) -> list[TaskRecord]:
    inputs_by_group = group_input_types(tracked_paths)
    records: list[TaskRecord] = []
    for path in sorted(snapshot.glob("tasks/*/subtasks/*.json")):
        group = path.parents[1].name
        payload = json.loads(path.read_text(encoding="utf-8"))
        evaluation = payload.get("evaluation", [])
        evaluators = [
            str(item.get("function", "unknown"))
            for item in evaluation
            if isinstance(item, dict)
        ]
        task_text = str(payload.get("task", "")).strip()
        input_types = set(inputs_by_group.get(group, set()))
        output_types = infer_output_types(task_text, evaluation)
        apps = infer_apps(task_text, input_types, output_types, evaluators)
        operations = infer_operations(task_text, input_types, output_types, apps)
        coverage, gaps = conservative_coverage(input_types, output_types, operations)
        records.append(
            TaskRecord(
                task_id=group,
                subtask_id=path.stem,
                declared_app_count=int(group.split("-", 1)[0]),
                input_types=sorted(input_types),
                output_types=sorted(output_types),
                inferred_apps=sorted(apps),
                inferred_operations=sorted(operations),
                evaluator_types=sorted(evaluators),
                inferred_chain=infer_chain(input_types, output_types),
                conservative_coverage=coverage,
                coverage_gaps=gaps,
                task_file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    return records


def _counter(records: Iterable[TaskRecord], attr: str) -> Counter[str]:
    result: Counter[str] = Counter()
    for record in records:
        result.update(getattr(record, attr))
    return result


def build_summary(records: list[TaskRecord]) -> dict[str, object]:
    declared = Counter(str(record.declared_app_count) for record in records)
    coverage = Counter(record.conservative_coverage for record in records)
    chains = Counter(record.inferred_chain for record in records)
    return {
        "schema_version": "1.0",
        "analysis_kind": "offline_static_inference_not_runtime_tool_trace",
        "source": {
            "repository": "https://github.com/zlwang-cs/OfficeBench",
            "commit": PINNED_COMMIT,
        },
        "methodology": {
            "declared_app_count": "Exact value from task-id prefix.",
            "input_types": "Suffixes under each task group's tracked testbed tree.",
            "output_types": "Deterministic extraction from evaluator args and output-oriented task text.",
            "apps_and_operations": "Rule-based inference from file types, evaluator config and task text; not observed execution traces.",
            "coverage": "Conservative component mapping against current LocalDesk registered capabilities; not a benchmark result.",
        },
        "task_count": len(records),
        "declared_app_count_frequency": dict(sorted(declared.items())),
        "inferred_application_frequency": dict(_counter(records, "inferred_apps").most_common()),
        "inferred_operation_frequency": dict(
            _counter(records, "inferred_operations").most_common()
        ),
        "input_file_type_frequency": dict(
            _counter(records, "input_types").most_common()
        ),
        "output_product_type_frequency": dict(
            _counter(records, "output_types").most_common()
        ),
        "evaluator_type_frequency": dict(
            _counter(records, "evaluator_types").most_common()
        ),
        "inferred_cross_application_chain_frequency": dict(chains.most_common()),
        "conservative_localdesk_coverage": dict(coverage.most_common()),
        "task_catalog": {
            "file": "task_catalog.csv",
            "row_count": len(records),
            "fields": list(asdict(records[0]).keys()),
        },
    }


def validate_summary(summary: dict[str, object]) -> None:
    if summary["task_count"] != 300:
        raise StaticAnalysisError(
            f"Expected 300 task records, got {summary['task_count']}"
        )
    actual = summary["declared_app_count_frequency"]
    if actual != EXPECTED_TASK_COUNTS:
        raise StaticAnalysisError(
            f"Declared app count mismatch: expected {EXPECTED_TASK_COUNTS}, got {actual}"
        )


def write_csv(records: list[TaskRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(asdict(records[0]).keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = asdict(record)
            for key, value in row.items():
                if isinstance(value, list):
                    row[key] = "|".join(value)
            writer.writerow(row)


def _table(counter: dict[str, int], limit: int = 20) -> str:
    lines = ["| 项目 | 任务出现次数 |", "|---|---:|"]
    lines.extend(
        f"| `{key}` | {value} |" for key, value in list(counter.items())[:limit]
    )
    return "\n".join(lines)


def write_markdown(summary: dict[str, object], path: Path) -> None:
    apps = summary["inferred_application_frequency"]
    operations = summary["inferred_operation_frequency"]
    inputs = summary["input_file_type_frequency"]
    outputs = summary["output_product_type_frequency"]
    evaluators = summary["evaluator_type_frequency"]
    chains = summary["inferred_cross_application_chain_frequency"]
    coverage = summary["conservative_localdesk_coverage"]
    office_priority = (
        inputs.get(".xlsx", 0)
        + outputs.get(".xlsx", 0)
        + inputs.get(".csv", 0)
        + outputs.get(".csv", 0)
    )
    doc_priority = (
        inputs.get(".docx", 0)
        + outputs.get(".docx", 0)
        + inputs.get(".pdf", 0)
        + outputs.get(".pdf", 0)
    )
    mail_priority = inputs.get(".eml", 0) + outputs.get(".eml", 0)
    content = f"""# OfficeBench 300 条任务静态目录分析

> 数据源：[OfficeBench@{PINNED_COMMIT[:8]}](https://github.com/zlwang-cs/OfficeBench/tree/{PINNED_COMMIT})
> 分析类型：固定 commit 的完全离线静态分析。应用、操作和链路是规则推断，不是真实 Agent 工具调用 Trace；LocalDesk 覆盖是保守组件映射，不是 Benchmark 成绩。

## 1. 数据完整性

| 任务层级 | 官方任务数 | 本次读到 |
|---|---:|---:|
| 单应用 | 93 | {summary["declared_app_count_frequency"]["1"]} |
| 双应用 | 95 | {summary["declared_app_count_frequency"]["2"]} |
| 三应用 | 112 | {summary["declared_app_count_frequency"]["3"]} |
| 合计 | 300 | {summary["task_count"]} |

任务数来自 task ID 前缀，是官方确定数据。输入类型来自 Git tree 中的 `testbed`；输出类型来自 Evaluator 参数和明确的输出型任务措辞。

## 2. 推断应用频率

{_table(apps)}

## 3. 推断操作频率

{_table(operations)}

同一任务可能出现多个应用和多个操作，因此频率之和会超过 300。`create_or_update_file` 是静态分析归一名，不是新增 LocalDesk 产品工具。

## 4. 输入文件与输出产物

### 输入文件类型

{_table(inputs)}

### 输出产物类型

{_table(outputs)}

用于验证优先级的组合出现量（输入出现次数 + 输出出现次数）：

- Excel/CSV：**{office_priority}**
- DOCX/PDF：**{doc_priority}**
- EML/邮件产物：**{mail_priority}**

这三个数字衡量“有多少任务组涉及该类文件”，不是文件总数，也不是成功率。根据全量静态数据，Excel/CSV 与 DOCX/PDF 确实是高频办公边界；邮件也重复出现，但低于文档/表格，因此更适合先做可审计草稿产物而非真实账户发送。

## 5. Evaluator 类型

{_table(evaluators)}

OfficeBench 的主判定以文件存在、内容包含、精确匹配和 Excel 单元格值等确定性检查为主。后续 Adapter 应原样调用，不用 LocalDesk 自建判断替代。

## 6. 高频静态跨应用链路

{_table(chains, 25)}

链路按“测试床输入应用集合 → Evaluator/任务要求的输出应用集合”归一；它不能表示真实执行顺序，但可以显示高频信息流向。

## 7. LocalDesk 保守覆盖

{_table(coverage)}

覆盖规则只承认当前真实能力：

- 可读输入：TXT、Markdown、PDF；
- 可生成正式办公产物：Markdown、DOCX；
- 已有横切能力：Runtime、Policy、staging、Trace、确认与文件移动；
- 不把内部 DOCX 渲染 PDF 当作正式 PDF 产品工具；
- 不把通用 Coding `Bash` 当作 Desktop 产品能力；
- Excel/CSV、邮件、日历、OCR、DOCX 读取均按缺失处理。

因此 `near_reusable_not_verified` 也只表示组件接近，仍然没有 OfficeBench 官方运行结果。

## 8. 数据驱动的优先顺序

1. **Excel/CSV 结构化读写**：表格输入/输出和 Excel Evaluator 均高频，而且 LocalDesk 当前完全缺失，是最明显的通用缺口。
2. **DOCX/PDF 输入与正式转换**：已有 DOCX 生成和渲染基础，补读取/正式 PDF 交付可以复用较多现有代码。
3. **`.eml` 邮件草稿**：任务中反复出现，但应先生成标准草稿和附件，执行真实发送仍需独立确认。
4. **日历/ICS 与 OCR**：有稳定重复需求，但优先级应由频次和前述三项完成后的边际收益决定。

## 9. 真实性边界

- 本报告没有运行 Docker、模型或任何 OfficeBench 任务；
- 没有调用官方 Evaluator；
- 没有运行 3 条冻结 Eval；
- 频率来自静态目录、任务 JSON、Evaluator 配置和确定性规则；
- 机器可读明细位于 `evaluation/officebench/results/task_static_analysis.json` 和 `task_catalog.csv`。
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def run_analysis(snapshot: Path, output_dir: Path, report_path: Path) -> dict[str, object]:
    verify_snapshot(snapshot)
    paths = tracked_task_paths(snapshot)
    records = load_records(snapshot, paths)
    summary = build_summary(records)
    validate_summary(summary)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "task_static_analysis.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_csv(records, output_dir / "task_catalog.csv")
    write_markdown(summary, report_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/officebench/results"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/officebench_300_task_analysis.md"),
    )
    args = parser.parse_args()
    summary = run_analysis(
        args.snapshot.resolve(), args.output_dir.resolve(), args.report.resolve()
    )
    print(
        json.dumps(
            {
                "task_count": summary["task_count"],
                "declared_app_count_frequency": summary[
                    "declared_app_count_frequency"
                ],
                "status": "offline_static_analysis_only",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
