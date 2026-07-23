"""Rule-based completion review (rulesVersion review-1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from server.checklist_parse import parse_checklist
from server.models import (
    ArtifactsOut,
    ChecklistEvidenceOut,
    NextStepOut,
    ReadinessOut,
    ReviewEvidenceOut,
    ReviewOut,
    ReviewSummaryOut,
    TaskSummaryOut,
)
from server.trellis_reader import MAX_FILE_BYTES, ReaderError, summarize_task

RULES_VERSION = "review-1"


def _read_md(task_dir: Path, name: str) -> str | None:
    path = task_dir / name
    if not path.is_file():
        return None
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        data = data[:MAX_FILE_BYTES]
    return data.decode("utf-8", errors="replace")


def _checklist_out(result) -> ChecklistEvidenceOut:
    return ChecklistEvidenceOut(
        maintained=result.maintained,
        checked=result.checked,
        total=result.total,
        ratio=result.ratio,
        uncheckedSamples=result.unchecked_samples,
    )


def _status_prior(status: str | None) -> float:
    s = (status or "").lower()
    if s == "planning":
        return 0.2
    if s == "in_progress":
        return 0.6
    if s == "completed":
        return 1.0
    return 0.5


def _artifact_score(artifacts: ArtifactsOut) -> float:
    # prd=0.5, design=0.25, implement=0.25
    score = 0.0
    if artifacts.prd:
        score += 0.5
    if artifacts.design:
        score += 0.25
    if artifacts.implement:
        score += 0.25
    return score


def _compute_score(
    *,
    ac_ratio: float | None,
    ac_maintained: bool,
    impl_ratio: float | None,
    impl_maintained: bool,
    has_implement_file: bool,
    artifacts: ArtifactsOut,
    status: str | None,
) -> float:
    parts: list[tuple[float, float]] = []  # (weight, value)

    if ac_maintained and ac_ratio is not None:
        parts.append((0.40, ac_ratio))
    if has_implement_file and impl_maintained and impl_ratio is not None:
        parts.append((0.30, impl_ratio))
    elif has_implement_file and not impl_maintained:
        # file exists but no checkboxes — neutral 0.5 on implement weight
        parts.append((0.30, 0.5))

    parts.append((0.20, _artifact_score(artifacts)))
    parts.append((0.10, _status_prior(status)))

    total_w = sum(w for w, _ in parts)
    if total_w <= 0:
        return 0.0
    return sum(w * v for w, v in parts) / total_w


def _build_flags(
    *,
    artifacts: ArtifactsOut,
    ac,
    impl,
    has_implement_file: bool,
    status: str | None,
    score: float,
) -> list[str]:
    flags: list[str] = []
    if not artifacts.prd:
        flags.append("missing_prd")
    if not artifacts.design:
        flags.append("missing_design")
    if not ac.maintained:
        flags.append("ac_unmaintained")
    elif ac.ratio is not None and ac.ratio < 1.0:
        flags.append("ac_incomplete")
    if not has_implement_file:
        flags.append("implement_missing_file")
    elif impl.maintained and impl.ratio is not None:
        if impl.ratio >= 1.0 and impl.total > 0:
            flags.append("implement_done")
        elif impl.ratio < 1.0:
            flags.append("implement_incomplete")
    st = (status or "").lower()
    if st == "planning":
        flags.append("status_planning")
    if st == "in_progress":
        flags.append("status_in_progress")
    if score >= 0.75:
        flags.append("high_score")
    if score < 0.4:
        flags.append("low_score")
    return flags


def _judgment(
    *,
    flags: list[str],
    artifacts: ArtifactsOut,
    ac,
    impl,
    has_implement_file: bool,
    status: str | None,
    score: float,
    has_task_json: bool,
) -> str:
    if not has_task_json or "missing_prd" in flags:
        return "insufficient_evidence"
    st = (status or "").lower()
    if st == "planning" and not has_implement_file:
        return "planning"
    implement_done = "implement_done" in flags
    ac_ok = (ac.maintained and ac.ratio is not None and ac.ratio >= 0.8) or (
        not ac.maintained
    )
    if implement_done and ac_ok and artifacts.prd:
        return "ready_to_archive"
    if implement_done and ac.maintained and ac.ratio is not None and ac.ratio < 0.8:
        return "needs_verification"
    if score >= 0.75 and st == "in_progress":
        return "needs_verification"
    if st == "planning":
        return "planning"
    return "in_progress"


def _summary(judgment: str, flags: list[str], score: float) -> str:
    pct = round(score * 100)
    if judgment == "insufficient_evidence":
        return f"證據不足（分數約 {pct}%）：缺少 prd 或 task.json，無法可靠判斷是否可結案。"
    if judgment == "ready_to_archive":
        return (
            f"文件證據傾向可結案（分數約 {pct}%）。"
            "建議快速手測 Goal 後執行 archive；本工具不會自動改狀態。"
        )
    if judgment == "needs_verification":
        extra = "AC 未全部勾選，" if "ac_incomplete" in flags else ""
        if "ac_unmaintained" in flags:
            extra = "PRD 未維護 checkbox，"
        return (
            f"像是做完了但仍建議手測（分數約 {pct}%）。{extra}"
            "通過後再 archive。"
        )
    if judgment == "planning":
        return f"仍在規劃階段（分數約 {pct}%）。應補齊規劃產物，或確認取消後再 archive。"
    return f"仍有進行中證據（分數約 {pct}%）。可依 implement 未完成項繼續，或縮 scope 後重評。"


def _next_steps(
    judgment: str,
    dir_name: str,
    ac_samples: list[str],
    impl_samples: list[str],
) -> list[NextStepOut]:
    archive_cmd = f"python3 ./.trellis/scripts/task.py archive {dir_name}"
    steps: list[NextStepOut] = []

    if judgment == "ready_to_archive":
        steps = [
            NextStepOut(
                id="verify-goal",
                title="快速手測 Goal",
                detail="用 prd 的 Goal 做 1～3 分鐘驗證，確認主路徑可用。",
                actionType="manual",
            ),
            NextStepOut(
                id="archive-cli",
                title="複製 archive 指令",
                detail=archive_cmd,
                actionType="copy_cli",
            ),
            NextStepOut(
                id="note-limits",
                title="可選：記錄已知限制",
                detail="若有小尾巴，在 notes 或 follow-up task 註明後再結案。",
                actionType="manual",
            ),
        ]
    elif judgment == "needs_verification":
        sample = ac_samples or impl_samples
        detail = (
            "建議手測：\n- " + "\n- ".join(sample)
            if sample
            else "對照 prd Goal 做手測；AC checkbox 可能未維護。"
        )
        steps = [
            NextStepOut(
                id="hand-test",
                title="手測關鍵項目",
                detail=detail,
                actionType="manual",
            ),
            NextStepOut(
                id="archive-if-ok",
                title="通過後 archive",
                detail=archive_cmd,
                actionType="copy_cli",
            ),
            NextStepOut(
                id="write-gap",
                title="不通過則寫下缺口",
                detail="把失敗點寫回 prd notes 或開 follow-up，避免永遠卡在 in_progress。",
                actionType="manual",
            ),
        ]
    elif judgment == "planning":
        steps = [
            NextStepOut(
                id="finish-prd",
                title="補齊 prd 驗收條件",
                detail="寫清楚 Goal 與 Acceptance，或確認此 task 要取消。",
                actionType="open_tab",
            ),
            NextStepOut(
                id="freeze-archive",
                title="若已放棄：archive 凍結",
                detail=archive_cmd + "\n（可在 notes 註明取消／凍結原因）",
                actionType="copy_cli",
            ),
            NextStepOut(
                id="dont-fake-progress",
                title="不要長期假 in_progress",
                detail="planning 很久應重開更小 task 或結案，避免污染清單。",
                actionType="manual",
            ),
        ]
    elif judgment == "insufficient_evidence":
        steps = [
            NextStepOut(
                id="add-prd",
                title="補 prd.md",
                detail="至少寫 Goal 與可測的 Acceptance。",
                actionType="open_tab",
            ),
            NextStepOut(
                id="check-dir",
                title="確認 task 目錄完整",
                detail="檢查 task.json 是否可讀、路徑是否正確。",
                actionType="manual",
            ),
        ]
    else:  # in_progress
        detail = (
            "未完成 implement 項：\n- " + "\n- ".join(impl_samples)
            if impl_samples
            else "查看 implement.md 或 prd 未勾項目，收斂剩餘工作。"
        )
        steps = [
            NextStepOut(
                id="continue-impl",
                title="繼續未完成項",
                detail=detail,
                actionType="open_tab",
            ),
            NextStepOut(
                id="shrink-scope",
                title="考慮縮 scope",
                detail="若主功能已好，把剩餘拆 follow-up 後走手測與 archive。",
                actionType="manual",
            ),
            NextStepOut(
                id="archive-when-ready",
                title="就緒時的 archive 指令",
                detail=archive_cmd,
                actionType="copy_cli",
            ),
        ]
    return steps[:3]


def build_review_from_summary(
    summary: TaskSummaryOut,
    *,
    task_dir: Path,
    has_task_json: bool = True,
) -> ReviewOut:
    prd_text = _read_md(task_dir, "prd.md") if summary.artifacts.prd else None
    impl_text = (
        _read_md(task_dir, "implement.md") if summary.artifacts.implement else None
    )
    ac = parse_checklist(prd_text)
    impl = parse_checklist(impl_text)
    has_implement_file = summary.artifacts.implement

    score = _compute_score(
        ac_ratio=ac.ratio,
        ac_maintained=ac.maintained,
        impl_ratio=impl.ratio,
        impl_maintained=impl.maintained,
        has_implement_file=has_implement_file,
        artifacts=summary.artifacts,
        status=summary.status,
    )
    flags = _build_flags(
        artifacts=summary.artifacts,
        ac=ac,
        impl=impl,
        has_implement_file=has_implement_file,
        status=summary.status,
        score=score,
    )
    judgment = _judgment(
        flags=flags,
        artifacts=summary.artifacts,
        ac=ac,
        impl=impl,
        has_implement_file=has_implement_file,
        status=summary.status,
        score=score,
        has_task_json=has_task_json,
    )
    archive_cmd = f"python3 ./.trellis/scripts/task.py archive {summary.dirName}"
    next_steps = _next_steps(
        judgment,
        summary.dirName,
        ac.unchecked_samples,
        impl.unchecked_samples,
    )

    return ReviewOut(
        rulesVersion=RULES_VERSION,
        dirName=summary.dirName,
        title=summary.title,
        status=summary.status,
        score=round(score, 4),
        judgment=judgment,  # type: ignore[arg-type]
        summary=_summary(judgment, flags, score),
        flags=flags,
        evidence=ReviewEvidenceOut(
            ac=_checklist_out(ac),
            implement=_checklist_out(impl),
            artifacts=summary.artifacts,
            readiness=summary.readiness,
        ),
        nextSteps=next_steps,
        archiveCommand=archive_cmd,
    )


def review_summary_only(review: ReviewOut) -> ReviewSummaryOut:
    return ReviewSummaryOut(
        judgment=review.judgment,
        score=review.score,
        flags=list(review.flags),
    )


def review_task(project_root: str | Path, dir_name: str) -> ReviewOut:
    root = Path(project_root).resolve()
    summary = summarize_task(root, dir_name)
    task_dir = root / ".trellis" / "tasks" / dir_name
    if not task_dir.is_dir():
        raise ReaderError(f"Task not found: {dir_name}", status_code=404)
    has_json = (task_dir / "task.json").is_file()
    return build_review_from_summary(summary, task_dir=task_dir, has_task_json=has_json)


def attach_review_summaries(
    project_root: str | Path, tasks: list[TaskSummaryOut]
) -> list[dict[str, Any]]:
    """Return task dicts with embedded review summary."""
    root = Path(project_root).resolve()
    out: list[dict[str, Any]] = []
    for t in tasks:
        data = t.model_dump()
        try:
            task_dir = root / ".trellis" / "tasks" / t.dirName
            rev = build_review_from_summary(
                t,
                task_dir=task_dir,
                has_task_json=(task_dir / "task.json").is_file(),
            )
            data["review"] = review_summary_only(rev).model_dump()
        except Exception:
            data["review"] = None
        out.append(data)
    return out
