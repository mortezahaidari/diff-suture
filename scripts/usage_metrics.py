#!/usr/bin/env python3
"""Measure local surgical-edit usage and estimate avoided rewrite payload."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
CHARACTERS_PER_TOKEN = 4
ESTIMATION_NOTE = (
    "Estimate uses four text characters per token and compares a three-context-line "
    "unified patch with rewriting each changed text file in full. It does not measure "
    "model input, context-window, billed, or account token usage."
)


class MetricsError(RuntimeError):
    """Raised when a metrics operation cannot be completed safely."""


def run_git(repository_root: Path, command_arguments: list[str]) -> str:
    completed_process = subprocess.run(
        ["git", *command_arguments],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed_process.returncode != 0:
        failure_description = completed_process.stderr.strip() or "Git command failed"
        raise MetricsError(failure_description)
    return completed_process.stdout.strip()


def find_repository_root() -> Path:
    completed_process = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed_process.returncode != 0:
        raise MetricsError("Run usage metrics from inside a Git repository.")
    return Path(completed_process.stdout.strip()).resolve()


def can_write_directory(candidate_directory: Path) -> bool:
    try:
        candidate_directory.mkdir(parents=True, exist_ok=True)
        probe_file = candidate_directory / f".write-probe-{uuid.uuid4().hex}"
        probe_file.write_text("probe", encoding="utf-8")
        probe_file.unlink()
        return True
    except OSError:
        return False


def resolve_metrics_directory(repository_root: Path) -> Path:
    override_directory = os.environ.get("SURGICAL_EDIT_METRICS_DIR")
    candidate_directories: list[Path] = []
    if override_directory:
        candidate_directories.append(Path(override_directory).expanduser().resolve())

    try:
        git_directory_text = run_git(repository_root, ["rev-parse", "--git-dir"])
        git_directory = Path(git_directory_text)
        if not git_directory.is_absolute():
            git_directory = repository_root / git_directory
        candidate_directories.append(git_directory.resolve() / "surgical-code-edits")
    except MetricsError:
        pass

    candidate_directories.append(repository_root / ".agent-data" / "surgical-code-edits")
    for candidate_directory in candidate_directories:
        if can_write_directory(candidate_directory):
            return candidate_directory

    raise MetricsError("No writable local directory is available for usage metrics.")


def resolve_target_file(repository_root: Path, target_text: str) -> tuple[str, Path]:
    target_file = Path(target_text)
    if not target_file.is_absolute():
        target_file = Path.cwd() / target_file
    resolved_target = target_file.resolve(strict=False)
    try:
        repository_relative_path = resolved_target.relative_to(repository_root)
    except ValueError as outside_repository_error:
        raise MetricsError(f"Target is outside the repository: {target_text}") from outside_repository_error

    if resolved_target.is_dir():
        raise MetricsError(f"Track files, not directories: {target_text}")
    return repository_relative_path.as_posix(), resolved_target


def validate_session_id(session_id: str) -> str:
    try:
        return str(uuid.UUID(session_id))
    except ValueError as invalid_session_error:
        raise MetricsError(f"Invalid session ID: {session_id}") from invalid_session_error


def load_json(json_file: Path) -> dict[str, Any]:
    try:
        parsed_content = json.loads(json_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as read_error:
        raise MetricsError(f"Cannot read metrics state: {json_file}") from read_error
    if not isinstance(parsed_content, dict):
        raise MetricsError(f"Metrics state is not an object: {json_file}")
    return parsed_content


def write_json(json_file: Path, payload: dict[str, Any]) -> None:
    json_file.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def session_directory(metrics_directory: Path, session_id: str) -> Path:
    return metrics_directory / "sessions" / validate_session_id(session_id)


def capture_target_files(
    repository_root: Path,
    active_session_directory: Path,
    session_metadata: dict[str, Any],
    target_texts: list[str],
) -> int:
    tracked_files = session_metadata.setdefault("tracked_files", [])
    known_paths = {
        tracked_file["repository_relative_path"]
        for tracked_file in tracked_files
        if isinstance(tracked_file, dict) and "repository_relative_path" in tracked_file
    }
    captured_count = 0

    for target_text in target_texts:
        repository_relative_path, resolved_target = resolve_target_file(repository_root, target_text)
        if repository_relative_path in known_paths:
            continue

        snapshot_name = f"{len(tracked_files):04d}.snapshot"
        target_existed = resolved_target.is_file()
        if resolved_target.exists() and not target_existed:
            raise MetricsError(f"Target is not a regular file: {target_text}")

        original_content = resolved_target.read_bytes() if target_existed else b""
        (active_session_directory / snapshot_name).write_bytes(original_content)
        tracked_files.append(
            {
                "repository_relative_path": repository_relative_path,
                "snapshot_name": snapshot_name,
                "target_existed": target_existed,
            }
        )
        known_paths.add(repository_relative_path)
        captured_count += 1

    return captured_count


def start_session(target_texts: list[str]) -> dict[str, Any]:
    repository_root = find_repository_root()
    metrics_directory = resolve_metrics_directory(repository_root)
    session_id = str(uuid.uuid4())
    active_session_directory = session_directory(metrics_directory, session_id)
    active_session_directory.mkdir(parents=True, exist_ok=False)
    session_metadata: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "repository_fingerprint": hashlib.sha256(str(repository_root).encode("utf-8")).hexdigest(),
        "tracked_files": [],
    }
    capture_target_files(
        repository_root,
        active_session_directory,
        session_metadata,
        target_texts,
    )
    write_json(active_session_directory / "session.json", session_metadata)
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "tracked_files": len(session_metadata["tracked_files"]),
        "message": "Capture additional files before editing them with the track command.",
    }


def track_session_files(session_id: str, target_texts: list[str]) -> dict[str, Any]:
    repository_root = find_repository_root()
    metrics_directory = resolve_metrics_directory(repository_root)
    active_session_directory = session_directory(metrics_directory, session_id)
    session_metadata_file = active_session_directory / "session.json"
    session_metadata = load_json(session_metadata_file)
    captured_count = capture_target_files(
        repository_root,
        active_session_directory,
        session_metadata,
        target_texts,
    )
    write_json(session_metadata_file, session_metadata)
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": validate_session_id(session_id),
        "newly_tracked_files": captured_count,
        "tracked_files": len(session_metadata["tracked_files"]),
    }


def count_changed_lines(original_lines: list[str], final_lines: list[str]) -> tuple[int, int]:
    added_lines = 0
    deleted_lines = 0
    line_matcher = difflib.SequenceMatcher(None, original_lines, final_lines, autojunk=False)
    for operation, original_start, original_end, final_start, final_end in line_matcher.get_opcodes():
        if operation in {"replace", "delete"}:
            deleted_lines += original_end - original_start
        if operation in {"replace", "insert"}:
            added_lines += final_end - final_start
    return added_lines, deleted_lines


def estimate_text_file_change(
    repository_relative_path: str,
    original_content: bytes,
    final_content: bytes,
) -> dict[str, int] | None:
    if b"\x00" in original_content or b"\x00" in final_content:
        return None
    try:
        original_text = original_content.decode("utf-8")
        final_text = final_content.decode("utf-8")
    except UnicodeDecodeError:
        return None

    original_lines = original_text.splitlines(keepends=True)
    final_lines = final_text.splitlines(keepends=True)
    added_lines, deleted_lines = count_changed_lines(original_lines, final_lines)
    unified_patch = "".join(
        difflib.unified_diff(
            original_lines,
            final_lines,
            fromfile=f"a/{repository_relative_path}",
            tofile=f"b/{repository_relative_path}",
            n=3,
        )
    )
    estimated_patch_tokens = math.ceil(len(unified_patch) / CHARACTERS_PER_TOKEN)
    projected_full_rewrite_tokens = math.ceil(len(final_text) / CHARACTERS_PER_TOKEN)
    projected_tokens_saved = max(projected_full_rewrite_tokens - estimated_patch_tokens, 0)
    return {
        "lines_added": added_lines,
        "lines_deleted": deleted_lines,
        "estimated_patch_tokens": estimated_patch_tokens,
        "projected_full_rewrite_tokens": projected_full_rewrite_tokens,
        "projected_tokens_saved": projected_tokens_saved,
    }


def load_usage_history(history_file: Path) -> list[dict[str, Any]]:
    if not history_file.exists():
        return []
    history_records: list[dict[str, Any]] = []
    for history_line in history_file.read_text(encoding="utf-8").splitlines():
        try:
            history_record = json.loads(history_line)
        except json.JSONDecodeError:
            continue
        if isinstance(history_record, dict):
            history_records.append(history_record)
    return history_records


def calculate_cumulative_metrics(history_records: list[dict[str, Any]]) -> dict[str, int | float]:
    completed_uses = len(history_records)
    cumulative_files_changed = sum(int(record.get("files_changed", 0)) for record in history_records)
    cumulative_lines_added = sum(int(record.get("lines_added", 0)) for record in history_records)
    cumulative_lines_deleted = sum(int(record.get("lines_deleted", 0)) for record in history_records)
    cumulative_patch_tokens = sum(int(record.get("estimated_patch_tokens", 0)) for record in history_records)
    cumulative_full_rewrite_tokens = sum(
        int(record.get("projected_full_rewrite_tokens", 0)) for record in history_records
    )
    cumulative_tokens_saved = sum(int(record.get("projected_tokens_saved", 0)) for record in history_records)
    average_tokens_saved = cumulative_tokens_saved / completed_uses if completed_uses else 0.0
    savings_percentage = (
        cumulative_tokens_saved / cumulative_full_rewrite_tokens * 100
        if cumulative_full_rewrite_tokens
        else 0.0
    )
    return {
        "completed_uses": completed_uses,
        "files_changed": cumulative_files_changed,
        "lines_added": cumulative_lines_added,
        "lines_deleted": cumulative_lines_deleted,
        "estimated_patch_tokens": cumulative_patch_tokens,
        "projected_full_rewrite_tokens": cumulative_full_rewrite_tokens,
        "projected_tokens_saved": cumulative_tokens_saved,
        "average_projected_tokens_saved_per_use": round(average_tokens_saved, 1),
        "projected_savings_percentage": round(savings_percentage, 1),
    }


def finish_session(session_id: str) -> dict[str, Any]:
    repository_root = find_repository_root()
    metrics_directory = resolve_metrics_directory(repository_root)
    active_session_directory = session_directory(metrics_directory, session_id)
    session_metadata = load_json(active_session_directory / "session.json")
    repository_fingerprint = hashlib.sha256(str(repository_root).encode("utf-8")).hexdigest()
    if session_metadata.get("repository_fingerprint") != repository_fingerprint:
        raise MetricsError("The metrics session belongs to a different repository.")

    current_metrics = {
        "files_observed": len(session_metadata.get("tracked_files", [])),
        "files_changed": 0,
        "binary_files_changed": 0,
        "lines_added": 0,
        "lines_deleted": 0,
        "estimated_patch_tokens": 0,
        "projected_full_rewrite_tokens": 0,
        "projected_tokens_saved": 0,
    }

    for tracked_file in session_metadata.get("tracked_files", []):
        repository_relative_path = tracked_file["repository_relative_path"]
        snapshot_file = active_session_directory / tracked_file["snapshot_name"]
        original_content = snapshot_file.read_bytes()
        current_file = repository_root / repository_relative_path
        final_content = current_file.read_bytes() if current_file.is_file() else b""
        if original_content == final_content:
            continue

        current_metrics["files_changed"] += 1
        text_file_metrics = estimate_text_file_change(
            repository_relative_path,
            original_content,
            final_content,
        )
        if text_file_metrics is None:
            current_metrics["binary_files_changed"] += 1
            continue
        for metric_name, metric_value in text_file_metrics.items():
            current_metrics[metric_name] += metric_value

    history_file = metrics_directory / "usage.jsonl"
    history_records = load_usage_history(history_file)
    usage_number = len(history_records) + 1
    completed_record = {
        "schema_version": SCHEMA_VERSION,
        "usage_number": usage_number,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        **current_metrics,
    }
    with history_file.open("a", encoding="utf-8") as history_stream:
        history_stream.write(json.dumps(completed_record, sort_keys=True) + "\n")
    history_records.append(completed_record)
    cumulative_metrics = calculate_cumulative_metrics(history_records)
    shutil.rmtree(active_session_directory)

    result = {
        "schema_version": SCHEMA_VERSION,
        "session_id": validate_session_id(session_id),
        "usage_number": usage_number,
        "current": current_metrics,
        "cumulative": cumulative_metrics,
        "estimation_note": ESTIMATION_NOTE,
    }
    write_json(metrics_directory / "latest.json", result)
    return result


def report_history() -> dict[str, Any]:
    repository_root = find_repository_root()
    metrics_directory = resolve_metrics_directory(repository_root)
    history_records = load_usage_history(metrics_directory / "usage.jsonl")
    return {
        "schema_version": SCHEMA_VERSION,
        "cumulative": calculate_cumulative_metrics(history_records),
        "estimation_note": ESTIMATION_NOTE,
    }


def cancel_session(session_id: str) -> dict[str, Any]:
    repository_root = find_repository_root()
    metrics_directory = resolve_metrics_directory(repository_root)
    active_session_directory = session_directory(metrics_directory, session_id)
    if not active_session_directory.exists():
        raise MetricsError(f"Metrics session does not exist: {session_id}")
    shutil.rmtree(active_session_directory)
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": validate_session_id(session_id),
        "cancelled": True,
    }


def print_human_summary(command_name: str, result: dict[str, Any]) -> None:
    if command_name == "start":
        print(f"Metrics session: {result['session_id']}")
        print(f"Files captured: {result['tracked_files']}")
        return
    if command_name == "track":
        print(f"Metrics session: {result['session_id']}")
        print(f"New files captured: {result['newly_tracked_files']}")
        print(f"Total files captured: {result['tracked_files']}")
        return
    if command_name == "cancel":
        print(f"Cancelled metrics session: {result['session_id']}")
        return

    if command_name == "finish":
        current_metrics = result["current"]
        print(f"Surgical edit use: #{result['usage_number']}")
        print(f"Files changed: {current_metrics['files_changed']} / {current_metrics['files_observed']}")
        print(f"Lines changed: +{current_metrics['lines_added']} / -{current_metrics['lines_deleted']}")
        print(f"Estimated patch tokens: ~{current_metrics['estimated_patch_tokens']}")
        print(f"Projected tokens saved: ~{current_metrics['projected_tokens_saved']}")

    cumulative_metrics = result["cumulative"]
    print(f"Completed uses: {cumulative_metrics['completed_uses']}")
    print(f"Cumulative projected tokens saved: ~{cumulative_metrics['projected_tokens_saved']}")
    print(
        "Average projected savings per use: "
        f"~{cumulative_metrics['average_projected_tokens_saved_per_use']}"
    )
    print(result["estimation_note"])


def build_argument_parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description="Record surgical edit usage and estimate avoided full-file rewrite tokens."
    )
    command_parsers = argument_parser.add_subparsers(dest="command_name", required=True)

    start_parser = command_parsers.add_parser("start", help="Capture files before editing.")
    start_parser.add_argument("files", nargs="+", help="Target files to capture.")
    start_parser.add_argument("--json", action="store_true", dest="use_json_output")

    track_parser = command_parsers.add_parser("track", help="Capture additional files before editing.")
    track_parser.add_argument("session_id")
    track_parser.add_argument("files", nargs="+")
    track_parser.add_argument("--json", action="store_true", dest="use_json_output")

    finish_parser = command_parsers.add_parser("finish", help="Measure changes and record a completed use.")
    finish_parser.add_argument("session_id")
    finish_parser.add_argument("--json", action="store_true", dest="use_json_output")

    report_parser = command_parsers.add_parser("report", help="Show cumulative usage history.")
    report_parser.add_argument("--json", action="store_true", dest="use_json_output")

    cancel_parser = command_parsers.add_parser("cancel", help="Delete an unfinished local session.")
    cancel_parser.add_argument("session_id")
    cancel_parser.add_argument("--json", action="store_true", dest="use_json_output")
    return argument_parser


def main() -> int:
    argument_parser = build_argument_parser()
    parsed_arguments = argument_parser.parse_args()
    try:
        if parsed_arguments.command_name == "start":
            result = start_session(parsed_arguments.files)
        elif parsed_arguments.command_name == "track":
            result = track_session_files(parsed_arguments.session_id, parsed_arguments.files)
        elif parsed_arguments.command_name == "finish":
            result = finish_session(parsed_arguments.session_id)
        elif parsed_arguments.command_name == "report":
            result = report_history()
        else:
            result = cancel_session(parsed_arguments.session_id)
    except MetricsError as metrics_error:
        print(f"usage_metrics.py: {metrics_error}", file=sys.stderr)
        return 2

    if parsed_arguments.use_json_output:
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print_human_summary(parsed_arguments.command_name, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
