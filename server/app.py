"""FastAPI entrypoint for Trellis Window."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server import config_store
from server.config_store import ConfigError
from server.fs_browser import BrowseError, browse_dir
from server.models import ProjectAddRequest, ScanRequest
from server.progress import summarize_progress
from server.review_engine import attach_review_summaries, review_task
from server.trellis_reader import (
    ReaderError,
    build_spec_tree,
    get_task_detail,
    list_active_tasks,
    read_spec_file,
)

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

app = FastAPI(title="Trellis Window", version="0.3.0")


def _http_from_config(exc: ConfigError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"error": exc.message})


def _http_from_reader(exc: ReaderError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"error": exc.message})


def _http_from_browse(exc: BrowseError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"error": exc.message})


@app.get("/api/health")
def health():
    return {"ok": True, "service": "trellis-window", "version": "0.3.0"}


@app.get("/api/browse")
def api_browse(path: str | None = None):
    try:
        return browse_dir(path)
    except BrowseError as e:
        raise _http_from_browse(e) from e


@app.get("/api/scan-roots")
def api_scan_roots():
    return {"scanRoots": [s.model_dump() for s in config_store.list_scan_roots()]}


@app.post("/api/scan")
def api_scan(body: ScanRequest):
    try:
        result = config_store.scan_and_register(
            body.path,
            label=body.label,
            max_depth=body.maxDepth,
            replace=body.replace,
        )
    except ConfigError as e:
        raise _http_from_config(e) from e
    return result


@app.get("/api/projects")
def api_list_projects():
    store = config_store.load_projects()
    return {
        "projects": [p.model_dump() for p in store.projects],
        "scanRoots": [s.model_dump() for s in store.scanRoots],
    }


@app.post("/api/projects", status_code=201)
def api_add_project(body: ProjectAddRequest):
    try:
        project = config_store.add_project(body.path, body.label)
    except ConfigError as e:
        raise _http_from_config(e) from e
    return project.model_dump()


@app.delete("/api/projects/{project_id}")
def api_remove_project(project_id: str):
    """Remove from UI list only — does not delete any files on disk."""
    if not config_store.remove_project(project_id):
        raise HTTPException(status_code=404, detail={"error": "Project not found"})
    return {
        "ok": True,
        "diskDeleted": False,
        "message": "已從清單移除（磁碟檔案未刪除）",
    }


@app.delete("/api/projects")
def api_clear_projects():
    """Clear entire project list from UI only."""
    n = config_store.clear_project_list()
    return {
        "ok": True,
        "removed": n,
        "diskDeleted": False,
        "message": "已清空清單（磁碟檔案未刪除）",
    }


@app.post("/api/projects/unhide")
def api_unhide_projects():
    """Allow previously UI-hidden paths to appear on the next scan."""
    n = config_store.unhide_all_paths()
    return {"ok": True, "clearedHidden": n}


def _require_project(project_id: str):
    p = config_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail={"error": "Project not found"})
    return p


@app.get("/api/projects/{project_id}/tasks")
def api_list_tasks(project_id: str):
    project = _require_project(project_id)
    try:
        tasks = list_active_tasks(project.path)
    except ReaderError as e:
        raise _http_from_reader(e) from e
    progress = summarize_progress(tasks)
    tasks_with_review = attach_review_summaries(project.path, tasks)
    return {
        "projectId": project_id,
        "project": project.model_dump(),
        "tasks": tasks_with_review,
        "progress": progress,
    }


@app.get("/api/projects/{project_id}/tasks/{dir_name}/review")
def api_task_review(project_id: str, dir_name: str):
    project = _require_project(project_id)
    try:
        review = review_task(project.path, dir_name)
    except ReaderError as e:
        raise _http_from_reader(e) from e
    return review.model_dump()


@app.get("/api/projects/{project_id}/progress")
def api_progress(project_id: str):
    project = _require_project(project_id)
    try:
        tasks = list_active_tasks(project.path)
    except ReaderError as e:
        raise _http_from_reader(e) from e
    return {
        "projectId": project_id,
        "progress": summarize_progress(tasks),
    }


@app.get("/api/projects/{project_id}/tasks/{dir_name}")
def api_task_detail(project_id: str, dir_name: str):
    project = _require_project(project_id)
    try:
        detail = get_task_detail(project.path, dir_name)
    except ReaderError as e:
        raise _http_from_reader(e) from e
    return detail.model_dump()


@app.get("/api/projects/{project_id}/specs/tree")
def api_spec_tree(project_id: str):
    project = _require_project(project_id)
    try:
        tree = build_spec_tree(project.path)
    except ReaderError as e:
        raise _http_from_reader(e) from e
    if tree is None:
        return {"projectId": project_id, "tree": None}
    return {"projectId": project_id, "tree": tree.model_dump()}


@app.get("/api/projects/{project_id}/specs/file")
def api_spec_file(project_id: str, path: str = Query(..., min_length=1)):
    project = _require_project(project_id)
    try:
        doc = read_spec_file(project.path, path)
    except ReaderError as e:
        raise _http_from_reader(e) from e
    return doc.model_dump()


@app.get("/")
def index():
    index_path = STATIC / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail={"error": "UI not found"})
    return FileResponse(index_path)


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
