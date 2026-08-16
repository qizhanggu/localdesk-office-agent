from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class CitableEvidence(Protocol):
    def citation(self) -> str: ...


@dataclass(frozen=True)
class ReviewResult:
    approved: bool
    findings: list[str]
    warnings: list[str]
    blockers: list[str]


class DeterministicReviewer:
    """不依赖 LLM 的交付前检查；不能批准或扩大任何高风险动作。"""

    _SENSITIVE_PATTERNS = (
        r"api[_-]?key\s*[:=]",
        r"authorization:\s*bearer",
        r"password\s*[:=]",
        r"access[_-]?token\s*[:=]",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    )

    def review_markdown(self, path: str, evidence: list[CitableEvidence]) -> ReviewResult:
        text = Path(path).read_text(encoding="utf-8")
        warnings: list[str] = []
        blockers: list[str] = []
        if not text.strip():
            blockers.append("草稿为空")
        if "## Sources" not in text:
            warnings.append("草稿缺少 Sources 章节")
        if not evidence:
            warnings.append("没有可用于交付的本地或网页证据")
        for item in evidence:
            if item.citation() not in text:
                warnings.append(f"草稿缺少证据引用: {item.citation()}")
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in self._SENSITIVE_PATTERNS):
            blockers.append("草稿疑似包含敏感字段")
        return ReviewResult(approved=not blockers, findings=[*blockers, *warnings], warnings=warnings, blockers=blockers)
