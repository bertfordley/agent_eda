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


def _kind_of(meta: dict) -> str:
    """'playbook' (default) or 'script'. Unrecognized values fall back to
    'playbook' — this is advisory routing metadata, not a correctness contract,
    so it fails soft rather than raising (unlike agents/loader.py's tools:
    validation)."""
    kind = str(meta.get("kind") or "playbook").strip().lower()
    return kind if kind in ("playbook", "script") else "playbook"


def list_skill_names() -> list[str]:
    names = []
    for p in _skill_files():
        meta, _ = _parse_skill(p)
        names.append(_name_of(p, meta))
    return names


# NOTE: "[playbook]"/"[script]" literal tags below are referenced by name in
# agents/definitions/main_agent.md's ROUTING section — keep in sync.
def load_skill_index() -> str:
    """Compact index injected into the system prompt. Empty string if none."""
    playbook_entries: list[str] = []
    script_entries: list[str] = []
    for p in _skill_files():
        meta, _ = _parse_skill(p)
        name = _name_of(p, meta)
        desc = str(meta.get("description", "")).strip()
        when = str(meta.get("when_to_use", "")).strip()
        line = f"  • {name}: {desc}"
        if when:
            line += f"  [use when: {when}]"
        if _kind_of(meta) == "script":
            script_entries.append(line)
        else:
            playbook_entries.append(line)

    if not playbook_entries and not script_entries:
        return ""

    sections = [
        "━━ SKILLS ━━\n"
        "Reusable analysis playbooks. When a request matches one, call "
        "load_skill(<name>) to get its full step-by-step instructions, then "
        "follow them."
    ]
    if playbook_entries:
        sections.append(
            "[playbook] — needs BigQuery/Sheets/Drive data first, then "
            "follow the BIGQUERY ANALYSIS FLOW:\n" + "\n".join(playbook_entries)
        )
    if script_entries:
        sections.append(
            "[script] — self-contained; do NOT load data first, call "
            "run_skill_script as the skill instructs:\n" + "\n".join(script_entries)
        )
    return "\n\n".join(sections)


def get_skill_body(name: str) -> str | None:
    """Return the instruction body for a named skill, or None if not found."""
    for p in _skill_files():
        meta, body = _parse_skill(p)
        if _name_of(p, meta) == name:
            return body
    return None


def get_skill_dir(name: str) -> Path | None:
    """Return the directory for a named skill, or None if not found.

    A skill's directory holds its SKILL.md plus any scripts/ and assets/ folders.
    Used by the run_skill_script tool to locate and bound skill-owned scripts.
    """
    for p in _skill_files():
        meta, _ = _parse_skill(p)
        if _name_of(p, meta) == name:
            return p.parent
    return None
