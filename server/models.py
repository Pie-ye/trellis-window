"""Pydantic DTOs for Trellis Window API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectAddRequest(BaseModel):
    path: str
    label: str | None = None


class ScanRequest(BaseModel):
    path: str
    label: str | None = None
    maxDepth: int = Field(default=6, ge=0, le=12)
    replace: bool = True


class BrowseQuery(BaseModel):
    path: str | None = None


class ProjectOut(BaseModel):
    id: str
    path: str
    label: str
    addedAt: str
    scanRoot: str | None = None
    relPath: str | None = None


class ScanRootOut(BaseModel):
    id: str
    path: str
    label: str
    addedAt: str
    lastScanAt: str | None = None
    projectCount: int = 0


class ProjectsFile(BaseModel):
    version: int = 2
    scanRoots: list[ScanRootOut] = Field(default_factory=list)
    projects: list[ProjectOut] = Field(default_factory=list)
    # Paths removed from UI only (never delete on-disk files). Scan will skip these.
    hiddenPaths: list[str] = Field(default_factory=list)


class ArtifactsOut(BaseModel):
    prd: bool = False
    design: bool = False
    implement: bool = False
    implementJsonl: bool = False
    checkJsonl: bool = False


class ReadinessOut(BaseModel):
    level: Literal["ok", "partial", "missing_required"]
    flags: list[str] = Field(default_factory=list)


class ChecklistEvidenceOut(BaseModel):
    maintained: bool
    checked: int
    total: int
    ratio: float | None = None
    uncheckedSamples: list[str] = Field(default_factory=list)


class ReviewEvidenceOut(BaseModel):
    ac: ChecklistEvidenceOut
    implement: ChecklistEvidenceOut
    artifacts: ArtifactsOut
    readiness: ReadinessOut


class NextStepOut(BaseModel):
    id: str
    title: str
    detail: str
    actionType: Literal["manual", "copy_cli", "open_tab"]


JudgmentLiteral = Literal[
    "ready_to_archive",
    "needs_verification",
    "in_progress",
    "planning",
    "insufficient_evidence",
]


class ReviewSummaryOut(BaseModel):
    judgment: JudgmentLiteral
    score: float
    flags: list[str] = Field(default_factory=list)


class ReviewOut(BaseModel):
    rulesVersion: str
    dirName: str
    title: str | None = None
    status: str | None = None
    score: float
    judgment: JudgmentLiteral
    summary: str
    flags: list[str] = Field(default_factory=list)
    evidence: ReviewEvidenceOut
    nextSteps: list[NextStepOut] = Field(default_factory=list)
    archiveCommand: str


class TaskSummaryOut(BaseModel):
    dirName: str
    id: str | None = None
    name: str | None = None
    title: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee: str | None = None
    package: str | None = None
    scope: str | None = None
    parent: str | None = None
    children: list[Any] = Field(default_factory=list)
    description: str | None = None
    notes: str | None = None
    artifacts: ArtifactsOut
    readiness: ReadinessOut
    error: str | None = None
    review: ReviewSummaryOut | None = None


class MdDocOut(BaseModel):
    name: str
    missing: bool
    content: str | None = None
    truncated: bool = False


class TaskDetailOut(TaskSummaryOut):
    documents: dict[str, MdDocOut] = Field(default_factory=dict)
    rawTaskJson: dict[str, Any] | None = None


class SpecNodeOut(BaseModel):
    name: str
    type: Literal["dir", "file"]
    relPath: str
    children: list[SpecNodeOut] | None = None


class SpecFileOut(BaseModel):
    relPath: str
    content: str
    truncated: bool = False


class ErrorOut(BaseModel):
    error: str
