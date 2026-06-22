"""
tools/report_tools.py
─────────────────────────────────────────────────────────────────────────────
Report assembly tools. Deep Agents' virtual filesystem means the agent can
write report sections to files progressively during a long session, then
assemble them at the end — rather than keeping everything in context.

Tools:
  report_start         – begin a new report (clears staging state)
  report_add_section   – add a heading + text body
  report_add_chart     – embed a chart PNG by file path
  report_generate_html – render to a self-contained HTML file
  report_generate_pdf  – convert HTML → PDF (requires weasyprint)
  report_to_drive      – upload finished report to Google Drive
"""

from __future__ import annotations

import base64
import datetime
import threading
import uuid
from pathlib import Path
from typing import Any

from jinja2 import Template

from config.settings import settings

# WARNING: single global report. For true multi-user isolation, key this dict
# by session_id passed from server.py.
# TICKET-006: protect _report with a threading.Lock so concurrent FastAPI
# requests cannot interleave their report content or wipe each other's state.
_report: dict[str, Any] = {"title": "EDA Report", "sections": [], "charts": [], "html_path": None}
_report_lock = threading.Lock()


def _reset(title: str) -> None:
    _report.update(title=title, sections=[], charts=[], html_path=None)


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ title }}</title>
<style>
  body  { font-family:'Segoe UI',Arial,sans-serif; margin:0; background:#f7f8fa; color:#1a1a2e; }
  .page { max-width:960px; margin:40px auto; background:#fff; padding:48px 56px;
          border-radius:8px; box-shadow:0 2px 16px rgba(0,0,0,.08); }
  h1    { font-size:2rem; border-bottom:3px solid #1a73e8; padding-bottom:12px; }
  h2    { font-size:1.3rem; color:#1a73e8; margin-top:2.4rem; }
  pre   { background:#f1f3f4; padding:16px; border-radius:6px; overflow-x:auto;
          font-size:.82rem; line-height:1.5; white-space:pre-wrap; }
  img   { max-width:100%; border-radius:6px; margin:16px 0;
          box-shadow:0 1px 8px rgba(0,0,0,.12); }
  .meta { color:#888; font-size:.85rem; margin-bottom:2rem; }
</style>
</head>
<body><div class="page">
  <h1>{{ title }}</h1>
  <p class="meta">Generated {{ ts }} · EDA Agent</p>
  {% for s in sections %}
  <h2>{{ s.heading }}</h2><pre>{{ s.content }}</pre>
  {% endfor %}
  {% for b64 in charts %}
  <img src="data:image/png;base64,{{ b64 }}" alt="chart">
  {% endfor %}
</div></body></html>"""


def report_start(title: str = "EDA Report") -> str:
    """
    Begin a new report, clearing any previous staging state.

    Args:
        title: Report title shown in the heading.
    """
    # TICKET-006: hold lock for the duration of the state mutation.
    with _report_lock:
        _reset(title)
    return f"Report started: '{title}'"


def report_add_section(heading: str, content: str) -> str:
    """
    Add a text section to the current report.

    Args:
        heading: Section heading, e.g. 'Monthly Revenue Trends'.
        content: Body text — paste analysis output directly here.
    """
    # TICKET-006: hold lock for the duration of the state mutation.
    with _report_lock:
        _report["sections"].append({"heading": heading, "content": content})
    return f"Section '{heading}' added."


def report_add_chart(chart_path: str) -> str:
    """
    Embed a chart image into the current report by file path.

    Args:
        chart_path: File path returned by any chart_* tool.
    """
    p = Path(chart_path)
    if not p.exists():
        return f"Chart not found: {chart_path}"
    # TICKET-006: hold lock for the duration of the state mutation.
    with _report_lock:
        _report["charts"].append(str(p))
    return f"Chart '{p.name}' added to report."


def report_generate_html() -> str:
    """
    Render the staged report to a self-contained HTML file.
    Charts are embedded as base64 so the file is fully portable.

    Returns:
        File path of the generated HTML.
    """
    # TICKET-006: hold lock for the full read-render-write cycle.
    with _report_lock:
        b64s = []
        for p in _report["charts"]:
            path = Path(p)
            if path.exists():
                b64s.append(base64.b64encode(path.read_bytes()).decode())

        html = Template(_HTML).render(
            title=_report["title"],
            sections=_report["sections"],
            charts=b64s,
            ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        slug = _report["title"].lower().replace(" ", "_")[:30]
        out = settings.reports_dir / f"{slug}_{uuid.uuid4().hex[:6]}.html"
        out.write_text(html, encoding="utf-8")
        _report["html_path"] = str(out)
    return f"HTML report saved: {out}"


def report_generate_pdf() -> str:
    """
    Convert the most recently generated HTML report to PDF.
    Requires `weasyprint` (included in pyproject.toml dependencies).

    Returns:
        File path of the PDF, or a fallback message if weasyprint is missing
        or its system libraries are absent.
    """
    # TICKET-006: hold lock while reading shared state.
    with _report_lock:
        html_path = _report.get("html_path")

    if not html_path or not Path(html_path).exists():
        return "No HTML report found. Run report_generate_html first."
    try:
        from weasyprint import HTML as WP
        pdf = Path(html_path).with_suffix(".pdf")
        WP(filename=html_path).write_pdf(str(pdf))
        return f"PDF saved: {pdf}"
    except ImportError:
        return f"weasyprint not installed. HTML is at: {html_path}"
    # TICKET-025: weasyprint raises OSError when system libraries are absent
    # even though the Python package imports successfully.
    except OSError as e:
        return (
            f"weasyprint is installed but its system libraries are missing "
            f"({e}). HTML report is available at: {html_path}"
        )


def report_to_drive(folder_id: str = "") -> str:
    """
    Upload the latest report (PDF preferred, HTML fallback) to Google Drive.

    Args:
        folder_id: Optional Drive folder ID. Uploads to root if blank.
    """
    # TICKET-006: hold lock while reading shared state.
    with _report_lock:
        html_path = _report.get("html_path")

    if not html_path:
        return "No report generated yet. Run report_generate_html first."

    candidates = []
    pdf = Path(html_path).with_suffix(".pdf")
    if pdf.exists():
        candidates.append(str(pdf))
    candidates.append(html_path)

    from tools.drive_tools import drive_upload_file
    return drive_upload_file(candidates[0], folder_id=folder_id)
