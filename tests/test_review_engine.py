import json
from pathlib import Path

from server.models import ArtifactsOut, ReadinessOut, TaskSummaryOut
from server.review_engine import build_review_from_summary, review_task


def _summary(dir_name, status, artifacts, **kwargs):
    return TaskSummaryOut(
        dirName=dir_name,
        title=dir_name,
        status=status,
        artifacts=artifacts,
        readiness=ReadinessOut(level="ok", flags=[]),
        **kwargs,
    )


def test_ready_to_archive(tmp_path):
    d = tmp_path / "t1"
    d.mkdir()
    (d / "task.json").write_text(json.dumps({"title": "T", "status": "in_progress"}))
    (d / "prd.md").write_text("# G\n\n- [x] a\n- [x] b\n")
    (d / "design.md").write_text("# d")
    (d / "implement.md").write_text("- [x] one\n- [x] two\n")
    s = _summary(
        "t1",
        "in_progress",
        ArtifactsOut(prd=True, design=True, implement=True),
    )
    r = build_review_from_summary(s, task_dir=d, has_task_json=True)
    assert r.judgment == "ready_to_archive"
    assert r.score >= 0.75
    assert "archive" in r.archiveCommand


def test_ac_unmaintained_still_ready_when_impl_done(tmp_path):
    d = tmp_path / "t2"
    d.mkdir()
    (d / "prd.md").write_text("# Goal only\nno checkboxes")
    (d / "implement.md").write_text("- [x] a\n- [x] b\n")
    s = _summary(
        "t2",
        "in_progress",
        ArtifactsOut(prd=True, design=False, implement=True),
    )
    r = build_review_from_summary(s, task_dir=d, has_task_json=True)
    assert "ac_unmaintained" in r.flags
    assert r.judgment == "ready_to_archive"


def test_needs_verification_when_ac_incomplete(tmp_path):
    d = tmp_path / "t3"
    d.mkdir()
    (d / "prd.md").write_text("- [x] a\n- [ ] b\n- [ ] c\n")
    (d / "implement.md").write_text("- [x] done\n")
    s = _summary(
        "t3",
        "in_progress",
        ArtifactsOut(prd=True, design=True, implement=True),
    )
    r = build_review_from_summary(s, task_dir=d, has_task_json=True)
    assert r.judgment == "needs_verification"


def test_planning(tmp_path):
    d = tmp_path / "t4"
    d.mkdir()
    (d / "prd.md").write_text("- [ ] plan\n")
    s = _summary("t4", "planning", ArtifactsOut(prd=True, design=False, implement=False))
    r = build_review_from_summary(s, task_dir=d, has_task_json=True)
    assert r.judgment == "planning"


def test_insufficient_without_prd(tmp_path):
    d = tmp_path / "t5"
    d.mkdir()
    s = _summary("t5", "in_progress", ArtifactsOut(prd=False, design=False, implement=False))
    r = build_review_from_summary(s, task_dir=d, has_task_json=True)
    assert r.judgment == "insufficient_evidence"


def test_review_task_api_path(tmp_path):
    root = tmp_path / "repo"
    t = root / ".trellis" / "tasks" / "01-01-x"
    t.mkdir(parents=True)
    (t / "task.json").write_text(
        json.dumps({"id": "x", "title": "X", "status": "in_progress"}),
        encoding="utf-8",
    )
    (t / "prd.md").write_text("- [x] ok\n")
    (t / "implement.md").write_text("- [x] ok\n")
    r = review_task(root, "01-01-x")
    assert r.dirName == "01-01-x"
    assert r.rulesVersion == "review-1"
