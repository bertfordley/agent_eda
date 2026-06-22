"""
config/settings.py  +  config/gcp.py  (combined for brevity)
─────────────────────────────────────────────────────────────────────────────
Typed settings from .env / environment, and the GCP client factory.

Auth priority (standard ADC order):
  1. GOOGLE_APPLICATION_CREDENTIALS → service-account JSON
  2. `gcloud auth application-default login`  (local dev)
  3. Workload Identity (GKE / Cloud Run)
"""

from __future__ import annotations

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


def _parse_cors_origins(name: str, default: str) -> list[str]:
    """Parse CORS_ALLOW_ORIGINS as a comma-separated list of origin URLs."""
    raw = os.getenv(name, default)
    return [o.strip() for o in raw.split(",") if o.strip()]


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

    # Drive OAuth
    oauth_client_secrets: str = os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS", "./oauth_client_secrets.json")
    oauth_token_cache: str = os.getenv("GOOGLE_OAUTH_TOKEN_CACHE", "./oauth_token.json")

    # Deep Agents filesystem backend
    agent_fs_backend: str = os.getenv("AGENT_FS_BACKEND", "state")   # "state" | "local"
    agent_workspace_dir: Path = Path(os.getenv("AGENT_WORKSPACE_DIR", "./workspace"))

    # Output dirs
    charts_dir: Path = Path(os.getenv("CHARTS_DIR", "./charts"))
    reports_dir: Path = Path(os.getenv("REPORTS_DIR", "./reports"))

    # TICKET-009: restrict CORS to known origins instead of wildcard "*".
    # CORS_ALLOW_ORIGINS is a comma-separated list of allowed origin URLs.
    # Default covers Vite dev (:5173) and Vite preview (:4173) servers.
    cors_allow_origins: list[str] = _parse_cors_origins(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://localhost:4173",
    )

    def __init__(self):
        for d in [self.charts_dir, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)
        if self.agent_fs_backend not in {"state", "local"}:
            raise ValueError(
                f"AGENT_FS_BACKEND must be 'state' or 'local', got '{self.agent_fs_backend}'"
            )
        if self.agent_fs_backend == "local":
            self.agent_workspace_dir.mkdir(parents=True, exist_ok=True)


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
