import json
from pathlib import Path

import pytest

from server import config_store


@pytest.fixture()
def cfg_dir(tmp_path, monkeypatch):
    d = tmp_path / "cfg"
    monkeypatch.setenv("TRELLIS_WINDOW_CONFIG_DIR", str(d))
    return d


def _make_trellis_root(tmp_path: Path, name: str = "proj") -> Path:
    root = tmp_path / name
    (root / ".trellis").mkdir(parents=True)
    return root


def test_empty_load(cfg_dir):
    store = config_store.load_projects()
    assert store.projects == []


def test_add_and_list(cfg_dir, tmp_path):
    root = _make_trellis_root(tmp_path)
    p = config_store.add_project(str(root), label="Demo")
    assert p.label == "Demo"
    assert p.path == str(root.resolve())
    listed = config_store.list_projects()
    assert len(listed) == 1
    assert listed[0].id == p.id

    data = json.loads((cfg_dir / "projects.json").read_text(encoding="utf-8"))
    assert data["version"] == 2
    assert data["projects"][0]["path"] == str(root.resolve())


def test_reject_no_trellis(cfg_dir, tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    with pytest.raises(config_store.ConfigError) as ei:
        config_store.add_project(str(bare))
    assert ei.value.status_code == 400
    assert "No .trellis" in ei.value.message


def test_reject_missing_path(cfg_dir, tmp_path):
    with pytest.raises(config_store.ConfigError):
        config_store.add_project(str(tmp_path / "nope"))


def test_duplicate_path(cfg_dir, tmp_path):
    root = _make_trellis_root(tmp_path)
    config_store.add_project(str(root))
    with pytest.raises(config_store.ConfigError) as ei:
        config_store.add_project(str(root))
    assert ei.value.status_code == 409


def test_remove(cfg_dir, tmp_path):
    root = _make_trellis_root(tmp_path)
    p = config_store.add_project(str(root))
    assert config_store.remove_project(p.id) is True
    assert config_store.list_projects() == []
    assert config_store.remove_project(p.id) is False
