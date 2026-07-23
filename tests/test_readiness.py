from server.models import ArtifactsOut
from server.readiness import compute_readiness


def test_missing_task_json():
    r = compute_readiness(
        has_task_json=False,
        artifacts=ArtifactsOut(),
    )
    assert r.level == "missing_required"
    assert "missing_task_json" in r.flags


def test_missing_prd_partial():
    r = compute_readiness(
        has_task_json=True,
        artifacts=ArtifactsOut(prd=False, design=True, implement=True),
    )
    assert r.level == "partial"
    assert "missing_prd" in r.flags


def test_prd_only_ok_with_info_flags():
    r = compute_readiness(
        has_task_json=True,
        artifacts=ArtifactsOut(prd=True, design=False, implement=False),
    )
    assert r.level == "ok"
    assert "no_design" in r.flags
    assert "no_implement" in r.flags


def test_full_ok():
    r = compute_readiness(
        has_task_json=True,
        artifacts=ArtifactsOut(prd=True, design=True, implement=True),
    )
    assert r.level == "ok"
    assert r.flags == []
