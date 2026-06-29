"""
skills/loader.py
──────────────────────────────────────────────────────────────────────────────
Discover and load SKILL.md playbooks.

Dependency-light (stdlib + frontmatter, which is stdlib + pyyaml) so it imports
in isolation for tests. A skill lives at  skills/<name>/SKILL.md  with frontmatter:

    ---
    name: key-comparison
    description: Safely compare two datasets on a join key.
    when_to_use: User asks to compare / diff / reconcile two tables.
    ---
    <step-by-step instructions...>
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from frontmatter import split_frontmatter

SKILLS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _skill_files() -> tuple[Path, ...]:
    return tuple(sorted(SKILLS_DIR.glob("*/SKILL.md")))


@lru_cache(maxsize=None)
def _parse_skill(path: Path) -> tuple[dict, str]:
    """Parse and cache a single SKILL.md file. One file read per process lifetime."""
    return split_frontmatter(path.read_text())


def _name_of(path: Path, meta: dict) -> str:
    return str(meta.get("name") or path.parent.name)


def list_skill_names() -> list[str]:
    names = []
    for p in _skill_files():
        meta, _ = _parse_skill(p)
        names.append(_name_of(p, meta))
    return names


def load_skill_index() -> str:
    """Compact index injected into the system prompt. Empty string if none."""
    entries: list[str] = []
    for p in _skill_files():
        meta, _ = _parse_skill(p)
        name = _name_of(p, meta)
        desc = str(meta.get("description", "")).strip()
        when = str(meta.get("when_to_use", "")).strip()
        line = f"  • {name}: {desc}"
        if when:
            line += f"  [use when: {when}]"
        entries.append(line)

    if not entries:
        return ""

    return (
        "━━ SKILLS ━━\n"
        "Reusable analysis playbooks. When a request matches one, call "
        "load_skill(<name>) to get its full step-by-step instructions, then "
        "follow them.\n" + "\n".join(entries)
    )


def get_skill_body(name: str) -> str | None:
    """Return the instruction body for a named skill, or None if not found."""
    for p in _skill_files():
        meta, body = _parse_skill(p)
        if _name_of(p, meta) == name:
            return body
    return None
