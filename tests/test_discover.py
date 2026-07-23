from pathlib import Path

import pytest

from server.discover import DiscoverError, discover_trellis_projects


def _trellis(path: Path) -> None:
    (path / ".trellis").mkdir(parents=True)


def test_discover_nested(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _trellis(root)
    child = root / "pkg-a"
    child.mkdir()
    _trellis(child)
    nested = root / "deep" / "pkg-b"
    nested.mkdir(parents=True)
    _trellis(nested)
    # junk
    (root / "node_modules" / "x" / ".trellis").mkdir(parents=True)

    found = discover_trellis_projects(str(root))
    paths = {p["path"] for p in found}
    assert str(root.resolve()) in paths
    assert str(child.resolve()) in paths
    assert str(nested.resolve()) in paths
    assert not any("node_modules" in p for p in paths)


def test_discover_none(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    assert discover_trellis_projects(str(d)) == []


def test_discover_missing():
    with pytest.raises(DiscoverError):
        discover_trellis_projects("/no/such/path/ever")
