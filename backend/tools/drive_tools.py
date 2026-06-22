"""
tools/drive_tools.py
─────────────────────────────────────────────────────────────────────────────
Google Drive / Sheets / Docs tools.

KEY USER FLOW: A user can paste a Google Sheets URL or share a spreadsheet,
and the agent will load it directly into the DataFrame cache for analysis.

    User: "Here's our sales data: https://docs.google.com/spreadsheets/d/1abc…"
    Agent: [calls sheet_from_url("https://docs.google.com/spreadsheets/d/1abc…")]
    → DataFrame cached, ready for df_describe / charts / reports

Auth: OAuth2 user credentials (not service-account) so the agent can access
files the *user* owns. First run opens a browser consent flow; token cached.

Tools:
  sheet_from_url      – ⭐ load a Google Sheet by pasting its URL
  drive_search_files  – search Drive by name / type
  drive_read_sheet    – read a sheet by spreadsheet ID + tab name
  drive_read_doc      – extract text from a Google Doc
  drive_read_csv      – download a CSV from Drive
  drive_upload_file   – upload a local file (chart / report) to Drive
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path

import pandas as pd
from googleapiclient.errors import HttpError

from config.settings import settings
from tools.bigquery_tools import set_cached_df


# ── Shared OAuth credential bootstrap ────────────────────────────────────────

_CREDS_CACHE: dict = {}


def _get_oauth_creds():
    """Single OAuth credential bootstrap shared by all Google services."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    if "creds" in _CREDS_CACHE and _CREDS_CACHE["creds"].valid:
        return _CREDS_CACHE["creds"]

    SCOPES = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/documents.readonly",
    ]
    token = settings.oauth_token_cache
    secrets = settings.oauth_client_secrets

    creds = None
    if os.path.exists(token):
        creds = Credentials.from_authorized_user_file(token, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secrets, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(token).write_text(creds.to_json())

    _CREDS_CACHE["creds"] = creds
    return creds


def _drive_service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_get_oauth_creds())


def _sheets_service():
    from googleapiclient.discovery import build
    return build("sheets", "v4", credentials=_get_oauth_creds())


def _docs_service():
    from googleapiclient.discovery import build
    return build("docs", "v1", credentials=_get_oauth_creds())


def _extract_sheet_id(url_or_id: str) -> str:
    """Extract the spreadsheet ID from a URL or return the raw ID."""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
    return match.group(1) if match else url_or_id


# ── Tools ─────────────────────────────────────────────────────────────────────

def sheet_from_url(
    url: str,
    sheet_name: str = "Sheet1",
    cache_key: str = "latest",
) -> str:
    """
    ⭐ Load a Google Sheet by pasting its full URL (or just the spreadsheet ID).

    Args:
        url:        Full Google Sheets URL or just the spreadsheet ID.
        sheet_name: Tab name to load (default 'Sheet1').
                    Ask the user if unsure — a Sheets URL doesn't include it.
        cache_key:  Name for this DataFrame (default 'latest').

    Returns:
        Shape + column summary. DataFrame is available for all analysis tools.
    """
    try:
        spreadsheet_id = _extract_sheet_id(url)
        service = _sheets_service()

        meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        tab_names = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if sheet_name not in tab_names:
            return (
                f"Tab '{sheet_name}' not found in this spreadsheet. "
                f"Available tabs: {tab_names}. "
                f"Call sheet_from_url again with the correct sheet_name."
            )

        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=sheet_name)
            .execute()
        )
        values = result.get("values", [])
        if not values:
            return f"Sheet '{sheet_name}' in {spreadsheet_id} appears empty."

        headers, *rows = values
        df = pd.DataFrame(rows, columns=headers)

        # TICKET-015: safe numeric coercion.
        # Skip entirely-empty columns so they are not silently converted to
        # all-NaN float. Only apply conversion when at least one value parsed
        # successfully and no non-null values were lost.
        for col in df.columns:
            if df[col].notna().sum() == 0:
                continue
            converted = pd.to_numeric(df[col], errors="coerce")
            original_non_null = df[col].notna().sum()
            converted_non_null = converted.notna().sum()
            if converted_non_null > 0 and converted_non_null == original_non_null:
                df[col] = converted

        set_cached_df(df, key=cache_key)
        return (
            f"✓ Sheet '{sheet_name}' loaded as '{cache_key}'. "
            f"Shape: {df.shape[0]:,} rows × {df.shape[1]} cols. "
            f"Columns: {list(df.columns)}"
        )
    except HttpError as e:
        return f"Could not read sheet (check the URL and that it's shared with you): {e}"


def drive_search_files(query: str, max_results: int = 10) -> str:
    """
    Search Google Drive for files matching a query.

    Args:
        query:       Free-text search or a Drive query string,
                     e.g. "name contains 'Q2 sales'" or just "Q2 sales".
        max_results: Maximum results to return (default 10).
    """
    try:
        service = _drive_service()
        if "contains" not in query and "=" not in query:
            query = f"fullText contains '{query}'"

        results = (
            service.files()
            .list(
                q=query + " and trashed=false",
                pageSize=max_results,
                fields="files(id, name, mimeType, modifiedTime)",
            )
            .execute()
        )
        files = results.get("files", [])
        if not files:
            return "No files matched."
        lines = [
            f"  [{f['mimeType'].rsplit('.', 1)[-1] if '.' in f['mimeType'] else f['mimeType'].split('/')[-1]}] {f['name']}  "
            f"(id: {f['id']}, modified: {f.get('modifiedTime','?')[:10]})"
            for f in files
        ]
        return f"Found {len(files)} file(s):\n" + "\n".join(lines)
    except HttpError as e:
        return f"Drive search failed: {e}"


def drive_read_sheet(
    spreadsheet_id: str,
    sheet_name: str = "Sheet1",
    cache_key: str = "latest",
) -> str:
    """
    Read a Google Sheet tab by spreadsheet ID.
    Prefer sheet_from_url when the user pastes a link.

    Args:
        spreadsheet_id: The ID from the spreadsheet URL.
        sheet_name:     Tab name (default 'Sheet1').
        cache_key:      DataFrame cache name.
    """
    return sheet_from_url(spreadsheet_id, sheet_name, cache_key)


def drive_read_doc(document_id: str) -> str:
    """
    Extract plain text from a Google Doc.

    Args:
        document_id: The doc ID from its URL (/document/d/<ID>/edit).

    Returns:
        Full extracted text (truncated to 4 000 chars).
    """
    try:
        service = _docs_service()
        doc = service.documents().get(documentId=document_id).execute()
        parts = []
        for elem in doc.get("body", {}).get("content", []):
            para = elem.get("paragraph")
            if para:
                for run in para.get("elements", []):
                    tr = run.get("textRun")
                    if tr:
                        parts.append(tr.get("content", ""))
        text = "".join(parts)
        if len(text) > 4000:
            text = text[:4000] + "\n… [truncated]"
        return text or "(Document appears empty)"
    except HttpError as e:
        return f"Could not read doc '{document_id}': {e}"


def drive_read_csv(file_id: str, cache_key: str = "latest") -> str:
    """
    Download a CSV file from Drive and cache it as a DataFrame.

    Args:
        file_id:   Drive file ID (get it from drive_search_files).
        cache_key: DataFrame cache name.
    """
    from googleapiclient.http import MediaIoBaseDownload

    try:
        service = _drive_service()
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, service.files().get_media(fileId=file_id))
        done = False
        while not done:
            _, done = dl.next_chunk()

        buf.seek(0)
        try:
            df = pd.read_csv(buf)
        except pd.errors.ParserError as e:
            return f"Downloaded file is not valid CSV: {e}"

        set_cached_df(df, key=cache_key)
        return (
            f"✓ CSV loaded as '{cache_key}'. "
            f"Shape: {df.shape[0]:,} rows × {df.shape[1]} cols. "
            f"Columns: {list(df.columns)}"
        )
    except HttpError as e:
        return f"Could not download CSV '{file_id}': {e}"


def drive_upload_file(local_path: str, folder_id: str = "") -> str:
    """
    Upload a local file (chart PNG, HTML report, PDF) to Google Drive.

    Args:
        local_path: Path to the local file.
        folder_id:  Optional Drive folder ID to upload into.

    Returns:
        Drive web URL of the uploaded file.
    """
    import mimetypes
    from googleapiclient.http import MediaFileUpload

    path = Path(local_path)
    if not path.exists():
        return f"File not found: {local_path}"

    try:
        service = _drive_service()
        mime, _ = mimetypes.guess_type(str(path))
        meta: dict = {"name": path.name}
        if folder_id:
            meta["parents"] = [folder_id]

        file = (
            service.files()
            .create(
                body=meta,
                media_body=MediaFileUpload(str(path), mimetype=mime or "application/octet-stream"),
                fields="id, webViewLink",
            )
            .execute()
        )
        return f"✓ Uploaded '{path.name}' → {file.get('webViewLink', '(no link)')}"
    except HttpError as e:
        return f"Upload failed: {e}"
