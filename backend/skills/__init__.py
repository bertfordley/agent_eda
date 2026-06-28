"""
skills package.

Holds reusable analysis playbooks ("skills") as SKILL.md files, one per
subdirectory, plus a lightweight loader. Skills are model-agnostic: only a
compact index sits in the system prompt; the agent pulls a skill's full
instructions on demand via the load_skill tool (progressive disclosure).
"""
