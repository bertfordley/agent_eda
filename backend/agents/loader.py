"""
agents/loader.py
──────────────────────────────────────────────────────────────────────────────
Load agent/subagent definitions from agents/definitions/*.md.

Each definition is a frontmatter Markdown file:
    ---
    name: bq_explorer
    description: ...
    tools: [bq_run_query, df_check_key, ...]   # omitted for main_agent
    ---
    <system prompt body...>

The pure parsing function `parse_agent_markdown(text, registry)` takes an
explicit tool registry so it is testable without importing the heavy tool stack.
Runtime callers use the default registry built lazily from tools.ALL_TOOLS.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from frontmatter import split_frontmatter

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"
MAIN_AGENT_STEM = "main_agent"


def build_tool_registry() -> dict[str, Callable]:
    """Map tool __name__ → callable. Lazy import keeps this module light."""
    from tools import ALL_TOOLS

    return {fn.__name__: fn for fn in ALL_TOOLS}


def parse_agent_markdown(text: str, registry: dict[str, Callable]) -> dict:
    """Parse one agent definition into a Deep Agents subagent dict. Pure.

    Shape matches the hand-written subagent dicts in orchestrator.py:
        {name, description, system_prompt, tools}
    Raises ValueError on a missing name or an unknown tool reference (fail-fast).
    """
    meta, body = split_frontmatter(text)

    name = str(meta.get("name") or "").strip()
    if not name:
        raise ValueError("Agent definition is missing required 'name'.")

    raw_tools = meta.get("tools") or []
    if not isinstance(raw_tools, list):
        raise ValueError(f"Agent '{name}': 'tools' must be a list.")

    tools: list[Callable] = []
    for tn in raw_tools:
        if tn not in registry:
            raise ValueError(
                f"Agent '{name}': unknown tool '{tn}'. "
                f"Known tools: {', '.join(sorted(registry))}."
            )
        tools.append(registry[tn])

    return {
        "name": name,
        "description": str(meta.get("description", "")).strip(),
        "system_prompt": body,
        "tools": tools,
    }


def load_agent_definition(
    path: str | Path, registry: dict[str, Callable] | None = None
) -> dict:
    registry = registry if registry is not None else build_tool_registry()
    return parse_agent_markdown(Path(path).read_text(), registry)


def definitions_available() -> bool:
    """True when a definitions dir with a main_agent.md is present."""
    return (DEFINITIONS_DIR / f"{MAIN_AGENT_STEM}.md").is_file()


def main_prompt_base() -> str:
    """The main agent's system-prompt body (catalog + skills are appended by
    the orchestrator, not here)."""
    _, body = split_frontmatter((DEFINITIONS_DIR / f"{MAIN_AGENT_STEM}.md").read_text())
    return body


def load_subagents(registry: dict[str, Callable] | None = None) -> list[dict]:
    """Every definitions/*.md except main_agent.md, as subagent dicts."""
    registry = registry if registry is not None else build_tool_registry()
    subs: list[dict] = []
    for p in sorted(DEFINITIONS_DIR.glob("*.md")):
        if p.stem == MAIN_AGENT_STEM:
            continue
        subs.append(load_agent_definition(p, registry))
    return subs
