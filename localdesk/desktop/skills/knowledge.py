from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document

from localdesk.desktop.workspace import DesktopWorkspace

_SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf", ".docx"}
_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    source_path: str
    locator: str
    text: str

    def citation(self) -> str:
        return f"{self.source_path} ({self.locator})"


class KnowledgeSkill:
    """轻量、可追踪的本地资料检索；不构建独立向量数据库。"""

    def __init__(self, workspace: DesktopWorkspace, chunk_lines: int = 24) -> None:
        self.workspace = workspace
        self.chunk_lines = chunk_lines
        self._chunks: list[SourceChunk] = []

    def index(self) -> int:
        chunks: list[SourceChunk] = []
        for root in self.workspace.read_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
                    continue
                resolved = path.resolve(strict=False)
                if not self.workspace.can_read(resolved):
                    continue
                relative = resolved.relative_to(root).as_posix()
                if resolved.suffix.lower() == ".pdf":
                    chunks.extend(self._pdf_chunks(resolved, relative))
                elif resolved.suffix.lower() == ".docx":
                    chunks.extend(self._docx_chunks(resolved, relative))
                else:
                    chunks.extend(self._text_chunks(resolved, relative))
        self._chunks = chunks
        return len(chunks)

    def search(self, query: str, limit: int = 5) -> list[SourceChunk]:
        tokens = _tokens(query)
        scored = [(sum(chunk.text.lower().count(token) for token in tokens), chunk) for chunk in self._chunks]
        scored = [item for item in scored if item[0]]
        scored.sort(key=lambda item: (-item[0], item[1].source_path, item[1].locator))
        return [chunk for _, chunk in scored[:limit]]

    def _text_chunks(self, path: Path, relative: str) -> list[SourceChunk]:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        result: list[SourceChunk] = []
        for offset in range(0, len(lines), self.chunk_lines):
            part = "\n".join(lines[offset : offset + self.chunk_lines]).strip()
            if part:
                start, end = offset + 1, min(offset + self.chunk_lines, len(lines))
                result.append(SourceChunk(f"{relative}:L{start}-L{end}", relative, f"lines {start}-{end}", part))
        return result

    def _pdf_chunks(self, path: Path, relative: str) -> list[SourceChunk]:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
        except Exception as exc:
            return [SourceChunk(f"{relative}:unreadable", relative, "unreadable PDF", f"[PDF text extraction failed: {exc}]")]
        result: list[SourceChunk] = []
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                result.append(SourceChunk(f"{relative}:P{index}", relative, f"page {index}", text))
        return result

    def _docx_chunks(self, path: Path, relative: str) -> list[SourceChunk]:
        try:
            document = Document(path)
        except Exception as exc:
            return [SourceChunk(f"{relative}:unreadable", relative, "unreadable DOCX", f"[DOCX text extraction failed: {exc}]")]
        result: list[SourceChunk] = []
        for index, paragraph in enumerate(document.paragraphs, start=1):
            text = paragraph.text.strip()
            if text:
                result.append(SourceChunk(f"{relative}:P{index}", relative, f"paragraph {index}", text))
        for table_index, table in enumerate(document.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                text = " | ".join(cell.text.strip() for cell in row.cells).strip(" |")
                if text:
                    result.append(SourceChunk(f"{relative}:T{table_index}R{row_index}", relative, f"table {table_index} row {row_index}", text))
        return result


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]
