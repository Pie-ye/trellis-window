"""Read-only scanner for a Trellis project tree."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server.models import (
    ArtifactsOut,
    MdDocOut,
    SpecFileOut,
    SpecNodeOut,
    TaskDetailOut,
    TaskSummaryOut,
)
from server.readiness import compute_readiness

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MiB

MD_NAMES = ("prd.md", "design.md", "implement.md")


class ReaderError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _tasks_dir(project_root: Path) -> Path:
    return project_root / ".trellis" / "tasks"


def _spec_dir(project_root: Path) -> Path:
    return project_root / ".trellis" / "spec"


def _safe_under(root: Path, candidate: Path) -> Path:
    """Resolve candidate and ensure it stays under root."""
    root_res = root.resolve()
    cand_res = candidate.resolve()
    try:
        cand_res.relative_to(root_res)
    except ValueError as e:
        raise ReaderError("Path escapes allowed directory", status_code=400) from e
    return cand_res


def _read_text_limited(path: Path) -> tuple[str, bool]:
    data = path.read_bytes()
    truncated = False
    if len(data) > MAX_FILE_BYTES:
        data = data[:MAX_FILE_BYTES]
        truncated = True
    return data.decode("utf-8", errors="replace"), truncated


def _artifact_flags(task_dir: Path) -> ArtifactsOut:
    return ArtifactsOut(
        prd=(task_dir / "prd.md").is_file(),
        design=(task_dir / "design.md").is_file(),
        implement=(task_dir / "implement.md").is_file(),
        implementJsonl=(task_dir / "implement.jsonl").is_file(),
        checkJsonl=(task_dir / "check.jsonl").is_file(),
    )


def _load_task_json(task_dir: Path) -> tuple[dict[str, Any] | None, str | None, bool]:
    path = task_dir / "task.json"
    if not path.is_file():
        return None, None, False
    try:
        return json.loads(path.read_text(encoding="utf-8")), None, True
    except (json.JSONDecodeError, OSError) as e:
        return None, str(e), True


def list_active_tasks(project_root: str | Path) -> list[TaskSummaryOut]:
    root = Path(project_root).resolve()
    tasks = _tasks_dir(root)
    if not tasks.is_dir():
        return []

    results: list[TaskSummaryOut] = []
    for entry in sorted(tasks.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        if entry.name == "archive":
            continue
        results.append(summarize_task(root, entry.name))
    return results


def summarize_task(project_root: Path, dir_name: str) -> TaskSummaryOut:
    root = Path(project_root).resolve()
    task_dir = _safe_under(_tasks_dir(root), _tasks_dir(root) / dir_name)
    if not task_dir.is_dir():
        raise ReaderError(f"Task not found: {dir_name}", status_code=404)

    data, err, has_json = _load_task_json(task_dir)
    artifacts = _artifact_flags(task_dir)
    readiness = compute_readiness(
        has_task_json=has_json,
        artifacts=artifacts,
        parse_error=err,
    )

    data = data or {}
    return TaskSummaryOut(
        dirName=dir_name,
        id=data.get("id"),
        name=data.get("name"),
        title=data.get("title") or dir_name,
        status=data.get("status"),
        priority=data.get("priority"),
        assignee=data.get("assignee"),
        package=data.get("package"),
        scope=data.get("scope"),
        parent=data.get("parent"),
        children=list(data.get("children") or data.get("subtasks") or []),
        description=data.get("description"),
        notes=data.get("notes"),
        artifacts=artifacts,
        readiness=readiness,
        error=err,
    )


def get_task_detail(project_root: str | Path, dir_name: str) -> TaskDetailOut:
    root = Path(project_root).resolve()
    summary = summarize_task(root, dir_name)
    task_dir = _safe_under(_tasks_dir(root), _tasks_dir(root) / dir_name)

    documents: dict[str, MdDocOut] = {}
    for name in MD_NAMES:
        key = name.removesuffix(".md")
        path = task_dir / name
        if not path.is_file():
            documents[key] = MdDocOut(name=name, missing=True)
            continue
        content, truncated = _read_text_limited(path)
        documents[key] = MdDocOut(
            name=name, missing=False, content=content, truncated=truncated
        )

    raw, _, _ = _load_task_json(task_dir)
    return TaskDetailOut(**summary.model_dump(), documents=documents, rawTaskJson=raw)


def build_spec_tree(project_root: str | Path) -> SpecNodeOut | None:
    root = Path(project_root).resolve()
    spec = _spec_dir(root)
    if not spec.is_dir():
        return None
    return _walk_spec(spec, rel="")


def _walk_spec(dir_path: Path, rel: str) -> SpecNodeOut:
    children: list[SpecNodeOut] = []
    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        entries = []

    for entry in entries:
        if entry.name.startswith("."):
            continue
        child_rel = f"{rel}/{entry.name}".lstrip("/") if rel else entry.name
        if entry.is_dir():
            children.append(_walk_spec(entry, child_rel))
        elif entry.is_file():
            children.append(
                SpecNodeOut(name=entry.name, type="file", relPath=child_rel, children=None)
            )

    name = dir_path.name if rel else "spec"
    return SpecNodeOut(name=name, type="dir", relPath=rel or "", children=children)


def read_spec_file(project_root: str | Path, rel_path: str) -> SpecFileOut:
    if not rel_path or rel_path.strip() == "":
        raise ReaderError("path is required", status_code=400)

    # Normalize: reject absolute and parent segments before join
    cleaned = rel_path.replace("\\", "/").lstrip("/")
    if ".." in cleaned.split("/"):
        raise ReaderError("Invalid path", status_code=400)

    root = Path(project_root).resolve()
    spec_root = _spec_dir(root)
    if not spec_root.is_dir():
        raise ReaderError("No .trellis/spec directory", status_code=404)

    target = _safe_under(spec_root, spec_root / cleaned)
    if not target.is_file():
        raise ReaderError(f"Spec file not found: {cleaned}", status_code=404)

    content, truncated = _read_text_limited(target)
    return SpecFileOut(relPath=cleaned, content=content, truncated=truncated)
