"""
frontmatter.py
──────────────────────────────────────────────────────────────────────────────
Pure parser for YAML-frontmatter Markdown files (agent and skill definitions).

Format:
    ---
    name: bq_explorer
    description: ...
    ---
    <body text...>

No external dependencies beyond pyyaml — importable in isolation (test-friendly),
mirroring history.py.
"""

from __future__ import annotations

import yaml

_DELIM = "---"


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a frontmatter document into (metadata dict, body string).

    A document without a leading `---` block yields ({}, original_text). The
    body is returned stripped of its leading/trailing blank lines.
    """
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != _DELIM:
        return {}, text.strip()

    # Find the closing delimiter.
    for i in range(1, len(lines)):
        if lines[i].strip() == _DELIM:
            front_raw = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :]).strip()
            meta = yaml.safe_load(front_raw) or {}
            if not isinstance(meta, dict):
                raise ValueError("Frontmatter must be a YAML mapping.")
            return meta, body

    raise ValueError("Frontmatter opened with '---' but never closed.")
