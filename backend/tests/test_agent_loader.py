"""
tests/test_agent_loader.py
──────────────────────────────────────────────────────────────────────────────
Unit tests for the frontmatter parser, agent loader, and skills loader.

All exercise pure logic with an injected fake tool registry, so no heavy tool
stack is imported — same isolation contract as test_catalog.py.
"""

from pathlib import Path

import pytest

import skills.loader as skills_loader
from agents.loader import load_subagents, main_prompt_base, parse_agent_markdown
from frontmatter import split_frontmatter
from skills.loader import (
    _kind_of,
    get_skill_body,
    list_skill_names,
    load_skill_index,
)

# ── frontmatter parser ────────────────────────────────────────────────────────


def test_split_frontmatter_extracts_meta_and_body():
    text = "---\nname: x\ndescription: hi\n---\nBody line one.\nBody line two."
    meta, body = split_frontmatter(text)
    assert meta == {"name": "x", "description": "hi"}
    assert body == "Body line one.\nBody line two."


def test_split_frontmatter_no_frontmatter_returns_empty_meta():
    meta, body = split_frontmatter("Just a body, no frontmatter.")
    assert meta == {}
    assert body == "Just a body, no frontmatter."


def test_split_frontmatter_unclosed_raises():
    with pytest.raises(ValueError):
        split_frontmatter("---\nname: x\nbody with no close")


# ── agent loader (with injected registry) ─────────────────────────────────────


def _fake_registry():
    def bq_run_query():  # names are what the loader maps on
        pass

    def df_check_key():
        pass

    return {fn.__name__: fn for fn in (bq_run_query, df_check_key)}


def test_parse_agent_maps_tool_names_to_callables():
    reg = _fake_registry()
    text = (
        "---\nname: bq_explorer\ndescription: d\n"
        "tools:\n  - bq_run_query\n  - df_check_key\n---\nPrompt body."
    )
    spec = parse_agent_markdown(text, reg)
    assert spec["name"] == "bq_explorer"
    assert spec["description"] == "d"
    assert spec["system_prompt"] == "Prompt body."
    assert spec["tools"] == [reg["bq_run_query"], reg["df_check_key"]]


def test_parse_agent_unknown_tool_raises():
    text = "---\nname: x\ntools:\n  - no_such_tool\n---\nbody"
    with pytest.raises(ValueError):
        parse_agent_markdown(text, _fake_registry())


def test_parse_agent_missing_name_raises():
    text = "---\ndescription: no name\n---\nbody"
    with pytest.raises(ValueError):
        parse_agent_markdown(text, _fake_registry())


def test_parse_agent_no_tools_defaults_empty():
    text = "---\nname: main_agent\ndescription: d\n---\nThe prompt."
    spec = parse_agent_markdown(text, _fake_registry())
    assert spec["tools"] == []
    assert spec["system_prompt"] == "The prompt."


def test_parse_agent_tools_not_a_list_raises():
    text = "---\nname: x\ntools: bq_run_query\n---\nbody"
    with pytest.raises(ValueError):
        parse_agent_markdown(text, _fake_registry())


# ── skills loader (reads the real seeded skills/) ─────────────────────────────


def test_seeded_skills_are_discovered():
    names = list_skill_names()
    assert "key-comparison" in names
    assert "explore-data" in names


def test_skill_index_mentions_seeded_skills():
    index = load_skill_index()
    assert "key-comparison" in index
    assert "load_skill" in index


def test_get_skill_body_returns_instructions():
    body = get_skill_body("key-comparison")
    assert body is not None
    assert "df_check_key" in body


def test_get_skill_body_unknown_returns_none():
    assert get_skill_body("no-such-skill") is None


def test_kind_of_normalizes_unknown_value_to_playbook():
    assert _kind_of({}) == "playbook"
    assert _kind_of({"kind": "bogus"}) == "playbook"
    assert _kind_of({"kind": "PLAYBOOK"}) == "playbook"
    assert _kind_of({"kind": "script"}) == "script"
    assert _kind_of({"kind": "  script  "}) == "script"


def test_kind_defaults_to_playbook_for_seeded_skills():
    # None of the 5 seeded skills declare kind, so all fall into [playbook]
    # and no [script] group should render.
    index = load_skill_index()
    assert "[playbook]" in index
    assert "[script]" not in index


def test_skill_index_groups_by_kind(monkeypatch):
    # Inject one fake kind: script skill alongside the real seeded ones to
    # prove load_skill_index() actually groups by kind (none of the real
    # skills qualify for the [script] branch).
    real_skill_files = skills_loader._skill_files()
    real_parse_skill = skills_loader._parse_skill
    fake_path = Path("/fake/fake-script-skill/SKILL.md")

    def fake_parse_skill(path):
        if path == fake_path:
            return ({"name": "fake-script-skill", "description": "d", "kind": "script"}, "body")
        return real_parse_skill(path)

    monkeypatch.setattr(skills_loader, "_skill_files", lambda: (*real_skill_files, fake_path))
    monkeypatch.setattr(skills_loader, "_parse_skill", fake_parse_skill)

    index = skills_loader.load_skill_index()

    assert "[playbook]" in index
    assert "[script]" in index
    assert index.index("fake-script-skill") > index.index("[script]")


# ── main_prompt_base and load_subagents (definitions dir) ─────────────────────


def test_main_prompt_base_reads_definitions_file():
    prompt = main_prompt_base()
    assert isinstance(prompt, str)
    assert len(prompt) > 50
    assert "BigQuery" in prompt


def test_load_subagents_returns_bq_explorer_and_viz_analyst():
    subs = load_subagents(_full_registry())
    names = {s["name"] for s in subs}
    assert names == {"bq_explorer", "viz_analyst"}
    assert len(subs) == 2


def _full_registry() -> dict:
    """Registry covering every tool referenced in any definitions/*.md file."""
    tool_names = [
        "bq_list_datasets", "bq_list_tables", "bq_describe_table",
        "bq_run_query", "bq_profile_dataset", "df_check_key",
        "df_describe", "chart_bar", "chart_line", "chart_scatter",
        "chart_histogram", "chart_heatmap", "chart_interactive",
        "report_start", "report_add_section", "report_add_chart",
        "report_generate_html", "report_generate_pdf", "report_to_drive",
    ]
    return {name: (lambda: None) for name in tool_names}


def test_load_subagents_bq_explorer_has_expected_tools():
    subs = load_subagents(_full_registry())
    explorer = next(s for s in subs if s["name"] == "bq_explorer")
    assert len(explorer["tools"]) == 6


def test_load_subagents_main_agent_excluded():
    # main_agent.md must never appear as a subagent
    subs = load_subagents(_full_registry())
    assert all(s["name"] != "main_agent" for s in subs)
