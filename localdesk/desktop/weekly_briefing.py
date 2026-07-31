"""Auditable weekly AI-news briefing workflow. It never sends email."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.workspace import DesktopWorkspace
from localdesk.desktop.skills.office_artifacts import EmailDraftSkill
from localdesk.desktop.models import ActionKind, PlannedAction, Task
from localdesk.desktop.service import DesktopTaskService
from localdesk.desktop.browser import BrowserAdapter


@dataclass(frozen=True)
class NewsSource:
    category: str
    title: str
    published: str
    url: str
    summary: str
    value: str


@dataclass(frozen=True)
class NewsCard:
    card_id: str
    category: str
    title: str
    published: str
    url: str
    summary: str
    value: str


@dataclass(frozen=True)
class BriefingReview:
    approved: bool
    findings: list[str]
    blockers: list[str]


class WeeklyBriefingMemory:
    """Small, inspectable project memory: seen cards plus explicit user feedback."""

    def __init__(self, root: Path) -> None:
        self.path = root / "weekly_briefing_memory.json"

    def load(self) -> dict:
        if not self.path.exists():
            return {"seen": {}, "feedback": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, cards: Iterable[NewsCard], feedback: Iterable[dict] = ()) -> None:
        data = self.load()
        data["seen"].update({card.card_id: {"title": card.title, "published": card.published, "url": card.url} for card in cards})
        data["feedback"].extend(feedback)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


class WeeklyBriefingReviewer:
    def review(self, cards: list[NewsCard], start: date, end: date, pptx: Path | None = None, pdf: Path | None = None) -> BriefingReview:
        findings: list[str] = []; blockers: list[str] = []
        seen: set[str] = set()
        for card in cards:
            try: published = date.fromisoformat(card.published)
            except ValueError:
                blockers.append(f"日期格式无效: {card.title}"); continue
            if not start <= published <= end: blockers.append(f"超出本周时间范围: {card.title}")
            if not card.url.startswith("https://"): blockers.append(f"缺少 HTTPS 来源: {card.title}")
            if not card.summary or not card.value: blockers.append(f"资讯卡片不完整: {card.title}")
            key = _normalize(card.title)
            if key in seen: blockers.append(f"重复资讯: {card.title}")
            seen.add(key)
        if len(cards) < 3: blockers.append("少于三个研究方向的资讯")
        if pptx and (not pptx.is_file() or pptx.stat().st_size < 20_000): blockers.append("PPTX 未生成或过小")
        if pdf and (not pdf.is_file() or pdf.stat().st_size < 5_000): blockers.append("PDF 未生成或过小")
        if not blockers: findings.append("时间范围、来源、去重、PPTX/PDF 文件检查通过")
        return BriefingReview(not blockers, findings + blockers, blockers)


class WeeklyBriefingWorkflow:
    """Three role-isolated researchers, deterministic editor, delivery and trace."""
    def __init__(self, workspace: DesktopWorkspace, trace_store: TaskTraceStore, memory: WeeklyBriefingMemory | None = None, browser: BrowserAdapter | None = None) -> None:
        self.workspace, self.trace_store = workspace, trace_store
        self.memory = memory or WeeklyBriefingMemory(workspace.task_root.parent / "memory")
        self.reviewer = WeeklyBriefingReviewer()
        self.browser = browser

    def create_task(self, service: DesktopTaskService, start: date, end: date) -> Task:
        """Create a real Runtime task; delivery remains awaiting human confirmation."""
        task = service.create_task(f"创建本周AI资讯汇报（{start.isoformat()} 至 {end.isoformat()}）")
        final = self.workspace.output_root / f"本周AI资讯汇报_{end.isoformat()}.pptx"
        service.set_plan(task, "三路研究后生成本地 PPTX/PDF/邮件草稿；只在人工确认后交付。", [
            PlannedAction(
                action_id="deliver-weekly-pptx",
                skill="document.commit_pptx",
                kind=ActionKind.WRITE,
                args={"destination": str(final)},
                summary="将已审核的周报 PPTX 交付到输出目录",
                preview={"destination": str(final), "risk": "new_file_delivery"},
            )
        ])
        return task

    def run(self, task_id: str, start: date, end: date, sources: list[NewsSource], feedback: Iterable[dict] = ()) -> dict:
        task_dir = self.workspace.task_dir(task_id); staging = task_dir / "staging"; staging.mkdir(parents=True, exist_ok=True)
        self.trace_store.append(task_id, "weekly_briefing_started", {"start": start.isoformat(), "end": end.isoformat(), "research_agents": ["model", "agent_product", "industry"]})
        by_category = {name: [s for s in sources if s.category == name] for name in ("model", "agent_product", "industry")}
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="weekly-research") as pool:
            groups = list(pool.map(lambda item: self._research(item[0], item[1], start, end), by_category.items()))
        researched = [card for group, _reads in groups for card in group]
        source_reads = [read for _group, reads in groups for read in reads]
        for category, (group, reads) in zip(by_category, groups): self.trace_store.append(task_id, "research_agent_finished", {"agent": category, "card_count": len(group), "source_reads": reads})
        memory = self.memory.load(); cards = self._edit(researched, memory.get("seen", {}))
        self.trace_store.append(task_id, "editor_finished", {"input_cards": len(researched), "selected_cards": len(cards), "memory_seen": len(memory.get("seen", {}))})
        cards_path = staging / "news_cards.json"; cards_path.write_text(json.dumps([asdict(c) for c in cards], ensure_ascii=False, indent=2), encoding="utf-8")
        (staging / "source_reads.json").write_text(json.dumps(source_reads, ensure_ascii=False, indent=2), encoding="utf-8")
        markdown = staging / "weekly_briefing.md"; markdown.write_text(_markdown(start, end, cards), encoding="utf-8")
        pptx = staging / "本周AI资讯汇报.pptx"; self._build_pptx(cards_path, pptx, start, end)
        pdf = self._export_pdf(pptx)
        review = self.reviewer.review(cards, start, end, pptx, pdf)
        render_dir = staging / "ppt_render"; self._render_pptx(pptx, render_dir)
        overflow = self._overflow_check(pptx)
        if overflow: review = BriefingReview(False, review.findings + overflow, review.blockers + overflow)
        review_path = staging / "review.json"; review_path.write_text(json.dumps(asdict(review), ensure_ascii=False, indent=2), encoding="utf-8")
        confirm = staging / "人工确认页面.html"; confirm.write_text(_confirmation_html(cards, review, pptx, pdf), encoding="utf-8")
        draft = EmailDraftSkill(self.workspace).stage_draft(
            task_id,
            "AI资讯周报_未发送草稿.eml",
            ["review@example.com"],
            "本周AI资讯汇报（未发送草稿）",
            _email_body(cards),
            [pptx, pdf],
        )
        eml = Path(draft.staged_path)
        self.memory.save(cards, feedback)
        self.trace_store.append(task_id, "weekly_briefing_reviewed", {"review": asdict(review), "pptx": str(pptx), "pdf": str(pdf), "email_draft": str(eml), "render_dir": str(render_dir)})
        return {"cards": cards, "pptx": pptx, "pdf": pdf, "markdown": markdown, "review": review, "confirmation": confirm, "email": eml, "memory": self.memory.path}

    def _research(self, category: str, sources: list[NewsSource], start: date, end: date) -> tuple[list[NewsCard], list[dict]]:
        reads: list[dict] = []
        cards=[]
        for item in sources:
            try: published=date.fromisoformat(item.published)
            except ValueError: continue
            if start <= published <= end:
                if self.browser:
                    chunk = self.browser.open(item.url)
                    reads.append({"url": chunk.url, "title": chunk.title, "accessed_at": chunk.accessed_at, "content_hash": chunk.content_hash, "excerpt": chunk.excerpt(), "source_mode": getattr(self.browser, "source_mode", "live_https")})
                card_id=hashlib.sha256((item.title+item.url).encode()).hexdigest()[:16]
                cards.append(NewsCard(card_id, category, item.title, item.published, item.url, item.summary, item.value))
        return cards, reads

    @staticmethod
    def _edit(cards: list[NewsCard], seen: dict) -> list[NewsCard]:
        chosen=[]; titles=set()
        for card in sorted(cards, key=lambda c: (c.published, c.title), reverse=True):
            key=_normalize(card.title)
            if card.card_id in seen or key in titles: continue
            titles.add(key); chosen.append(card)
        # retain one freshest evidence-backed card per role for an executive weekly deck
        result=[]
        for category in ("model", "agent_product", "industry"):
            result.extend([c for c in chosen if c.category==category][:1])
        return result

    def _build_pptx(self, cards: Path, output: Path, start: date, end: date) -> None:
        source_script=Path(__file__).with_name("weekly_briefing_presentation.mjs")
        bundled_node=Path(r"C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe")
        node=str(bundled_node if bundled_node.is_file() else shutil.which("node"))
        skill_dir=Path(r"C:\Users\Admin\.codex\plugins\cache\openai-primary-runtime\presentations\26.730.11710\skills\presentations")
        setup=skill_dir / "container_tools" / "setup_artifact_tool_workspace.mjs"
        if not setup.is_file():
            raise RuntimeError("PPTX 生成环境缺少 artifact-tool workspace 初始化脚本")
        runtime_dir=output.parent / "artifact_tool_runtime"
        artifact_env = os.environ.copy()
        artifact_env.setdefault("HOME", str(Path.home()))
        setup_result=subprocess.run([node, str(setup), "--workspace", str(runtime_dir)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, env=artifact_env)
        if setup_result.returncode:
            raise RuntimeError("PPTX 生成环境初始化失败: " + setup_result.stderr[-800:])
        script=runtime_dir / source_script.name
        shutil.copy2(source_script, script)
        result=subprocess.run([node, str(script), str(cards), str(output), start.isoformat(), end.isoformat()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, env=artifact_env)
        if result.returncode: raise RuntimeError("PPTX 生成失败: " + (result.stderr or result.stdout or "unknown error")[-800:])

    @staticmethod
    def _export_pdf(pptx: Path) -> Path:
        out=pptx.parent / (pptx.stem+".pdf")
        try:
            import win32com.client  # type: ignore[import-not-found]
            app = win32com.client.DispatchEx("PowerPoint.Application")
            presentation = app.Presentations.Open(str(pptx.resolve()), WithWindow=False)
            try:
                presentation.SaveAs(str(out.resolve()), 32)  # ppSaveAsPDF
            finally:
                presentation.Close()
                app.Quit()
        except Exception as exc:
            raise RuntimeError(f"PowerPoint PDF 导出失败: {exc}") from exc
        if not out.exists():
            raise RuntimeError("PowerPoint PDF 导出失败：未生成 PDF 文件")
        return out

    @staticmethod
    def _render_pptx(pptx: Path, out: Path) -> None:
        out.mkdir(exist_ok=True)
        pdf=pptx.with_suffix(".pdf")
        if not pdf.is_file():
            raise RuntimeError("PPT 渲染检查失败：找不到刚导出的 PDF")
        import fitz
        document = fitz.open(pdf)
        try:
            for index, page in enumerate(document, start=1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pixmap.save(out / f"slide-{index}.png")
        finally:
            document.close()
        images=list(out.glob("slide-*.png"))
        if not images or any(image.stat().st_size < 1000 for image in images):
            raise RuntimeError("PPT 渲染检查未生成有效页面图")

    @staticmethod
    def _overflow_check(pptx: Path) -> list[str]:
        if not pptx.stat().st_size:
            return ["PPTX 为空"]
        checker=Path(r"C:\Users\Admin\.codex\plugins\cache\openai-primary-runtime\presentations\26.730.11710\skills\presentations\container_tools\slides_test.py")
        if not checker.is_file():
            return ["找不到 PPTX 结构检查工具"]
        artifact_python=Path(r"C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
        python=str(artifact_python if artifact_python.is_file() else Path(sys.executable))
        artifact_env = os.environ.copy()
        artifact_env.setdefault("HOME", str(Path.home()))
        result=subprocess.run([python, str(checker), str(pptx)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, env=artifact_env)
        return [] if result.returncode == 0 else ["PPTX 结构检查失败: " + (result.stdout + result.stderr)[-400:]]


def _normalize(text: str) -> str: return re.sub(r"\W+", "", text).lower()
def _markdown(start: date, end: date, cards: list[NewsCard]) -> str:
    lines=[f"# 本周AI资讯汇报\n\n时间范围：{start} 至 {end}\n"]
    for c in cards: lines += [f"## {c.title}", f"- 日期：{c.published}", f"- 来源：{c.url}", f"- 摘要：{c.summary}", f"- 价值判断：{c.value}\n"]
    return "\n".join(lines)
def _confirmation_html(cards, review, pptx, pdf):
    rows="".join(f"<li><b>{c.title}</b> — {c.url}</li>" for c in cards)
    return f"<html><meta charset='utf-8'><body><h1>本周AI资讯汇报：人工确认</h1><p>Reviewer: {'通过' if review.approved else '阻断'}</p><ul>{rows}</ul><p>待确认交付：{pptx.name}、{pdf.name}。邮件仅为本地草稿，不会发送。</p></body></html>"
def _email_body(cards: list[NewsCard]) -> str:
    return "附件为本地生成的周报 PPTX/PDF，尚未发送；请在人工确认后自行处理。\n\n" + "\n".join(f"- {c.title}: {c.url}" for c in cards)
