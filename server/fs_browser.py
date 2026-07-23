"""Server-side directory browser for folder picker (LAN-safe alternative to OS dialog)."""

from __future__ import annotations

from pathlib import Path

from server.discover import SKIP_DIR_NAMES


class BrowseError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def browse_dir(path_str: str | None = None) -> dict:
    """List subdirectories of path (default: home)."""
    if path_str is None or str(path_str).strip() == "":
        current = Path.home().resolve()
    else:
        try:
            current = Path(path_str).expanduser().resolve(strict=True)
        except (OSError, FileNotFoundError) as e:
            raise BrowseError(f"Path does not exist: {path_str}") from e

    if not current.is_dir():
        raise BrowseError(f"Not a directory: {current}")

    parent = current.parent if current.parent != current else None
    children: list[dict] = []
    try:
        entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as e:
        raise BrowseError(f"Permission denied: {current}", status_code=403) from e
    except OSError as e:
        raise BrowseError(str(e)) from e

    for entry in entries:
        try:
            if not entry.is_dir() or entry.is_symlink():
                continue
        except OSError:
            continue
        name = entry.name
        if name in SKIP_DIR_NAMES:
            continue
        # hide most dot-dirs in browser; still allow navigating into known work roots
        if name.startswith(".") and name not in {".config"}:
            continue
        has_trellis = (entry / ".trellis").is_dir()
        children.append(
            {
                "name": name,
                "path": str(entry.resolve()),
                "hasTrellis": has_trellis,
            }
        )

    return {
        "path": str(current),
        "parent": str(parent) if parent is not None else None,
        "hasTrellis": (current / ".trellis").is_dir(),
        "entries": children,
    }
