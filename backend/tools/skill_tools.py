"""
tools/skill_tools.py
──────────────────────────────────────────────────────────────────────────────
The load_skill tool — progressive disclosure for analysis playbooks.

Only a compact skill INDEX lives in the system prompt (see skills/loader.py).
When the agent decides a skill applies, it calls load_skill(name) to pull that
skill's full step-by-step instructions into context on demand.
"""

from __future__ import annotations

from skills.loader import get_skill_body, list_skill_names

SKILL_NOT_FOUND = "SKILL_NOT_FOUND"


def load_skill(name: str) -> str:
    """
    Load the full step-by-step instructions for a named analysis skill.

    Args:
        name: Skill name from the skills index (e.g. 'key-comparison').
    """
    body = get_skill_body(name)
    if body is None:
        available = ", ".join(list_skill_names()) or "(none configured)"
        return f"[{SKILL_NOT_FOUND} name='{name}'] Available skills: {available}."
    return body
