"""Parse Markdown checkbox lists for Review scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass

_UNCHECKED = re.compile(r"^(\s*)- \[ \] (.+)$")
_CHECKED = re.compile(r"^(\s*)- \[[xX]\] (.+)$")
_FENCE = re.compile(r"^(\s*)```")


@dataclass
class ChecklistResult:
    checked: int
    total: int
    maintained: bool
    ratio: float | None
    unchecked_samples: list[str]
    items: list[tuple[bool, str]]  # (checked, text)


def parse_checklist(md: str | None, *, sample_limit: int = 3) -> ChecklistResult:
    """Parse full-document markdown checkboxes; ignore fenced code blocks."""
    if not md:
        return ChecklistResult(
            checked=0,
            total=0,
            maintained=False,
            ratio=None,
            unchecked_samples=[],
            items=[],
        )

    in_fence = False
    items: list[tuple[bool, str]] = []

    for line in md.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m_c = _CHECKED.match(line)
        if m_c:
            items.append((True, m_c.group(2).strip()))
            continue
        m_u = _UNCHECKED.match(line)
        if m_u:
            items.append((False, m_u.group(2).strip()))

    total = len(items)
    checked = sum(1 for c, _ in items if c)
    maintained = total > 0
    ratio = (checked / total) if maintained else None
    unchecked_samples = [t for c, t in items if not c][:sample_limit]

    return ChecklistResult(
        checked=checked,
        total=total,
        maintained=maintained,
        ratio=ratio,
        unchecked_samples=unchecked_samples,
        items=items,
    )
