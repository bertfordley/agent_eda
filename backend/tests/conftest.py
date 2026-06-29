"""
Shared pytest fixtures and environment bootstrap.

IMPORTANT: The os.environ.setdefault calls at module level MUST run before any
test module imports tools.bigquery_tools or config.settings, because
config/settings.py evaluates _require_env("GCP_PROJECT_ID") at class-body
level (import time). conftest.py is always loaded by pytest before test modules.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("GCP_PROJECT_ID", "test-project-id")
os.environ.setdefault("BQ_DEFAULT_DATASET", "test_dataset")
os.environ.setdefault("TELEMETRY_ENABLED", "false")
os.environ.setdefault("AGENT_FS_BACKEND", "state")


@pytest.fixture
def tmp_skills_dir(tmp_path: Path) -> Path:
    """Create a temporary skills directory structure for testing skill loading."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir()

    skill_a = skills_root / "key-comparison"
    skill_a.mkdir()
    (skill_a / "SKILL.md").write_text(
        "---\nname: key-comparison\ndescription: Compare two datasets on a join key.\n"
        "when_to_use: User wants to compare or diff two tables.\n---\n"
        "1. Call df_check_key on the join column.\n2. Call df_compare.\n"
    )

    skill_b = skills_root / "data-quality"
    skill_b.mkdir()
    (skill_b / "SKILL.md").write_text(
        "---\nname: data-quality\ndescription: Audit a table for quality issues.\n---\n"
        "1. bq_describe_table.\n2. Check nulls.\n"
    )

    return skills_root
