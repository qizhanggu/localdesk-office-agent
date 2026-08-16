from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Protocol


PINNED_COMMIT = "b978b808667c32b52ce19a67ce1def1de9ae02b7"
SUPPORTED_DEV_TASK = "1-16/0"
_TASK_ID_RE = re.compile(r"[1-3]-\d+")
_SUBTASK_ID_RE = re.compile(r"\d+")


class AdapterError(RuntimeError):
    """Base class for an offline adapter contract failure."""


class SnapshotValidationError(AdapterError):
    pass


class PathIsolationError(AdapterError):
    pass


class OfficialEnvironmentBlocked(AdapterError):
    pass


@dataclass(frozen=True)
class PinnedTask:
    task_id: str
    subtask_id: str
    sha256: str

    @property
    def key(self) -> str:
        return f"{self.task_id}/{self.subtask_id}"


@dataclass(frozen=True)
class OfficeBenchTask:
    task_id: str
    subtask_id: str
    username: str
    date: str
    weekday: str
    time: str
    instruction: str
    evaluation: list[dict[str, object]]
    task_file: str
    task_sha256: str


@dataclass(frozen=True)
class AdapterWorkspace:
    root: str
    inputs: str
    staging: str
    artifacts: str
    trace: str


@dataclass(frozen=True)
class LocalDeskBenchmarkInput:
    benchmark: str
    benchmark_commit: str
    benchmark_task_id: str
    user_query: str
    actor: str
    simulated_clock: dict[str, str]
    input_root: str
    staging_root: str
    artifact_root: str
    trace_path: str
    required_artifacts: list[str]


@dataclass(frozen=True)
class EvaluatorProbe:
    available: bool
    blocked_reasons: list[str]
    entrypoint: str
    docker_path: str | None


@dataclass(frozen=True)
class DryRunResult:
    status: str
    experiment_version: str
    task: LocalDeskBenchmarkInput
    evaluator_probe: EvaluatorProbe
    runtime_called: bool
    filesystem_prepared: bool
    note: str


@dataclass(frozen=True)
class RuntimeBridgeResult:
    status: str
    artifacts: list[str]
    details: dict[str, object]


class RuntimeBridge(Protocol):
    """Narrow interface between benchmark metadata and the LocalDesk Runtime.

    Implementations may call LocalDesk, a deterministic fixture, or a future
    model-backed runner.  This adapter never chooses or constructs a model.
    """

    def invoke(
        self, task: LocalDeskBenchmarkInput, workspace: AdapterWorkspace
    ) -> RuntimeBridgeResult: ...


CommitResolver = Callable[[Path], str]
CommandFinder = Callable[[str], str | None]


def _default_commit_resolver(snapshot: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(snapshot), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode:
        raise SnapshotValidationError(
            "cannot resolve OfficeBench commit: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_component(value: str, pattern: re.Pattern[str], label: str) -> str:
    if not pattern.fullmatch(value):
        raise PathIsolationError(f"invalid {label}: {value!r}")
    return value


def _safe_child(root: Path, *parts: str) -> Path:
    base = root.resolve(strict=False)
    candidate = base.joinpath(*parts).resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise PathIsolationError(f"path escapes adapter root: {candidate}") from exc
    return candidate


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def load_pinned_dev_task(manifest_path: Path) -> PinnedTask:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_commit = str(payload.get("source", {}).get("commit", ""))
    if source_commit != PINNED_COMMIT:
        raise SnapshotValidationError(
            f"manifest commit mismatch: expected {PINNED_COMMIT}, got {source_commit}"
        )
    for item in payload.get("development_tasks", []):
        if item.get("id") == SUPPORTED_DEV_TASK:
            task_id, subtask_id = SUPPORTED_DEV_TASK.split("/")
            return PinnedTask(
                task_id=task_id,
                subtask_id=subtask_id,
                sha256=str(item["task_file_sha256"]),
            )
    raise SnapshotValidationError(
        f"manifest does not contain supported dev task {SUPPORTED_DEV_TASK}"
    )


class OfflineOfficeBenchAdapter:
    """Minimal, offline-only OfficeBench adapter for Dev task ``1-16/0``."""

    def __init__(
        self,
        snapshot_root: Path,
        manifest_path: Path,
        run_root: Path,
        *,
        experiment_version: str = "ob-b2a-v1",
        commit_resolver: CommitResolver = _default_commit_resolver,
    ) -> None:
        self.snapshot_root = snapshot_root.resolve(strict=False)
        self.manifest_path = manifest_path.resolve(strict=False)
        self.run_root = run_root.resolve(strict=False)
        if _is_within(self.run_root, self.snapshot_root) or _is_within(
            self.snapshot_root, self.run_root
        ):
            raise PathIsolationError(
                "run_root and official snapshot_root must not overlap"
            )
        self.experiment_version = _safe_component(
            experiment_version,
            re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*"),
            "experiment_version",
        )
        self.commit_resolver = commit_resolver
        self.pinned_task = load_pinned_dev_task(self.manifest_path)

    def validate_snapshot(self) -> None:
        actual = self.commit_resolver(self.snapshot_root)
        if actual != PINNED_COMMIT:
            raise SnapshotValidationError(
                f"OfficeBench commit mismatch: expected {PINNED_COMMIT}, got {actual}"
            )

    def load_task(
        self, task_id: str = "1-16", subtask_id: str = "0"
    ) -> OfficeBenchTask:
        task_id = _safe_component(task_id, _TASK_ID_RE, "task_id")
        subtask_id = _safe_component(subtask_id, _SUBTASK_ID_RE, "subtask_id")
        key = f"{task_id}/{subtask_id}"
        if key != self.pinned_task.key:
            raise SnapshotValidationError(
                f"B2A adapter supports only Dev task {self.pinned_task.key}, got {key}"
            )
        self.validate_snapshot()
        task_file = _safe_child(
            self.snapshot_root, "tasks", task_id, "subtasks", f"{subtask_id}.json"
        )
        if not task_file.is_file():
            raise SnapshotValidationError(f"official task JSON not found: {task_file}")
        actual_hash = _sha256(task_file)
        if actual_hash != self.pinned_task.sha256:
            raise SnapshotValidationError(
                "OfficeBench task hash mismatch: "
                f"expected {self.pinned_task.sha256}, got {actual_hash}"
            )
        payload = json.loads(task_file.read_text(encoding="utf-8"))
        required = ("username", "date", "weekday", "time", "task", "evaluation")
        missing = [key for key in required if key not in payload]
        if missing:
            raise SnapshotValidationError(
                "official task JSON missing fields: " + ", ".join(missing)
            )
        if not isinstance(payload["evaluation"], list):
            raise SnapshotValidationError("official task evaluation must be a list")
        return OfficeBenchTask(
            task_id=task_id,
            subtask_id=subtask_id,
            username=str(payload["username"]),
            date=str(payload["date"]),
            weekday=str(payload["weekday"]),
            time=str(payload["time"]),
            instruction=str(payload["task"]),
            evaluation=payload["evaluation"],
            task_file=str(task_file),
            task_sha256=actual_hash,
        )

    def workspace_for(self, task: OfficeBenchTask) -> AdapterWorkspace:
        root = _safe_child(
            self.run_root,
            self.experiment_version,
            task.task_id,
            task.subtask_id,
        )
        inputs = _safe_child(root, "inputs")
        staging = _safe_child(root, "staging")
        artifacts = _safe_child(root, "artifacts")
        trace = _safe_child(root, "trace", "adapter_trace.jsonl")
        if len({inputs, staging, artifacts}) != 3:
            raise PathIsolationError("input, staging and artifact roots must be isolated")
        return AdapterWorkspace(
            root=str(root),
            inputs=str(inputs),
            staging=str(staging),
            artifacts=str(artifacts),
            trace=str(trace),
        )

    def _required_artifacts(self, task: OfficeBenchTask) -> list[str]:
        artifacts: set[str] = set()
        for evaluation in task.evaluation:
            args = evaluation.get("args", {})
            if not isinstance(args, dict):
                continue
            for key in ("file", "result_file", "filepath", "file_path"):
                value = args.get(key)
                if not isinstance(value, str):
                    continue
                normalized = value.replace("\\", "/").lstrip("./")
                if "reference/" in normalized:
                    continue
                if normalized.startswith("data/"):
                    normalized = normalized.removeprefix("data/")
                name = Path(normalized).name
                if name:
                    artifacts.add(name)
        return sorted(artifacts)

    def to_localdesk_input(
        self, task: OfficeBenchTask, workspace: AdapterWorkspace
    ) -> LocalDeskBenchmarkInput:
        return LocalDeskBenchmarkInput(
            benchmark="OfficeBench",
            benchmark_commit=PINNED_COMMIT,
            benchmark_task_id=f"{task.task_id}/{task.subtask_id}",
            user_query=task.instruction,
            actor=task.username,
            simulated_clock={
                "date": task.date,
                "weekday": task.weekday,
                "time": task.time,
            },
            input_root=workspace.inputs,
            staging_root=workspace.staging,
            artifact_root=workspace.artifacts,
            trace_path=workspace.trace,
            required_artifacts=self._required_artifacts(task),
        )

    def probe_official_evaluator(
        self,
        task: OfficeBenchTask,
        *,
        command_finder: CommandFinder = shutil.which,
    ) -> EvaluatorProbe:
        reasons: list[str] = []
        entrypoint = _safe_child(self.snapshot_root, "evaluation.py")
        evaluate_module = _safe_child(self.snapshot_root, "utils", "evaluate.py")
        docker_path = command_finder("docker")
        testbed = _safe_child(
            self.snapshot_root, "tasks", task.task_id, "testbed"
        )
        if not entrypoint.is_file() or not evaluate_module.is_file():
            reasons.append("official_evaluator_source_missing")
        if docker_path is None:
            reasons.append("docker_command_not_found")
        if not testbed.is_dir():
            reasons.append("official_testbed_inputs_not_materialized")
        return EvaluatorProbe(
            available=not reasons,
            blocked_reasons=reasons,
            entrypoint=str(entrypoint),
            docker_path=docker_path,
        )

    def prepare_local_contract_workspace(
        self, task: OfficeBenchTask
    ) -> AdapterWorkspace:
        """Copy fixture/testbed inputs into an isolated local contract workspace.

        This is not an OfficeBench run.  It is useful for adapter contract tests
        only and deliberately excludes official ``reference`` files.
        """

        workspace = self.workspace_for(task)
        source = _safe_child(
            self.snapshot_root, "tasks", task.task_id, "testbed"
        )
        if not source.is_dir():
            raise OfficialEnvironmentBlocked(
                "official testbed inputs are not materialized in the sparse snapshot"
            )
        destination = Path(workspace.inputs)
        if Path(workspace.root).exists():
            raise PathIsolationError(
                f"adapter workspace already exists; refusing overwrite: {workspace.root}"
            )
        for path in source.rglob("*"):
            if path.is_symlink():
                raise PathIsolationError(f"testbed symlink is not allowed: {path}")
        destination.parent.mkdir(parents=True, exist_ok=False)
        shutil.copytree(source, destination)
        Path(workspace.staging).mkdir()
        Path(workspace.artifacts).mkdir()
        Path(workspace.trace).parent.mkdir()
        return workspace

    def invoke_local_contract_bridge(
        self,
        task: OfficeBenchTask,
        workspace: AdapterWorkspace,
        bridge: RuntimeBridge,
    ) -> RuntimeBridgeResult:
        result = bridge.invoke(self.to_localdesk_input(task, workspace), workspace)
        trace_path = Path(workspace.trace)
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "event_type": "local_contract_bridge_completed",
            "benchmark_task_id": f"{task.task_id}/{task.subtask_id}",
            "result": asdict(result),
            "truth_boundary": "local_contract_test_not_officebench_result",
        }
        with trace_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return result

    def dry_run(
        self,
        *,
        command_finder: CommandFinder = shutil.which,
    ) -> DryRunResult:
        task = self.load_task()
        workspace = self.workspace_for(task)
        converted = self.to_localdesk_input(task, workspace)
        probe = self.probe_official_evaluator(task, command_finder=command_finder)
        return DryRunResult(
            status="ready_for_local_contract"
            if probe.available
            else "blocked_official_environment",
            experiment_version=self.experiment_version,
            task=converted,
            evaluator_probe=probe,
            runtime_called=False,
            filesystem_prepared=False,
            note=(
                "Dry-run only: no model, Runtime bridge, official evaluator, "
                "task workspace or formal output was invoked or created."
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline dry-run for the OfficeBench Dev 1-16/0 adapter."
    )
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    adapter = OfflineOfficeBenchAdapter(
        snapshot_root=args.snapshot,
        manifest_path=args.manifest,
        run_root=args.run_root,
    )
    result = adapter.dry_run()
    payload = json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
