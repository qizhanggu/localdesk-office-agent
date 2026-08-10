import csv
import json
from pathlib import Path

import pytest

from evaluation.weekly_human_review import (
    HumanReviewError,
    export_review_sheet,
    summarize_review,
)


def _cards(path: Path, count: int = 6) -> None:
    categories = ("model", "agent_product", "industry")
    payload = [
        {
            "card_id": f"card-{index}",
            "category": categories[index % 3],
            "title": f"Title {index}",
            "published": "2026-08-10",
            "url": f"https://example.com/{index}",
            "summary": f"Summary {index}",
            "source_mode": "fixture",
            "evidence_supported": True,
        }
        for index in range(count)
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_export_is_balanced_deterministic_and_does_not_claim_feedback(tmp_path: Path) -> None:
    cards = tmp_path / "cards.json"
    first = tmp_path / "review-1.csv"
    second = tmp_path / "review-2.csv"
    _cards(cards)

    result = export_review_sheet(cards, first, sample_size=3)
    export_review_sheet(cards, second, sample_size=3)

    assert result["cards_sampled"] == 3
    assert result["human_feedback_recorded"] is False
    assert first.read_bytes() == second.read_bytes()
    with first.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["category"] for row in rows} == {"model", "agent_product", "industry"}
    assert all(not row["decision"] for row in rows)


def test_summary_counts_only_completed_human_rows(tmp_path: Path) -> None:
    cards = tmp_path / "cards.json"
    review = tmp_path / "review.csv"
    summary = tmp_path / "summary.json"
    _cards(cards, count=3)
    export_review_sheet(cards, review, sample_size=3)
    with review.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames
    rows[0].update(decision="keep", reviewer="human-1", reviewed_at="2026-08-10T10:00:00+08:00")
    rows[1].update(decision="delete", reviewer="human-1", reviewed_at="2026-08-10T10:01:00+08:00")
    rows[2].update(decision="modify", edited_summary="Human-edited summary", reviewer="human-1", reviewed_at="2026-08-10T10:02:00+08:00")
    with review.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    result = summarize_review(review, summary)

    assert result["reviewed_count"] == 3
    assert result["human_delete_or_modify_count"] == 2
    assert result["completion_rate"] == 1.0
    assert json.loads(summary.read_text(encoding="utf-8"))["modify_count"] == 1


def test_blank_review_keeps_human_metric_null(tmp_path: Path) -> None:
    cards = tmp_path / "cards.json"
    review = tmp_path / "review.csv"
    _cards(cards, count=2)
    export_review_sheet(cards, review)

    result = summarize_review(review, tmp_path / "summary.json")

    assert result["reviewed_count"] == 0
    assert result["human_delete_or_modify_count"] is None


def test_modify_without_new_summary_is_rejected(tmp_path: Path) -> None:
    cards = tmp_path / "cards.json"
    review = tmp_path / "review.csv"
    _cards(cards, count=1)
    export_review_sheet(cards, review)
    with review.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        row = next(reader)
        fields = reader.fieldnames
    row.update(decision="modify", reviewer="human-1", reviewed_at="2026-08-10T10:00:00+08:00")
    with review.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)

    with pytest.raises(HumanReviewError, match="没有提供不同的新摘要"):
        summarize_review(review, tmp_path / "summary.json")


def test_export_rejects_sample_larger_than_frozen_maximum(tmp_path: Path) -> None:
    cards = tmp_path / "cards.json"
    _cards(cards, count=2)

    with pytest.raises(HumanReviewError, match="1 到 20"):
        export_review_sheet(cards, tmp_path / "review.csv", sample_size=21)
