"""Auditable weekly AI-news briefing workflow. It never sends email."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from localdesk.desktop.trace_store import TaskTraceStore
from localdesk.desktop.workspace import DesktopWorkspace
from localdesk.desktop.skills.office_artifacts import EmailDraftSkill
from localdesk.desktop.artifact_bundle import ArtifactBundleDelivery
from localdesk.desktop.models import Task
from localdesk.desktop.registry import create_desktop_registry
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
    evidence_quote: str = ""
    accessed_at: str = ""
    content_hash: str = ""
    source_mode: str = ""
    evidence_supported: bool = False
    event_id: str = ""
    related_urls: tuple[str, ...] = ()
    merged_card_ids: tuple[str, ...] = ()


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
            return {"seen": {}, "events": {}, "feedback": [], "preferences": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("seen", {})
        data.setdefault("events", {})
        data.setdefault("feedback", [])
        data.setdefault("preferences", {})
        return data

    def save(self, cards: Iterable[NewsCard], feedback: Iterable[dict] = ()) -> None:
        data = self.load()
        card_list = list(cards)
        feedback_list = list(feedback)
        data["seen"].update({card.card_id: {"title": card.title, "published": card.published, "url": card.url} for card in card_list})
        data["events"].update({card.event_id: {"title": card.title, "published": card.published, "urls": [card.url, *card.related_urls]} for card in card_list if card.event_id})
        by_id = {card.card_id: card for card in card_list}
        for item in feedback_list:
            card = by_id.get(str(item.get("card_id", "")))
            decision = str(item.get("decision", "")).casefold()
            if card and decision in {"keep", "delete"}:
                delta = 1 if decision == "keep" else -1
                data["preferences"][card.category] = int(data["preferences"].get(card.category, 0)) + delta
        data["feedback"].extend(feedback_list)
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
            if not card.evidence_quote or not card.accessed_at or len(card.content_hash) != 64:
                blockers.append(f"证据链字段不完整: {card.title}")
            elif not card.evidence_supported:
                blockers.append(f"摘要或标题未被引用片段支持: {card.title}")
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

    def create_task(self, service: DesktopTaskService, start: date, end: date, user_query: str | None = None) -> Task:
        """Create the Runtime task; approval is requested after files are reviewed."""
        return service.create_task(user_query or f"创建本周AI资讯汇报（{start.isoformat()} 至 {end.isoformat()}）")

    def run(self, service: DesktopTaskService, task: Task, start: date, end: date, sources: list[NewsSource], feedback: Iterable[dict] = ()) -> dict:
        task_id = task.task_id
        task_dir = self.workspace.task_dir(task_id); staging = task_dir / "staging"; staging.mkdir(parents=True, exist_ok=True)
        self.trace_store.append(task_id, "weekly_briefing_started", {"start": start.isoformat(), "end": end.isoformat(), "research_agents": ["model", "agent_product", "industry"]})
        by_category = {name: [s for s in sources if s.category == name] for name in ("model", "agent_product", "industry")}
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="weekly-research") as pool:
            groups = list(pool.map(lambda item: self._research(item[0], item[1], start, end), by_category.items()))
        researched = [card for group, _reads in groups for card in group]
        source_reads = [read for _group, reads in groups for read in reads]
        for category, (group, reads) in zip(by_category, groups): self.trace_store.append(task_id, "research_agent_finished", {"agent": category, "card_count": len(group), "source_reads": reads})
        memory = self.memory.load(); cards = self._edit(researched, memory.get("seen", {}), memory.get("events", {}), memory.get("preferences", {}))
        self.trace_store.append(task_id, "editor_finished", {"input_cards": len(researched), "selected_cards": len(cards), "memory_seen": len(memory.get("seen", {})), "memory_events": len(memory.get("events", {})), "preferences": memory.get("preferences", {}), "merged_cards": sum(len(card.merged_card_ids) for card in cards)})
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
        self.trace_store.append(task_id, "weekly_briefing_reviewed", {"review": asdict(review), "pptx": str(pptx), "pdf": str(pdf), "pdf_exporter": getattr(self, "_last_pdf_exporter", "test_or_unknown"), "email_draft": str(eml), "render_dir": str(render_dir)})
        if review.approved:
            registry = create_desktop_registry(service)
            delivery = ArtifactBundleDelivery(service, self.workspace, registry)
            artifacts = [
                delivery.capture(kind="pptx", staged_path=pptx, final_filename=f"本周AI资讯汇报_{end.isoformat()}.pptx", summary="交付已审核的 AI 资讯周报 PPTX"),
                delivery.capture(kind="pdf", staged_path=pdf, final_filename=f"本周AI资讯汇报_{end.isoformat()}.pdf", summary="交付已审核的 AI 资讯周报 PDF"),
                delivery.capture(kind="eml", staged_path=eml, final_filename=f"AI资讯周报_{end.isoformat()}_未发送草稿.eml", summary="交付明确标记为未发送的邮件草稿"),
            ]
            service.set_plan(
                task,
                "生成并审核周报后，人工确认一次，再交付 PPTX、PDF 和未发送邮件草稿。",
                [
                    delivery.action(action_id="weekly-commit-pptx", skill="document.commit_pptx", artifact=artifacts[0]),
                    delivery.action(action_id="weekly-commit-pdf", skill="document.commit_pdf", artifact=artifacts[1]),
                    delivery.action(action_id="weekly-commit-eml", skill="mail.commit_eml", artifact=artifacts[2]),
                ],
            )
        else:
            service.fail(task, "周报 Reviewer 未通过，未进入人工确认与正式交付。", event_type="weekly_briefing_review_failed")
        return {"task": task, "cards": cards, "pptx": pptx, "pdf": pdf, "markdown": markdown, "review": review, "confirmation": confirm, "email": eml, "memory": self.memory.path}

    def confirm_and_deliver(self, service: DesktopTaskService, task: Task, *, approved: bool) -> Task:
        registry = create_desktop_registry(service)
        return ArtifactBundleDelivery(service, self.workspace, registry).confirm_and_deliver(task, approved=approved)

    def _research(self, category: str, sources: list[NewsSource], start: date, end: date) -> tuple[list[NewsCard], list[dict]]:
        reads: list[dict] = []
        cards=[]
        for item in sources:
            try: published=date.fromisoformat(item.published)
            except ValueError: continue
            if start <= published <= end:
                quote = ""
                accessed_at = ""
                content_hash = ""
                source_mode = "preconfigured_without_source_read"
                evidence_supported = False
                if self.browser:
                    chunk = self.browser.open(item.url)
                    quote = _support_excerpt(chunk.text, item.summary)
                    accessed_at = chunk.accessed_at
                    content_hash = chunk.content_hash
                    source_mode = getattr(self.browser, "source_mode", "live_https")
                    evidence_supported = (
                        bool(content_hash)
                        and _normalize_evidence(item.summary) in _normalize_evidence(quote)
                        and _title_supported(item.title, f"{chunk.title} {chunk.text}")
                    )
                    reads.append({"url": chunk.url, "title": chunk.title, "accessed_at": chunk.accessed_at, "content_hash": chunk.content_hash, "excerpt": quote, "source_mode": source_mode, "evidence_supported": evidence_supported})
                card_id=hashlib.sha256((item.title+item.url).encode()).hexdigest()[:16]
                event_id=_event_id(item.title)
                cards.append(NewsCard(card_id, category, item.title, item.published, item.url, item.summary, item.value, quote, accessed_at, content_hash, source_mode, evidence_supported, event_id))
        return cards, reads

    @staticmethod
    def _edit(cards: list[NewsCard], seen: dict, seen_events: dict | None = None, preferences: dict | None = None) -> list[NewsCard]:
        seen_events = seen_events or {}
        preferences = preferences or {}
        candidates = [card for card in cards if card.card_id not in seen and (not card.event_id or card.event_id not in seen_events)]
        candidates.sort(key=lambda card: (int(preferences.get(card.category, 0)), card.evidence_supported, card.published, card.title), reverse=True)
        chosen: list[NewsCard] = []
        for card in candidates:
            match_index = next((index for index, existing in enumerate(chosen) if _same_event(existing, card)), None)
            if match_index is None:
                chosen.append(card)
                continue
            existing = chosen[match_index]
            chosen[match_index] = replace(
                existing,
                related_urls=tuple(dict.fromkeys([*existing.related_urls, card.url, *card.related_urls])),
                merged_card_ids=tuple(dict.fromkeys([*existing.merged_card_ids, card.card_id, *card.merged_card_ids])),
            )
        # retain one freshest evidence-backed card per role for an executive weekly deck
        result=[]
        for category in ("model", "agent_product", "industry"):
            result.extend([c for c in chosen if c.category==category][:1])
        return result

    def _build_pptx(self, cards: Path, output: Path, start: date, end: date) -> None:
        source_script=Path(__file__).with_name("weekly_briefing_presentation.mjs")
        bundled_node=Path(r"C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe")
        node=str(bundled_node if bundled_node.is_file() else shutil.which("node"))
        skill_dir=_presentation_skill_dir()
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

    def _export_pdf(self, pptx: Path) -> Path:
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
            self._last_pdf_exporter = "powerpoint_com"
        except Exception as exc:
            soffice = _find_soffice()
            if not soffice:
                raise RuntimeError(f"PPTX PDF 导出失败：PowerPoint={exc}；未找到 LibreOffice 回退") from exc
            try:
                self._export_pdf_with_libreoffice(pptx, out, soffice)
                self._last_pdf_exporter = "libreoffice_headless_fallback"
            except Exception as libreoffice_exc:
                raise RuntimeError(
                    f"PPTX PDF 导出失败：PowerPoint={exc}；LibreOffice={libreoffice_exc}"
                ) from exc
        if not out.exists():
            raise RuntimeError("PPTX PDF 导出失败：未生成 PDF 文件")
        return out

    @staticmethod
    def _export_pdf_with_libreoffice(pptx: Path, out: Path, soffice: str) -> None:
        profile = pptx.parent.parent / "libreoffice-pptx-profile"
        profile.mkdir(exist_ok=True)
        export_dir = pptx.parent / "pdf_export"
        export_dir.mkdir(exist_ok=True)
        converted_out = export_dir / out.name
        converted = subprocess.run(
            [
                sys.executable,
                "-m",
                "localdesk.desktop.pptx_pdf_export",
                "--soffice",
                soffice,
                "--pptx",
                str(pptx),
                "--output-dir",
                str(export_dir),
                "--profile",
                str(profile),
            ],
            capture_output=True,
            timeout=120,
        )
        for _ in range(60):
            if converted_out.is_file() and converted_out.stat().st_size:
                break
            time.sleep(0.25)
        if not converted_out.is_file() or not converted_out.stat().st_size:
            detail = (converted.stderr or converted.stdout or b"unknown error")[-600:].decode("utf-8", errors="replace")
            raise RuntimeError(f"LibreOffice exit={converted.returncode}: {detail}")
        shutil.copy2(converted_out, out)

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
        checker=_presentation_skill_dir() / "container_tools" / "slides_test.py"
        if not checker.is_file():
            return ["找不到 PPTX 结构检查工具"]
        artifact_python=Path(r"C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
        python=str(artifact_python if artifact_python.is_file() else Path(sys.executable))
        artifact_env = os.environ.copy()
        artifact_env.setdefault("HOME", str(Path.home()))
        result=subprocess.run([python, str(checker), str(pptx)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, env=artifact_env)
        return [] if result.returncode == 0 else ["PPTX 结构检查失败: " + (result.stdout + result.stderr)[-400:]]


def _normalize(text: str) -> str: return re.sub(r"\W+", "", text).lower()


_EVENT_STOPWORDS = {
    "a", "an", "and", "at", "by", "for", "from", "in", "into", "of",
    "on", "the", "to", "with", "new", "announces", "announced", "launches",
    "launched", "introduces", "introduced",
}


def _event_tokens(title: str) -> set[str]:
    """Return stable title features for conservative cross-source event matching."""
    normalized = " ".join(title.casefold().split())
    latin = {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 2 and token not in _EVENT_STOPWORDS
    }
    cjk_text = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    cjk_bigrams = {cjk_text[index : index + 2] for index in range(max(0, len(cjk_text) - 1))}
    return latin | cjk_bigrams


def _event_id(title: str) -> str:
    """Create a deterministic event fingerprint, not a general semantic embedding."""
    tokens = sorted(_event_tokens(title))
    canonical = " ".join(tokens) if tokens else _normalize(title)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _same_event(left: NewsCard, right: NewsCard) -> bool:
    """Conservatively merge title variants that describe the same event."""
    if left.event_id and right.event_id and left.event_id == right.event_id:
        return True
    left_normalized = _normalize(left.title)
    right_normalized = _normalize(right.title)
    if left_normalized == right_normalized:
        return True
    left_tokens = _event_tokens(left.title)
    right_tokens = _event_tokens(right.title)
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence_ratio = SequenceMatcher(None, left_normalized, right_normalized).ratio()
    if jaccard >= 0.60 or sequence_ratio >= 0.82:
        return True
    same_url = left.url.rstrip("/").casefold() == right.url.rstrip("/").casefold()
    return same_url and (jaccard >= 0.35 or sequence_ratio >= 0.55)


def _normalize_evidence(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _support_excerpt(text: str, claim: str, limit: int = 360) -> str:
    clean_text = " ".join(text.split())
    clean_claim = " ".join(claim.split())
    index = clean_text.casefold().find(clean_claim.casefold())
    if index < 0:
        return clean_text[:limit]
    start = max(0, index - 60)
    return clean_text[start : start + max(limit, len(clean_claim) + 120)]


def _title_supported(title: str, evidence: str) -> bool:
    tokens = [token for token in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", title.casefold()) if len(token) >= 3]
    if not tokens:
        return False
    normalized = evidence.casefold()
    return any(token in normalized for token in tokens)


def _presentation_skill_dir() -> Path:
    configured = os.environ.get("LOCALDESK_PRESENTATIONS_SKILL_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    cache = Path.home() / ".codex" / "plugins" / "cache" / "openai-primary-runtime" / "presentations"
    candidates = sorted(
        (path / "skills" / "presentations" for path in cache.glob("*") if path.is_dir()),
        key=lambda path: path.parent.parent.name,
        reverse=True,
    )
    for candidate in candidates:
        if (candidate / "container_tools" / "setup_artifact_tool_workspace.mjs").is_file():
            return candidate
    return cache / "missing" / "skills" / "presentations"


def _find_soffice() -> str | None:
    candidates = (
        r"D:\Apps\LibreOffice\program\soffice.com",
        r"C:\Program Files\LibreOffice\program\soffice.com",
        shutil.which("soffice"),
        r"D:\Apps\LibreOffice\program\soffice.exe",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
    )
    return next((str(Path(path)) for path in candidates if path and Path(path).is_file()), None)


def _markdown(start: date, end: date, cards: list[NewsCard]) -> str:
    lines=[f"# 本周AI资讯汇报\n\n时间范围：{start} 至 {end}\n"]
    for c in cards: lines += [f"## {c.title}", f"- 日期：{c.published}", f"- 来源：{c.url}", f"- 摘要：{c.summary}", f"- 价值判断：{c.value}\n"]
    return "\n".join(lines)
def _confirmation_html(cards, review, pptx, pdf):
    rows="".join(f"<li><b>{c.title}</b> — {c.url}</li>" for c in cards)
    return f"<html><meta charset='utf-8'><body><h1>本周AI资讯汇报：人工确认</h1><p>Reviewer: {'通过' if review.approved else '阻断'}</p><ul>{rows}</ul><p>待确认交付：{pptx.name}、{pdf.name}。邮件仅为本地草稿，不会发送。</p></body></html>"
def _email_body(cards: list[NewsCard]) -> str:
    return "附件为本地生成的周报 PPTX/PDF，尚未发送；请在人工确认后自行处理。\n\n" + "\n".join(f"- {c.title}: {c.url}" for c in cards)
