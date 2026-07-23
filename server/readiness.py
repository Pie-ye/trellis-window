"""Conservative artifact-presence readiness (no semantic analysis)."""

from __future__ import annotations

from server.models import ArtifactsOut, ReadinessOut


def compute_readiness(
    *,
    has_task_json: bool,
    artifacts: ArtifactsOut,
    parse_error: str | None = None,
) -> ReadinessOut:
    flags: list[str] = []

    if parse_error:
        flags.append("task_json_error")
    if not has_task_json:
        flags.append("missing_task_json")
        return ReadinessOut(level="missing_required", flags=flags)

    if not artifacts.prd:
        flags.append("missing_prd")

    if not artifacts.design:
        flags.append("no_design")
    if not artifacts.implement:
        flags.append("no_implement")

    if "missing_prd" in flags or parse_error:
        return ReadinessOut(level="partial", flags=flags)

    # design/implement absence is informational only (lightweight PRD-only is valid)
    if flags:
        return ReadinessOut(level="ok", flags=flags)
    return ReadinessOut(level="ok", flags=[])
