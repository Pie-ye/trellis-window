from pathlib import Path

from server import config_store


def _trellis(p: Path):
    (p / ".trellis").mkdir(parents=True)


def test_remove_is_ui_only_and_survives_rescan(tmp_path, monkeypatch):
    monkeypatch.setenv("TRELLIS_WINDOW_CONFIG_DIR", str(tmp_path / "cfg"))
    ws = tmp_path / "ws"
    a = ws / "a"
    b = ws / "b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    _trellis(a)
    _trellis(b)

    r = config_store.scan_and_register(str(ws), replace=True)
    assert r["count"] == 2
    projects = config_store.list_projects()
    assert len(projects) == 2
    victim = projects[0]
    assert config_store.remove_project(victim.id) is True
    assert len(config_store.list_projects()) == 1
    # disk still there
    assert (Path(victim.path) / ".trellis").is_dir()

    r2 = config_store.scan_and_register(str(ws), replace=True)
    assert r2["count"] == 1
    assert r2["hiddenSkipped"] == 1
    assert all(p.path != victim.path for p in config_store.list_projects())

    config_store.unhide_all_paths()
    r3 = config_store.scan_and_register(str(ws), replace=True)
    assert r3["count"] == 2
