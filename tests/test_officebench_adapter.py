from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evaluation.officebench.adapter import (
    PINNED_COMMIT,
    OfflineOfficeBenchAdapter,
    PathIsolationError,
    RuntimeBridgeResult,
    SnapshotValidationError,
)
from evaluation.officebench.analyze_tasks import (
    conservative_coverage,
    infer_apps,
    infer_operations,
    infer_output_types,
)


TASK_PAYLOAD = {
    "username": "Alice",
    "date": "2020-05-01",
    "weekday": "Friday",
    "time": "10:00 AM",
    "task": (
        "Create a new word file called random_paragraph.docx and add the "
        "content in random_paragraph.txt to it."
    ),
    "evaluation": [
        {
            "function": "evaluate_file_exist",
            "args": {"file": "data/random_paragraph.docx"},
        },
        {
            "function": "evaluate_contain",
            "args": {
                "doc_type": "docx",
                "file": "./data/random_paragraph.docx",
                "keywords": ["In the heart of the bustling city"],
            },
        },
    ],
}


def create_adapter_fixture(
    tmp_path: Path,
    *,
    task_hash: str | None = None,
    commit: str = PINNED_COMMIT,
) -> tuple[OfflineOfficeBenchAdapter, Path, Path]:
    snapshot = tmp_path / "snapshot"
    task_file = snapshot / "tasks" / "1-16" / "subtasks" / "0.json"
    task_file.parent.mkdir(parents=True)
    task_file.write_text(
        json.dumps(TASK_PAYLOAD, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    testbed = snapshot / "tasks" / "1-16" / "testbed" / "data"
    testbed.mkdir(parents=True)
    (testbed / "random_paragraph.txt").write_text(
        "In the heart of the bustling city.", encoding="utf-8"
    )
    (snapshot / "evaluation.py").write_text("# fixture\n", encoding="utf-8")
    (snapshot / "utils").mkdir()
    (snapshot / "utils" / "evaluate.py").write_text("# fixture\n", encoding="utf-8")

    actual_hash = hashlib.sha256(task_file.read_bytes()).hexdigest()
    manifest = tmp_path / "pilot_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source": {"commit": PINNED_COMMIT},
                "development_tasks": [
                    {
                        "id": "1-16/0",
                        "task_file_sha256": task_hash or actual_hash,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    run_root = tmp_path / "runs"
    adapter = OfflineOfficeBenchAdapter(
        snapshot,
        manifest,
        run_root,
        commit_resolver=lambda _: commit,
    )
    return adapter, snapshot, run_root


def test_wrong_commit_is_rejected(tmp_path: Path) -> None:
    adapter, _, _ = create_adapter_fixture(tmp_path, commit="0" * 40)

    with pytest.raises(SnapshotValidationError, match="commit mismatch"):
        adapter.load_task()


def test_wrong_task_hash_is_rejected(tmp_path: Path) -> None:
    adapter, _, _ = create_adapter_fixture(tmp_path, task_hash="f" * 64)

    with pytest.raises(SnapshotValidationError, match="task hash mismatch"):
        adapter.load_task()


def test_task_and_subtask_path_escape_is_rejected(tmp_path: Path) -> None:
    adapter, _, _ = create_adapter_fixture(tmp_path)

    with pytest.raises(PathIsolationError, match="invalid task_id"):
        adapter.load_task("../1-16", "0")
    with pytest.raises(PathIsolationError, match="invalid subtask_id"):
        adapter.load_task("1-16", "../../0")


def test_run_root_cannot_overlap_official_snapshot(tmp_path: Path) -> None:
    _, snapshot, _ = create_adapter_fixture(tmp_path)
    manifest = tmp_path / "pilot_manifest.json"

    with pytest.raises(PathIsolationError, match="must not overlap"):
        OfflineOfficeBenchAdapter(
            snapshot,
            manifest,
            snapshot / "runs",
            commit_resolver=lambda _: PINNED_COMMIT,
        )


def test_input_staging_and_artifact_directories_are_isolated(tmp_path: Path) -> None:
    adapter, _, _ = create_adapter_fixture(tmp_path)
    task = adapter.load_task()

    workspace = adapter.prepare_local_contract_workspace(task)

    inputs = Path(workspace.inputs)
    staging = Path(workspace.staging)
    artifacts = Path(workspace.artifacts)
    assert len({inputs.resolve(), staging.resolve(), artifacts.resolve()}) == 3
    assert (inputs / "data" / "random_paragraph.txt").is_file()
    assert not list(staging.iterdir())
    assert not list(artifacts.iterdir())
    assert not (Path(workspace.root) / "reference").exists()


def test_officebench_fields_are_converted_to_localdesk_input(tmp_path: Path) -> None:
    adapter, _, _ = create_adapter_fixture(tmp_path)
    task = adapter.load_task()
    converted = adapter.to_localdesk_input(task, adapter.workspace_for(task))

    assert converted.benchmark == "OfficeBench"
    assert converted.benchmark_commit == PINNED_COMMIT
    assert converted.benchmark_task_id == "1-16/0"
    assert converted.user_query == TASK_PAYLOAD["task"]
    assert converted.actor == "Alice"
    assert converted.simulated_clock == {
        "date": "2020-05-01",
        "weekday": "Friday",
        "time": "10:00 AM",
    }
    assert converted.required_artifacts == ["random_paragraph.docx"]


def test_dry_run_has_no_runtime_or_formal_output_side_effects(tmp_path: Path) -> None:
    adapter, _, run_root = create_adapter_fixture(tmp_path)
    formal_output = tmp_path / "formal-output"
    formal_output.mkdir()
    sentinel = formal_output / "keep.txt"
    sentinel.write_text("unchanged", encoding="utf-8")

    result = adapter.dry_run(command_finder=lambda _: None)

    assert result.runtime_called is False
    assert result.filesystem_prepared is False
    assert not run_root.exists()
    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert list(formal_output.iterdir()) == [sentinel]


def test_missing_official_environment_returns_clear_blocked_reason(
    tmp_path: Path,
) -> None:
    adapter, _, _ = create_adapter_fixture(tmp_path)

    result = adapter.dry_run(command_finder=lambda _: None)

    assert result.status == "blocked_official_environment"
    assert result.evaluator_probe.available is False
    assert result.evaluator_probe.blocked_reasons == ["docker_command_not_found"]
    assert "official evaluator" in result.note


def test_local_contract_bridge_is_explicitly_not_officebench_result(
    tmp_path: Path,
) -> None:
    adapter, _, _ = create_adapter_fixture(tmp_path)
    task = adapter.load_task()
    workspace = adapter.prepare_local_contract_workspace(task)

    class FixtureBridge:
        calls = 0

        def invoke(self, converted, prepared):
            self.calls += 1
            assert converted.benchmark_task_id == "1-16/0"
            assert prepared == workspace
            return RuntimeBridgeResult(
                status="fixture_only",
                artifacts=[],
                details={"model_called": False},
            )

    bridge = FixtureBridge()
    result = adapter.invoke_local_contract_bridge(task, workspace, bridge)

    assert bridge.calls == 1
    assert result.status == "fixture_only"
    trace = Path(workspace.trace).read_text(encoding="utf-8")
    assert "local_contract_test_not_officebench_result" in trace


def test_static_rules_keep_office_outputs_and_coverage_conservative() -> None:
    evaluation = TASK_PAYLOAD["evaluation"]
    outputs = infer_output_types(TASK_PAYLOAD["task"], evaluation)
    apps = infer_apps(TASK_PAYLOAD["task"], {".txt"}, outputs, [
        "evaluate_file_exist",
        "evaluate_contain",
    ])
    operations = infer_operations(TASK_PAYLOAD["task"], {".txt"}, outputs, apps)
    coverage, gaps = conservative_coverage({".txt"}, outputs, operations)

    assert outputs == {".docx"}
    assert "word" in apps
    assert "word.create_or_update_file" in operations
    assert coverage == "near_reusable_not_verified"
    assert gaps == []
