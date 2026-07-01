"""
config/settings.py
─────────────────────────────────────────────────────────────────────────────
Typed settings from .env / environment, and the GCP client factory.

Auth priority (standard ADC order):
  1. GOOGLE_APPLICATION_CREDENTIALS → service-account JSON
  2. `gcloud auth application-default login`  (local dev)
  3. Workload Identity (GKE / Cloud Run)
"""

from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache
from pathlib import Path

import google.auth
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

load_dotenv()


# ── Env-var parsing helpers ───────────────────────────────────────────────────

def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(
            f"Required environment variable {name} is not set. "
            f"Set it in your .env file or shell before starting the app."
        )
    return val


def _parse_float(name: str, default: str) -> float:
    raw = os.getenv(name, default)
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"Env var {name}='{raw}' is not a valid float.")


def _parse_int(name: str, default: str) -> int:
    raw = os.getenv(name, default)
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Env var {name}='{raw}' is not a valid integer.")


def _parse_bool(name: str, default: str) -> bool:
    """Parse an env var as a boolean. Truthy: '1','true','yes','on' (case-insensitive)."""
    raw = os.getenv(name, default).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _parse_cors_origins(name: str, default: str) -> list[str]:
    """Parse CORS_ALLOW_ORIGINS as a comma-separated list of origin URLs."""
    raw = os.getenv(name, default)
    return [o.strip() for o in raw.split(",") if o.strip()]


def _parse_mcp_servers(name: str) -> list[dict]:
    """Parse MCP_SERVERS — a JSON list of remote MCP server connection specs.

    Each entry: {"name": "knowledge_base", "url": "https://...", "transport": "streamable_http"}.
    Empty/unset → [] (no remote tools; fully backward compatible). Fails fast on
    malformed JSON so a typo never silently disables the knowledge base.
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    import json

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Env var {name} is not valid JSON: {exc}")
    if not isinstance(parsed, list) or not all(isinstance(s, dict) for s in parsed):
        raise ValueError(f"Env var {name} must be a JSON list of objects.")
    for s in parsed:
        if not s.get("name") or not s.get("url"):
            raise ValueError(f"Each {name} entry needs 'name' and 'url'.")
    return parsed


# ── Settings ──────────────────────────────────────────────────────────────────

class Settings:
    # GCP
    gcp_project_id: str = _require_env("GCP_PROJECT_ID")
    gcp_region: str = os.getenv("GCP_REGION", "us-central1")

    # Vertex AI
    vertex_model: str = os.getenv("VERTEX_AI_MODEL", "gemini-2.0-flash")
    vertex_temperature: float = _parse_float("VERTEX_AI_TEMPERATURE", "0.0")

    # BigQuery
    bq_default_dataset: str = os.getenv("BQ_DEFAULT_DATASET", "")
    bq_max_bytes_billed: int = _parse_int("BQ_MAX_BYTES_BILLED", str(10 * 1_000_000_000))

    # Data catalog — per-deployment domain scope + NL schema descriptions.
    # Absent file → unscoped (all datasets visible). See config/catalog.py.
    data_catalog_path: str = os.getenv("DATA_CATALOG_PATH", "./data_catalog.yaml")

    # Remote MCP servers (e.g. a knowledge base) consumed as additional agent
    # tools. JSON list; empty by default → no remote tools. See agents/mcp_client.py.
    mcp_servers: list[dict] = _parse_mcp_servers("MCP_SERVERS")

    # Drive OAuth
    oauth_client_secrets: str = os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS", "./oauth_client_secrets.json")
    oauth_token_cache: str = os.getenv("GOOGLE_OAUTH_TOKEN_CACHE", "./oauth_token.json")

    # Deep Agents filesystem backend
    agent_fs_backend: str = os.getenv("AGENT_FS_BACKEND", "state")   # "state" | "local"
    agent_workspace_dir: Path = Path(os.getenv("AGENT_WORKSPACE_DIR", "./workspace"))

    # Skill script execution (opt-in; disabled by default). When enabled, the
    # run_skill_script tool may execute vetted scripts that ship inside a skill's
    # own scripts/ folder. Off by default to preserve the read-only posture.
    skill_exec_enabled: bool = _parse_bool("SKILL_EXEC_ENABLED", "false")
    skill_script_timeout_sec: int = _parse_int("SKILL_SCRIPT_TIMEOUT_SEC", "30")
    skill_script_max_output_chars: int = _parse_int("SKILL_SCRIPT_MAX_OUTPUT_CHARS", "10000")

    # Output dirs
    charts_dir: Path = Path(os.getenv("CHARTS_DIR", "./charts"))
    reports_dir: Path = Path(os.getenv("REPORTS_DIR", "./reports"))

    # CORS — comma-separated allowed frontend origins.
    # Default covers Vite dev (:5173) and Vite preview (:4173).
    cors_allow_origins: list[str] = _parse_cors_origins(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://localhost:4173",
    )

    # ── Telemetry ──────────────────────────────────────────────────────────────
    # TELEMETRY_ENABLED   — master switch; set to false to silence all emission.
    # TELEMETRY_LEVEL     — "standard": metadata + governance (default).
    #                       "debug": also captures full model message payloads.
    # TELEMETRY_MAX_VALUE_CHARS — per-field string truncation ceiling.
    # TELEMETRY_SAMPLE_ROWS     — rows included when summarising a DataFrame.
    telemetry_enabled: bool = _parse_bool("TELEMETRY_ENABLED", "true")
    telemetry_level: str = os.getenv("TELEMETRY_LEVEL", "standard")
    telemetry_max_value_chars: int = _parse_int("TELEMETRY_MAX_VALUE_CHARS", "2000")
    telemetry_sample_rows: int = _parse_int("TELEMETRY_SAMPLE_ROWS", "5")

    # ── Checkpoint persistence ─────────────────────────────────────────────────
    # checkpoint_enabled is derived in __init__ after the encryption key is
    # validated — do not read it before __init__ completes.
    checkpoint_db_uri: str = os.getenv("CHECKPOINT_DB_URI", "")
    checkpoint_encryption_key: str = os.getenv("CHECKPOINT_ENCRYPTION_KEY", "")
    checkpoint_pool_min: int = _parse_int("CHECKPOINT_POOL_MIN", "2")
    checkpoint_pool_max: int = _parse_int("CHECKPOINT_POOL_MAX", "10")
    checkpoint_enabled: bool = False

    def __init__(self):
        for d in [self.charts_dir, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)

        if self.agent_fs_backend not in {"state", "local"}:
            raise ValueError(
                f"AGENT_FS_BACKEND must be 'state' or 'local', got '{self.agent_fs_backend}'"
            )
        if self.agent_fs_backend == "local":
            self.agent_workspace_dir.mkdir(parents=True, exist_ok=True)

        if self.telemetry_level not in {"standard", "debug"}:
            raise ValueError(
                f"TELEMETRY_LEVEL must be 'standard' or 'debug', got '{self.telemetry_level}'"
            )

        # Force LangSmith / LangChain tracing off so Deep Agents' bundled
        # langsmith client never ships traces to the cloud regardless of what
        # the environment has set. setdefault preserves an explicit "true" if
        # someone intentionally enables it, but that must be a conscious choice.
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
        os.environ.setdefault("LANGSMITH_TRACING", "false")

        # Restrict LangGraph checkpoint deserialization to safe types — mitigates
        # the msgpack-deserialization RCE class (CVE-2026-28277). setdefault so it
        # can be consciously overridden, but secure-by-default.
        os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

        # Derive checkpoint_enabled and enforce the encryption invariant.
        # Persistence is opt-in: if no URI is set the agent runs single-turn.
        self.checkpoint_enabled = bool(self.checkpoint_db_uri)

        if not self.checkpoint_enabled:
            _log = logging.getLogger(__name__)
            _log.warning(
                "CHECKPOINT_DB_URI is not set — running in dev fallback mode. "
                "Conversation memory is client-provided (no server-side audit trail). "
                "DEV ONLY: do NOT use for regulated data in production. "
                "Set CHECKPOINT_DB_URI and CHECKPOINT_ENCRYPTION_KEY to enable "
                "server-authoritative persistence."
            )
        else:
            # Encryption is mandatory when persistence is on: conversation history
            # may contain regulated data and must never be stored in plaintext.
            if not self.checkpoint_encryption_key:
                raise ValueError(
                    "CHECKPOINT_DB_URI is set but CHECKPOINT_ENCRYPTION_KEY is empty. "
                    "Encryption is mandatory whenever persistence is on. "
                    "Generate a 32-byte AES-256 key with: openssl rand -base64 32"
                )
            try:
                key_bytes = base64.b64decode(self.checkpoint_encryption_key)
            except Exception:
                raise ValueError(
                    "CHECKPOINT_ENCRYPTION_KEY is not valid base64. "
                    "Generate a 32-byte AES-256 key with: openssl rand -base64 32"
                )
            if len(key_bytes) != 32:
                raise ValueError(
                    f"CHECKPOINT_ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256); "
                    f"got {len(key_bytes)} bytes. "
                    "Generate a key with: openssl rand -base64 32"
                )


settings = Settings()


# ── GCP Credentials ───────────────────────────────────────────────────────────

GCP_SCOPES = [
    "https://www.googleapis.com/auth/bigquery",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/cloud-platform",
]


@lru_cache(maxsize=1)
def get_credentials():
    sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if sa_path and Path(sa_path).exists():
        return service_account.Credentials.from_service_account_file(sa_path, scopes=GCP_SCOPES)
    creds, _ = google.auth.default(scopes=GCP_SCOPES)
    return creds


@lru_cache(maxsize=1)
def get_bq_client() -> bigquery.Client:
    return bigquery.Client(project=settings.gcp_project_id, credentials=get_credentials())


def safe_query_config() -> bigquery.QueryJobConfig:
    return bigquery.QueryJobConfig(
        maximum_bytes_billed=settings.bq_max_bytes_billed,
        use_query_cache=True,
    )


def dry_run_query_config() -> bigquery.QueryJobConfig:
    """Config for a cost-estimation dry run — no cache, no billing."""
    return bigquery.QueryJobConfig(
        dry_run=True,
        use_query_cache=False,
    )
