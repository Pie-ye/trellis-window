import json
from pathlib import Path

import pytest

from server.trellis_reader import (
    ReaderError,
    build_spec_tree,
    get_task_detail,
    list_active_tasks,
    read_spec_file,
)


def _seed_project(root: Path) -> None:
    tasks = root / ".trellis" / "tasks"
    (tasks / "archive" / "old").mkdir(parents=True)
    (tasks / "archive" / "old" / "task.json").write_text("{}", encoding="utf-8")

    t1 = tasks / "01-01-demo"
    t1.mkdir(parents=True)
    (t1 / "task.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "title": "Demo Task",
                "status": "planning",
                "priority": "P2",
                "assignee": "Pie-ye",
                "package": None,
            }
        ),
        encoding="utf-8",
    )
    (t1 / "prd.md").write_text("# PRD\n\nHello", encoding="utf-8")

    t2 = tasks / "01-02-broken"
    t2.mkdir()
    (t2 / "task.json").write_text("{not-json", encoding="utf-8")

    spec = root / ".trellis" / "spec" / "guides"
    spec.mkdir(parents=True)
    (spec / "index.md").write_text("# Guide\n\nbody", encoding="utf-8")


def test_list_skips_archive(tmp_path):
    _seed_project(tmp_path)
    tasks = list_active_tasks(tmp_path)
    names = {t.dirName for t in tasks}
    assert "01-01-demo" in names
    assert "01-02-broken" in names
    assert "archive" not in names
    assert not any(n.startswith("old") for n in names)


def test_summary_and_detail(tmp_path):
    _seed_project(tmp_path)
    tasks = {t.dirName: t for t in list_active_tasks(tmp_path)}
    demo = tasks["01-01-demo"]
    assert demo.title == "Demo Task"
    assert demo.artifacts.prd is True
    assert demo.artifacts.design is False
    assert demo.readiness.level == "ok"
    assert "no_design" in demo.readiness.flags

    detail = get_task_detail(tmp_path, "01-01-demo")
    assert detail.documents["prd"].missing is False
    assert "Hello" in (detail.documents["prd"].content or "")
    assert detail.documents["design"].missing is True


def test_broken_json(tmp_path):
    _seed_project(tmp_path)
    broken = next(t for t in list_active_tasks(tmp_path) if t.dirName == "01-02-broken")
    assert broken.error
    assert broken.readiness.level == "partial"


def test_spec_tree_and_file(tmp_path):
    _seed_project(tmp_path)
    tree = build_spec_tree(tmp_path)
    assert tree is not None
    assert tree.type == "dir"
    file_node = None

    def find_file(node):
        nonlocal file_node
        if node.type == "file" and node.name == "index.md":
            file_node = node
            return
        for c in node.children or []:
            find_file(c)

    find_file(tree)
    assert file_node is not None
    doc = read_spec_file(tmp_path, file_node.relPath)
    assert "Guide" in doc.content


def test_path_traversal_rejected(tmp_path):
    _seed_project(tmp_path)
    with pytest.raises(ReaderError):
        read_spec_file(tmp_path, "../tasks/01-01-demo/prd.md")
    with pytest.raises(ReaderError):
        read_spec_file(tmp_path, "../../etc/passwd")


def test_spec_missing_dir(tmp_path):
    (tmp_path / ".trellis" / "tasks").mkdir(parents=True)
    assert build_spec_tree(tmp_path) is None
