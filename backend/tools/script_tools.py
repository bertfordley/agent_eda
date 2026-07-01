"""
tools/script_tools.py
──────────────────────────────────────────────────────────────────────────────
The run_skill_script tool — execute a vetted script that ships inside a skill's
own folder.

SECURITY MODEL (why this is narrow by design):
  • Disabled by default. Nothing runs unless SKILL_EXEC_ENABLED=true.
  • The agent can only run scripts that live under  skills/<name>/scripts/  — a
    resolved path-traversal guard rejects anything that escapes that folder, so
    the model can never point this at an arbitrary host path.
  • Only extensions in ALLOWED_EXT run. No shell: subprocess is invoked with an
    argv list (shell=False), so a JSON --matches argument (with braces, quotes,
    spaces) is passed as a single element with zero shell escaping and no
    injection surface. Never switch to shell=True or string-join argv.
  • A minimal environment is passed (see _safe_env) so executed code cannot read
    GCP credentials, DB URIs, or the checkpoint encryption key from os.environ.
  • Bounded: timeout and output-size caps come from settings.

The tool is deliberately generic (skill_name, script, args). It does not parse
or bound flag values like --config/--profile/--matches; a skill's own script is
responsible for resolving its assets/ files and validating its inputs. cwd is
set to the skill's base dir so the script can read assets/<name> relative to
itself.
"""

from __future__ import annotations

import subprocess
import sys
import time

from config.settings import settings
from skills.loader import get_skill_dir, list_skill_names

# Marker prefixes so callers (and tests) can assert on the failure mode.
SKILL_EXEC_DISABLED = "SKILL_EXEC_DISABLED"
SKILL_NOT_FOUND = "SKILL_NOT_FOUND"
SKILL_SCRIPT_NOT_FOUND = "SKILL_SCRIPT_NOT_FOUND"
SKILL_SCRIPT_DENIED = "SKILL_SCRIPT_DENIED"
SKILL_SCRIPT_TIMEOUT = "SKILL_SCRIPT_TIMEOUT"
SKILL_SCRIPT_ERROR = "SKILL_SCRIPT_ERROR"

# Only these script types may be executed. Python-only for now; adding ".sh"
# here (plus a bash dispatch below) is the single change needed to allow shell.
ALLOWED_EXT = {".py"}

# Environment variables safe to forward to executed scripts. Deliberately does
# NOT include secrets (GCP creds, CHECKPOINT_*, DB URIs) — see the sandbox docs:
# never hand secrets to code the model can influence.
_SAFE_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")


def _safe_env() -> dict[str, str]:
    """A minimal environment with no inherited secrets."""
    import os

    env = {k: os.environ[k] for k in _SAFE_ENV_KEYS if k in os.environ}
    env.setdefault("PATH", "/usr/bin:/bin")
    return env


def _cap_output(text: str) -> str:
    """Truncate combined script output to the configured ceiling."""
    limit = settings.skill_script_max_output_chars
    if len(text) > limit:
        excess = len(text) - limit
        return text[:limit] + f"\n…[truncated {excess} chars]"
    return text


def run_skill_script(skill_name: str, script: str, args: list[str] | None = None) -> str:
    """
    Run a vetted script that ships inside a skill's folder and return its output.

    Only scripts located under the named skill's scripts/ directory may run, and
    only when SKILL_EXEC_ENABLED is set. The script's working directory is the
    skill's base folder, so it can read its own assets/ files.

    Args:
        skill_name: Skill name from the skills index (e.g. 'match-scoring').
        script:     Script filename inside the skill's scripts/ folder
                    (e.g. 'evaluate_match_score.py'). Must stay inside that folder.
        args:       Optional command-line arguments passed to the script, e.g.
                    ['--config', 'cfg.yaml', '--profile', 'p.yaml', '--matches', '{...}'].
                    A JSON --matches value is passed verbatim (no shell escaping).
    """
    # Import here (not at module top) so telemetry can import tools without a
    # circular import — mirrors bq_run_query's lazy governance import.
    from telemetry.governance import log_script_executed

    started = time.monotonic()
    message, accepted, reason, exit_code = _evaluate(skill_name, script, args)
    log_script_executed(
        skill_name=skill_name,
        script=script,
        args=args,
        accepted=accepted,
        rejection_reason=reason,
        exit_code=exit_code,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return message


def _evaluate(
    skill_name: str, script: str, args: list[str] | None
) -> tuple[str, bool, str | None, int | None]:
    """Do the work; return (message, accepted, rejection_reason, exit_code).

    accepted=True only when the script was actually launched. Every early return
    is a pre-launch rejection (accepted=False). Never raises.
    """
    if not settings.skill_exec_enabled:
        msg = (
            f"[{SKILL_EXEC_DISABLED}] Script execution is turned off. "
            "Set SKILL_EXEC_ENABLED=true to enable."
        )
        return msg, False, SKILL_EXEC_DISABLED, None

    # Validate args: must be a list of strings the argv can accept.
    arg_list: list[str] = []
    if args is not None:
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            msg = f"[{SKILL_SCRIPT_ERROR}] args must be a list of strings."
            return msg, False, "args must be a list of strings", None
        arg_list = args

    base = get_skill_dir(skill_name)
    if base is None:
        available = ", ".join(list_skill_names()) or "(none configured)"
        msg = f"[{SKILL_NOT_FOUND} name='{skill_name}'] Available skills: {available}."
        return msg, False, SKILL_NOT_FOUND, None

    # KEY CONTROL: resolve, then confirm the target stays inside scripts/.
    # Resolve BEFORE the bound check so '..' and symlinks cannot escape.
    scripts_root = (base / "scripts").resolve()
    target = (scripts_root / script).resolve()
    if not target.is_relative_to(scripts_root):
        msg = (
            f"[{SKILL_SCRIPT_DENIED}] Script path escapes the skill's scripts/ folder: "
            f"{script!r}."
        )
        return msg, False, SKILL_SCRIPT_DENIED, None
    if target.suffix not in ALLOWED_EXT:
        allowed = ", ".join(sorted(ALLOWED_EXT))
        msg = (
            f"[{SKILL_SCRIPT_DENIED}] Script type {target.suffix or '(none)'!r} is not "
            f"allowed. Permitted: {allowed}."
        )
        return msg, False, SKILL_SCRIPT_DENIED, None
    if not target.is_file():
        msg = (
            f"[{SKILL_SCRIPT_NOT_FOUND}] {script!r} not found under "
            f"{skill_name}/scripts/."
        )
        return msg, False, SKILL_SCRIPT_NOT_FOUND, None

    argv = [sys.executable, str(target), *arg_list]

    try:
        proc = subprocess.run(
            argv,
            cwd=str(base),
            env=_safe_env(),
            capture_output=True,
            text=True,
            timeout=settings.skill_script_timeout_sec,
        )
    except subprocess.TimeoutExpired:
        msg = (
            f"[{SKILL_SCRIPT_TIMEOUT}] {script!r} exceeded the "
            f"{settings.skill_script_timeout_sec}s time limit and was terminated."
        )
        return msg, False, SKILL_SCRIPT_TIMEOUT, None
    except Exception as exc:  # noqa: BLE001 — never raise into the graph.
        msg = f"[{SKILL_SCRIPT_ERROR}] Failed to run {script!r}: {exc}"
        return msg, False, SKILL_SCRIPT_ERROR, None

    combined = (proc.stdout or "") + (proc.stderr or "")
    body = _cap_output(combined).rstrip()
    status = "" if proc.returncode == 0 else f"\n(exit code {proc.returncode})"
    msg = f"[{skill_name}/{script}]\n{body}{status}"
    return msg, True, None, proc.returncode
