"""Project-level progress aggregation from task summaries."""

from __future__ import annotations

from collections import Counter

from server.models import TaskSummaryOut


def summarize_progress(tasks: list[TaskSummaryOut]) -> dict:
    by_status: Counter[str] = Counter()
    by_readiness: Counter[str] = Counter()
    by_priority: Counter[str] = Counter()
    with_prd = 0
    with_design = 0
    with_implement = 0

    for t in tasks:
        by_status[t.status or "unknown"] += 1
        by_readiness[(t.readiness.level if t.readiness else "unknown")] += 1
        by_priority[t.priority or "unset"] += 1
        if t.artifacts:
            if t.artifacts.prd:
                with_prd += 1
            if t.artifacts.design:
                with_design += 1
            if t.artifacts.implement:
                with_implement += 1

    total = len(tasks)
    in_progress = by_status.get("in_progress", 0)
    planning = by_status.get("planning", 0)
    completed = by_status.get("completed", 0)

    return {
        "total": total,
        "byStatus": dict(by_status),
        "byReadiness": dict(by_readiness),
        "byPriority": dict(by_priority),
        "artifacts": {
            "prd": with_prd,
            "design": with_design,
            "implement": with_implement,
        },
        "percentInProgress": round(100 * in_progress / total, 1) if total else 0,
        "percentPlanning": round(100 * planning / total, 1) if total else 0,
        "percentCompleted": round(100 * completed / total, 1) if total else 0,
    }
