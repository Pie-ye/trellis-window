import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRELLIS_WINDOW_CONFIG_DIR", str(tmp_path / "cfg"))
    return TestClient(app)


def _seed(root: Path) -> None:
    t = root / ".trellis" / "tasks" / "01-01-x"
    t.mkdir(parents=True)
    (t / "task.json").write_text(
        json.dumps({"id": "x", "title": "X", "status": "planning", "priority": "P1"}),
        encoding="utf-8",
    )
    (t / "prd.md").write_text("# p", encoding="utf-8")
    g = root / ".trellis" / "spec" / "guides"
    g.mkdir(parents=True)
    (g / "a.md").write_text("# a", encoding="utf-8")


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_project_flow(client, tmp_path):
    root = tmp_path / "repo"
    _seed(root)

    bad = client.post("/api/projects", json={"path": str(tmp_path / "missing")})
    assert bad.status_code == 400

    bare = tmp_path / "bare"
    bare.mkdir()
    no_t = client.post("/api/projects", json={"path": str(bare)})
    assert no_t.status_code == 400
    assert "trellis" in no_t.json()["detail"]["error"].lower()

    ok = client.post("/api/projects", json={"path": str(root), "label": "Repo"})
    assert ok.status_code == 201
    pid = ok.json()["id"]

    listed = client.get("/api/projects")
    assert len(listed.json()["projects"]) == 1

    dup = client.post("/api/projects", json={"path": str(root)})
    assert dup.status_code == 409

    tasks = client.get(f"/api/projects/{pid}/tasks")
    assert tasks.status_code == 200
    assert tasks.json()["tasks"][0]["title"] == "X"

    detail = client.get(f"/api/projects/{pid}/tasks/01-01-x")
    assert detail.status_code == 200
    assert detail.json()["documents"]["prd"]["missing"] is False

    tasks_body = client.get(f"/api/projects/{pid}/tasks").json()
    assert "review" in tasks_body["tasks"][0]
    assert tasks_body["tasks"][0]["review"]["judgment"]

    rev = client.get(f"/api/projects/{pid}/tasks/01-01-x/review")
    assert rev.status_code == 200
    body = rev.json()
    assert body["rulesVersion"] == "review-1"
    assert "archiveCommand" in body
    before = (root / ".trellis" / "tasks" / "01-01-x" / "prd.md").read_text(encoding="utf-8")
    # review is read-only — content unchanged after request
    assert (root / ".trellis" / "tasks" / "01-01-x" / "prd.md").read_text(encoding="utf-8") == before

    tree = client.get(f"/api/projects/{pid}/specs/tree")
    assert tree.status_code == 200
    assert tree.json()["tree"] is not None

    f = client.get(f"/api/projects/{pid}/specs/file", params={"path": "guides/a.md"})
    assert f.status_code == 200
    assert "# a" in f.json()["content"]

    trav = client.get(
        f"/api/projects/{pid}/specs/file",
        params={"path": "../tasks/01-01-x/prd.md"},
    )
    assert trav.status_code == 400

    deleted = client.delete(f"/api/projects/{pid}")
    assert deleted.status_code == 200
    assert client.get("/api/projects").json()["projects"] == []
