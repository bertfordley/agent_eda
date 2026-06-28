"""
config package.

Re-exports the settings singleton and GCP client factories lazily (PEP 562) so
that importing a lightweight submodule such as `config.catalog` does NOT pull in
google.auth or trigger settings' required-env checks. This keeps pure modules
importable in isolation for fast, dependency-free unit tests.

Correct import patterns:
    from config.settings import settings          # the Settings() singleton
    from config.settings import get_bq_client     # GCP client factory

Avoid `from config import settings` — that returns the config.settings MODULE
(Python submodule takes precedence over __getattr__), not the singleton.
`import config; config.settings` does work via __getattr__ and returns the
singleton, but the submodule-direct form is clearer.
"""

from __future__ import annotations

__all__ = ["settings", "get_bq_client", "get_credentials", "safe_query_config"]


def __getattr__(name: str):
    if name in __all__:
        from config import settings as _settings_mod

        return getattr(_settings_mod, name)
    raise AttributeError(f"module 'config' has no attribute {name!r}")
