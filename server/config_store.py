"""XDG-backed project list and scan-root persistence."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from server.discover import DiscoverError, discover_trellis_projects
from server.models import ProjectOut, ProjectsFile, ScanRootOut

APP_NAME = "trellis-window"
CONFIG_FILENAME = "projects.json"


def config_dir() -> Path:
    """Return XDG config dir for this app (overridable via TRELLIS_WINDOW_CONFIG_DIR)."""
    override = os.environ.get("TRELLIS_WINDOW_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg).expanduser()
    else:
        base = Path.home() / ".config"
    return (base / APP_NAME).resolve()


def config_path() -> Path:
    return config_dir() / CONFIG_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _empty() -> ProjectsFile:
    return ProjectsFile(version=2, scanRoots=[], projects=[], hiddenPaths=[])


def load_projects() -> ProjectsFile:
    path = config_path()
    if not path.is_file():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # migrate v1 (projects only)
        if "scanRoots" not in data:
            data["scanRoots"] = []
        data.setdefault("version", 2)
        data.setdefault("hiddenPaths", [])
        return ProjectsFile.model_validate(data)
    except (json.JSONDecodeError, ValueError, OSError):
        return _empty()


def save_projects(store: ProjectsFile) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = store.model_dump()
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".projects.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def list_projects() -> list[ProjectOut]:
    return list(load_projects().projects)


def list_scan_roots() -> list[ScanRootOut]:
    return list(load_projects().scanRoots)


def get_project(project_id: str) -> ProjectOut | None:
    for p in load_projects().projects:
        if p.id == project_id:
            return p
    return None


class ConfigError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def add_project(path_str: str, label: str | None = None) -> ProjectOut:
    """Add a single Trellis project root (legacy / manual)."""
    raw = Path(path_str).expanduser()
    try:
        root = raw.resolve(strict=True)
    except (OSError, FileNotFoundError) as e:
        raise ConfigError(f"Path does not exist: {path_str}") from e

    if not root.is_dir():
        raise ConfigError(f"Not a directory: {root}")

    trellis = root / ".trellis"
    if not trellis.is_dir():
        raise ConfigError(f"No .trellis/ directory under: {root}")

    store = load_projects()
    abs_path = str(root)
    for existing in store.projects:
        if existing.path == abs_path:
            raise ConfigError(f"Project already added: {abs_path}", status_code=409)

    display = label.strip() if label and label.strip() else root.name
    project = ProjectOut(
        id=str(uuid.uuid4()),
        path=abs_path,
        label=display,
        addedAt=_now(),
        scanRoot=None,
        relPath=".",
    )
    store.projects.append(project)
    save_projects(store)
    return project


def scan_and_register(
    path_str: str,
    *,
    label: str | None = None,
    max_depth: int = 6,
    replace: bool = True,
) -> dict:
    """
    Scan a folder for all Trellis projects and persist them.

    When replace=True, drops previously discovered projects for this scan root
    (and if single-workspace UX, replaces entire project list).
    """
    try:
        discovered = discover_trellis_projects(path_str, max_depth=max_depth)
    except DiscoverError as e:
        raise ConfigError(e.message, status_code=e.status_code) from e

    if not discovered:
        raise ConfigError(
            f"在此資料夾下找不到任何 Trellis 專案（需含 .trellis/）：{path_str}"
        )

    root = Path(path_str).expanduser().resolve()
    abs_root = str(root)
    store = load_projects()
    hidden = set(store.hiddenPaths or [])
    # UI-only removals: skip hidden paths (disk files are never deleted)
    visible = [item for item in discovered if item["path"] not in hidden]
    if not visible:
        raise ConfigError(
            "掃描到的專案都已從清單隱藏。可「還原已隱藏」後再掃描，"
            "或移除的只是介面項目（磁碟檔案仍在）。"
        )

    now = _now()
    display = label.strip() if label and label.strip() else root.name

    # upsert scan root
    scan_id = None
    for sr in store.scanRoots:
        if sr.path == abs_root:
            scan_id = sr.id
            sr.label = display
            sr.lastScanAt = now
            sr.projectCount = len(visible)
            break
    if scan_id is None:
        scan_id = str(uuid.uuid4())
        store.scanRoots.append(
            ScanRootOut(
                id=scan_id,
                path=abs_root,
                label=display,
                addedAt=now,
                lastScanAt=now,
                projectCount=len(visible),
            )
        )

    new_projects = [
        ProjectOut(
            id=str(uuid.uuid4()),
            path=item["path"],
            label=item["label"],
            addedAt=now,
            scanRoot=abs_root,
            relPath=item.get("relPath"),
        )
        for item in visible
    ]

    if replace:
        # Keep manually-added projects (scanRoot is None) from other paths,
        # replace all from this scan root; also drop other scan roots' projects
        # for simpler "one workspace folder" UX when user re-scans.
        store.projects = [p for p in store.projects if p.scanRoot is None]
        # When user picks a folder as workspace, show only this scan's projects
        store.projects.extend(new_projects)
        # Keep only this scan root in UI focus (retain history of scanRoots lightly)
        for sr in store.scanRoots:
            if sr.path != abs_root:
                # leave history but projects only from latest scan
                pass
    else:
        existing_paths = {p.path for p in store.projects}
        for p in new_projects:
            if p.path not in existing_paths:
                store.projects.append(p)

    save_projects(store)
    return {
        "scanRoot": next(s.model_dump() for s in store.scanRoots if s.id == scan_id),
        "projects": [p.model_dump() for p in store.projects if p.scanRoot == abs_root],
        "count": len(visible),
        "hiddenSkipped": len(discovered) - len(visible),
    }


def remove_project(project_id: str) -> bool:
    """Remove from app list only — never deletes files on disk."""
    store = load_projects()
    target = next((p for p in store.projects if p.id == project_id), None)
    if not target:
        return False
    store.projects = [p for p in store.projects if p.id != project_id]
    if target.path not in store.hiddenPaths:
        store.hiddenPaths.append(target.path)
    for sr in store.scanRoots:
        if sr.path == target.scanRoot or (
            target.scanRoot is None and sr.path == target.path
        ):
            sr.projectCount = max(0, (sr.projectCount or 0) - 1)
    save_projects(store)
    return True


def clear_project_list() -> int:
    """Clear all projects from UI list (files untouched); hide their paths."""
    store = load_projects()
    n = len(store.projects)
    for p in store.projects:
        if p.path not in store.hiddenPaths:
            store.hiddenPaths.append(p.path)
    store.projects = []
    for sr in store.scanRoots:
        sr.projectCount = 0
    save_projects(store)
    return n


def unhide_all_paths() -> int:
    """Clear hidden list so the next scan can show projects again."""
    store = load_projects()
    n = len(store.hiddenPaths)
    store.hiddenPaths = []
    save_projects(store)
    return n


def remove_scan_root(scan_id: str) -> bool:
    store = load_projects()
    target = next((s for s in store.scanRoots if s.id == scan_id), None)
    if not target:
        return False
    store.scanRoots = [s for s in store.scanRoots if s.id != scan_id]
    store.projects = [p for p in store.projects if p.scanRoot != target.path]
    save_projects(store)
    return True
