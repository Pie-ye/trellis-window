"""Discover Trellis project roots under a folder."""

from __future__ import annotations

import os
from pathlib import Path

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".cache",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        "vendor",
        ".trellis",  # do not recurse into trellis internals
    }
)


class DiscoverError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def discover_trellis_projects(
    root_str: str,
    *,
    max_depth: int = 6,
    max_projects: int = 200,
) -> list[dict]:
    """
    Walk root and return dirs that contain a `.trellis/` subdirectory.

    If root itself has `.trellis`, it is included. Nested projects are also found
    (e.g. monorepo root + child package each with `.trellis`).
    """
    try:
        root = Path(root_str).expanduser().resolve(strict=True)
    except (OSError, FileNotFoundError) as e:
        raise DiscoverError(f"Path does not exist: {root_str}") from e

    if not root.is_dir():
        raise DiscoverError(f"Not a directory: {root}")

    found: list[dict] = []

    def visit(current: Path, depth: int) -> None:
        if len(found) >= max_projects:
            return
        trellis = current / ".trellis"
        if trellis.is_dir():
            found.append(
                {
                    "path": str(current),
                    "label": current.name or str(current),
                    "relPath": (
                        str(current.relative_to(root))
                        if current != root
                        else "."
                    ),
                }
            )
            # Still recurse: child packages may have their own .trellis

        if depth >= max_depth:
            return

        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return

        for entry in entries:
            if len(found) >= max_projects:
                return
            if not entry.is_dir():
                continue
            name = entry.name
            if name in SKIP_DIR_NAMES or name.startswith("."):
                # allow non-skipped hidden only if we already check .trellis above
                if name != ".trellis" and name.startswith("."):
                    continue
                if name in SKIP_DIR_NAMES:
                    continue
            try:
                # skip symlinks that escape or loops
                if entry.is_symlink():
                    continue
            except OSError:
                continue
            visit(entry, depth + 1)

    visit(root, 0)

    # Prefer deeper labels uniqueness: use relPath when label collisions
    labels = [p["label"] for p in found]
    for p in found:
        if labels.count(p["label"]) > 1 and p["relPath"] != ".":
            p["label"] = p["relPath"].replace(os.sep, "/")

    return found
