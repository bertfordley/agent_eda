"""
Unit tests for tools/script_tools.py (run_skill_script).

Covers the security gates (disabled, unknown skill, path traversal, extension
allowlist, missing file), the execution bounds (timeout, output truncation), and
the happy paths (arg pass-through, asset access via cwd, JSON --matches integrity).
"""

from __future__ import annotations

# Stub out the tools package before importing so tools/__init__.py (which eagerly
# imports matplotlib/jinja2/etc.) does not run — mirrors test_bigquery_tools.py.
import sys
import types
from pathlib import Path

if "tools" not in sys.modules:
    _tools_stub = types.ModuleType("tools")
    _tools_stub.__path__ = [str(Path(__file__).parent.parent / "tools")]
    _tools_stub.__package__ = "tools"
    sys.modules["tools"] = _tools_stub

import pytest

import tools.script_tools as st
from config.settings import settings
from tools.script_tools import (
    SKILL_EXEC_DISABLED,
    SKILL_NOT_FOUND,
    SKILL_SCRIPT_DENIED,
    SKILL_SCRIPT_NOT_FOUND,
    SKILL_SCRIPT_TIMEOUT,
    run_skill_script,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def enabled(monkeypatch):
    """Turn on execution on the imported settings singleton (not via env)."""
    monkeypatch.setattr(settings, "skill_exec_enabled", True)


@pytest.fixture
def skill(tmp_path, monkeypatch):
    """A temp skill dir with scripts/ + assets/, wired via get_skill_dir."""
    base = tmp_path / "match-scoring"
    (base / "scripts").mkdir(parents=True)
    (base / "assets").mkdir()
    monkeypatch.setattr(
        st, "get_skill_dir", lambda name: base if name == "match-scoring" else None
    )
    return base


def _write_script(base: Path, name: str, body: str) -> None:
    (base / "scripts" / name).write_text(body)


# ── Security gates ────────────────────────────────────────────────────────────


def test_disabled_by_default_runs_nothing(monkeypatch, skill):
    monkeypatch.setattr(settings, "skill_exec_enabled", False)

    def _boom(*a, **k):  # subprocess must never be reached
        raise AssertionError("subprocess.run should not be called when disabled")

    monkeypatch.setattr(st.subprocess, "run", _boom)

    result = run_skill_script("match-scoring", "whatever.py")

    assert SKILL_EXEC_DISABLED in result


def test_unknown_skill(enabled, monkeypatch):
    monkeypatch.setattr(st, "get_skill_dir", lambda name: None)
    monkeypatch.setattr(st, "list_skill_names", lambda: ["a", "b"])

    result = run_skill_script("nope", "x.py")

    assert SKILL_NOT_FOUND in result
    assert "a, b" in result


@pytest.mark.parametrize("bad", ["../../etc/passwd", "/etc/passwd", "../secret.py"])
def test_path_traversal_denied(enabled, skill, bad):
    result = run_skill_script("match-scoring", bad)

    assert SKILL_SCRIPT_DENIED in result


def test_disallowed_extension_denied(enabled, skill):
    (skill / "scripts" / "notes.txt").write_text("nope")

    result = run_skill_script("match-scoring", "notes.txt")

    assert SKILL_SCRIPT_DENIED in result


def test_missing_file(enabled, skill):
    result = run_skill_script("match-scoring", "ghost.py")

    assert SKILL_SCRIPT_NOT_FOUND in result


def test_non_string_args_rejected(enabled, skill):
    _write_script(skill, "hi.py", "print('x')")

    result = run_skill_script("match-scoring", "hi.py", args=[1, 2])  # type: ignore[list-item]

    assert "args must be a list of strings" in result


# ── Execution bounds ──────────────────────────────────────────────────────────


def test_timeout(enabled, skill, monkeypatch):
    monkeypatch.setattr(settings, "skill_script_timeout_sec", 1)
    _write_script(skill, "slow.py", "import time\ntime.sleep(5)\n")

    result = run_skill_script("match-scoring", "slow.py")

    assert SKILL_SCRIPT_TIMEOUT in result


def test_output_truncated(enabled, skill, monkeypatch):
    monkeypatch.setattr(settings, "skill_script_max_output_chars", 50)
    _write_script(skill, "loud.py", "print('A' * 500)")

    result = run_skill_script("match-scoring", "loud.py")

    assert "truncated" in result


def test_nonzero_exit_reported(enabled, skill):
    _write_script(skill, "fail.py", "import sys\nsys.exit(3)")

    result = run_skill_script("match-scoring", "fail.py")

    assert "(exit code 3)" in result


# ── Happy paths ───────────────────────────────────────────────────────────────


def test_happy_path(enabled, skill):
    _write_script(skill, "hello.py", "print('HELLO_TOKEN')")

    result = run_skill_script("match-scoring", "hello.py")

    assert "HELLO_TOKEN" in result
    assert "exit code" not in result


def test_args_passthrough_and_assets(enabled, skill):
    # cwd is the skill base dir, so the script can read assets/ relative to cwd.
    (skill / "assets" / "config.txt").write_text("ASSET_CONTENT")
    _write_script(
        skill,
        "evaluate_match_score.py",
        "import sys\n"
        "print('ARGS=' + ' '.join(sys.argv[1:]))\n"
        "print('ASSET=' + open('assets/config.txt').read())\n",
    )

    result = run_skill_script(
        "match-scoring",
        "evaluate_match_score.py",
        args=["--config", "config.txt", "--profile", "p.txt"],
    )

    assert "ARGS=--config config.txt --profile p.txt" in result
    assert "ASSET=ASSET_CONTENT" in result


def test_governance_event_emitted(enabled, skill, monkeypatch):
    import telemetry.governance as gov

    calls = []
    monkeypatch.setattr(gov, "log_script_executed", lambda **kw: calls.append(kw))
    _write_script(skill, "hello.py", "print('ok')")

    run_skill_script("match-scoring", "hello.py")

    assert len(calls) == 1
    assert calls[0]["accepted"] is True
    assert calls[0]["exit_code"] == 0
    assert calls[0]["script"] == "hello.py"


def test_governance_event_on_denied(enabled, skill, monkeypatch):
    import telemetry.governance as gov

    calls = []
    monkeypatch.setattr(gov, "log_script_executed", lambda **kw: calls.append(kw))

    run_skill_script("match-scoring", "../escape.py")

    assert len(calls) == 1
    assert calls[0]["accepted"] is False
    assert calls[0]["exit_code"] is None


def test_json_matches_integrity(enabled, skill):
    # Proves shell=False argv passes a JSON dict verbatim (no split/escaping).
    _write_script(
        skill,
        "evaluate_match_score.py",
        "import argparse, json\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--matches')\n"
        "a = p.parse_args()\n"
        "d = json.loads(a.matches)\n"
        "print('BUYER=' + d['buyer'])\n"
        "print('TAG0=' + d['tags'][0])\n",
    )
    matches = '{"buyer": "ACME", "min_score": 0.8, "tags": ["a b", "c"]}'

    result = run_skill_script(
        "match-scoring", "evaluate_match_score.py", args=["--matches", matches]
    )

    assert "BUYER=ACME" in result
    assert "TAG0=a b" in result
