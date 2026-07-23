from pathlib import Path

from fastapi.testclient import TestClient

from server.app import app


def test_browse_and_scan(tmp_path, monkeypatch):
    monkeypatch.setenv("TRELLIS_WINDOW_CONFIG_DIR", str(tmp_path / "cfg"))
    client = TestClient(app)

    ws = tmp_path / "workspace"
    a = ws / "alpha"
    b = ws / "beta" / "inner"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / ".trellis" / "tasks").mkdir(parents=True)
    (a / ".trellis" / "tasks" / "01-01-t").mkdir()
    (a / ".trellis" / "tasks" / "01-01-t" / "task.json").write_text(
        '{"id":"t","title":"T","status":"planning","priority":"P1"}',
        encoding="utf-8",
    )
    (a / ".trellis" / "tasks" / "01-01-t" / "prd.md").write_text("# p", encoding="utf-8")
    (b / ".trellis").mkdir(parents=True)

    br = client.get("/api/browse", params={"path": str(ws)})
    assert br.status_code == 200
    names = {e["name"] for e in br.json()["entries"]}
    assert "alpha" in names
    assert "beta" in names

    scanned = client.post("/api/scan", json={"path": str(ws), "replace": True})
    assert scanned.status_code == 200
    body = scanned.json()
    assert body["count"] == 2
    assert len(body["projects"]) == 2

    projects = client.get("/api/projects").json()
    assert len(projects["projects"]) == 2
    assert len(projects["scanRoots"]) == 1

    pid = next(p["id"] for p in projects["projects"] if p["label"] == "alpha" or "alpha" in (p.get("relPath") or ""))
    # fallback: path ends with alpha
    if not pid:
        pid = next(p["id"] for p in projects["projects"] if p["path"].endswith("alpha"))
    tasks = client.get(f"/api/projects/{pid}/tasks")
    assert tasks.status_code == 200
    data = tasks.json()
    assert "progress" in data
    assert data["progress"]["total"] == 1
    assert data["tasks"][0]["title"] == "T"
