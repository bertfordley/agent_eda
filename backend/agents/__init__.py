"""
agents package.

Re-exports the orchestrator entrypoints lazily (PEP 562) so that importing the
lightweight agents.loader (markdown → subagent specs) does NOT pull in deepagents
/ langchain / the full tool stack. Keeps the loader importable in isolation for
fast unit tests.

`from agents import build_agent` (etc.) still works and resolves on first use.
"""

from __future__ import annotations

__all__ = ["build_agent", "get_agent", "chat"]


def __getattr__(name: str):
    if name in __all__:
        from agents import orchestrator

        return getattr(orchestrator, name)
    raise AttributeError(f"module 'agents' has no attribute {name!r}")
