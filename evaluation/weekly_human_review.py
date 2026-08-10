"""Export auditable weekly-card review sheets and summarize real human feedback."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable


REVIEW_FIELDS = (
    "card_id",
    "category",
    "title",
    "published",
    "url",
    "source_mode",
    "evidence_supported",
    "original_summary",
    "decision",
    "edited_summary",
    "notes",
    "reviewer",
    "reviewed_at",
)
ALLOWED_DECISIONS = {"keep", "delete", "modify"}


class HumanReviewError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_cards(path: Path) -> list[dict[str, object]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise HumanReviewError("news_cards.json 必须是非空数组。")
    required = {"card_id", "category", "title", "published", "url", "summary"}
    cards: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict) or not required <= set(item):
            raise HumanReviewError(f"第 {index} 张卡片缺少必要字段。")
        card_id = str(item["card_id"])
        if not card_id or card_id in seen:
            raise HumanReviewError(f"card_id 为空或重复：{card_id}")
        seen.add(card_id)
        cards.append(item)
    return cards


def _sample(cards: Iterable[dict[str, object]], *, sample_size: int, seed: str) -> list[dict[str, object]]:
    if not 1 <= sample_size <= 20:
        raise HumanReviewError("sample_size 必须在 1 到 20 之间。")
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for card in cards:
        groups[str(card["category"])].append(card)
    for category, items in groups.items():
        items.sort(key=lambda item: hashlib.sha256(f"{seed}:{category}:{item['card_id']}".encode()).hexdigest())
    selected: list[dict[str, object]] = []
    categories = sorted(groups)
    while len(selected) < sample_size:
        added = False
        for category in categories:
            if groups[category] and len(selected) < sample_size:
                selected.append(groups[category].pop(0))
                added = True
        if not added:
            break
    return selected


def export_review_sheet(
    cards_path: Path,
    output_path: Path,
    *,
    sample_size: int = 20,
    seed: str = "localdesk-weekly-review-v1",
) -> dict[str, object]:
    cards_path = cards_path.resolve()
    output_path = output_path.resolve()
    if not 1 <= sample_size <= 20:
        raise HumanReviewError("sample_size 必须在 1 到 20 之间。")
    if output_path.exists():
        raise HumanReviewError(f"拒绝覆盖已有评审表：{output_path}")
    cards = _load_cards(cards_path)
    sample = _sample(cards, sample_size=min(sample_size, len(cards)), seed=seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        for card in sample:
            writer.writerow({
                "card_id": card["card_id"],
                "category": card["category"],
                "title": card["title"],
                "published": card["published"],
                "url": card["url"],
                "source_mode": card.get("source_mode", ""),
                "evidence_supported": str(bool(card.get("evidence_supported", False))).lower(),
                "original_summary": card["summary"],
                "decision": "",
                "edited_summary": "",
                "notes": "",
                "reviewer": "",
                "reviewed_at": "",
            })
    return {
        "status": "blank_review_sheet_created",
        "cards_input": len(cards),
        "cards_sampled": len(sample),
        "sampling": "category_round_robin_then_seeded_sha256",
        "seed": seed,
        "cards_sha256": _sha256(cards_path),
        "review_path": str(output_path),
        "human_feedback_recorded": False,
    }


def summarize_review(review_path: Path, output_path: Path) -> dict[str, object]:
    review_path = review_path.resolve()
    output_path = output_path.resolve()
    if output_path.exists():
        raise HumanReviewError(f"拒绝覆盖已有统计结果：{output_path}")
    with review_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REVIEW_FIELDS:
            raise HumanReviewError("评审表列结构与 v1 协议不一致。")
        rows = list(reader)
    if not rows:
        raise HumanReviewError("评审表没有资讯卡片。")

    counts = {"keep": 0, "delete": 0, "modify": 0, "unreviewed": 0}
    reviewed_ids: list[str] = []
    seen_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        card_id = row["card_id"].strip()
        if not card_id or card_id in seen_ids:
            raise HumanReviewError(f"第 {row_number} 行 card_id 为空或重复：{card_id}")
        seen_ids.add(card_id)
        decision = row["decision"].strip().casefold()
        if not decision:
            counts["unreviewed"] += 1
            continue
        if decision not in ALLOWED_DECISIONS:
            raise HumanReviewError(f"第 {row_number} 行 decision 无效：{decision}")
        if not row["reviewer"].strip() or not row["reviewed_at"].strip():
            raise HumanReviewError(f"第 {row_number} 行已评审但缺少 reviewer 或 reviewed_at。")
        try:
            datetime.fromisoformat(row["reviewed_at"].strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise HumanReviewError(f"第 {row_number} 行 reviewed_at 不是 ISO 时间。") from exc
        if decision == "modify":
            edited = row["edited_summary"].strip()
            if not edited or edited == row["original_summary"].strip():
                raise HumanReviewError(f"第 {row_number} 行选择 modify，但没有提供不同的新摘要。")
        counts[decision] += 1
        reviewed_ids.append(card_id)

    reviewed_count = len(reviewed_ids)
    payload = {
        "protocol_version": "weekly-human-review-v1",
        "review_sha256": _sha256(review_path),
        "sample_count": len(rows),
        "reviewed_count": reviewed_count,
        "completion_rate": round(reviewed_count / len(rows), 4),
        "keep_count": counts["keep"],
        "delete_count": counts["delete"],
        "modify_count": counts["modify"],
        "unreviewed_count": counts["unreviewed"],
        "human_delete_or_modify_count": (
            counts["delete"] + counts["modify"] if reviewed_count else None
        ),
        "reviewed_card_ids": reviewed_ids,
        "note": (
            "Statistics come from completed review rows."
            if reviewed_count
            else "No human feedback has been recorded; outcome metrics remain null."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or summarize an auditable weekly-card human review sheet.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--cards", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--sample-size", type=int, default=20)
    export_parser.add_argument("--seed", default="localdesk-weekly-review-v1")
    summary_parser = subparsers.add_parser("summarize")
    summary_parser.add_argument("--review", type=Path, required=True)
    summary_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "export":
        result = export_review_sheet(args.cards, args.output, sample_size=args.sample_size, seed=args.seed)
    else:
        result = summarize_review(args.review, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
