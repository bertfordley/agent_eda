"""
main.py — CLI entry-point (`poetry run eda`)

Usage:
    poetry run eda                        # interactive REPL
    poetry run eda "List my BQ datasets"  # single query

Telemetry:
    A session_id is generated once per process (REPL) or per invocation
    (single-shot). Every turn is wrapped in turn_span so lifecycle events
    and tracebacks are captured even when the agent fails on conversational
    (non-data) turns.
"""

from __future__ import annotations

import uuid

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from agents.orchestrator import chat as agent_chat, get_agent
from telemetry.core import turn_span
from tools.bigquery_tools import current_session_id, current_thread_id

console = Console()

BANNER = """\
[bold blue]EDA Agent[/bold blue]  [dim]powered by Deep Agents + LangGraph[/dim]

Try:
  • "List my BigQuery datasets"
  • "Here's my data: https://docs.google.com/spreadsheets/d/..."
  • "Describe the sales table and show me revenue by region as a bar chart"
  • "Build an HTML report with those findings and upload it to Drive"
  • "What's a good approach to cohort analysis?"

Type [bold]exit[/bold] to quit.\
"""


@click.command()
@click.argument("query", nargs=-1)
def cli(query: tuple[str, ...]):
    """Conversational EDA agent over BigQuery and Google Workspace."""

    # Single-shot mode: `poetry run eda "some question"`
    if query:
        session_id = uuid.uuid4().hex
        sid_token = current_session_id.set(session_id)
        tid_token = current_thread_id.set(session_id)
        try:
            get_agent()
            message = " ".join(query)
            with console.status("[yellow]Thinking…[/yellow]", spinner="dots"):
                try:
                    # turn_span emits turn_started / turn_completed / turn_failed.
                    # Re-raises on exception so the except below can print it.
                    with turn_span(message, channel="cli"):
                        reply = agent_chat(message)
                except Exception as exc:
                    console.print(f"[red]Error:[/red] {exc}")
                    return
            console.print(Markdown(reply))
        finally:
            current_session_id.reset(sid_token)
            current_thread_id.reset(tid_token)
        return

    # REPL mode — one session_id for the whole process lifetime.
    session_id = uuid.uuid4().hex
    sid_token = current_session_id.set(session_id)
    tid_token = current_thread_id.set(session_id)

    console.print(Panel(BANNER, expand=False))
    get_agent()  # warm up eagerly

    try:
        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye.[/dim]")
                break

            if user_input.strip().lower() in {"exit", "quit", "q", ""}:
                if user_input.strip():
                    console.print("[dim]Goodbye.[/dim]")
                    break
                continue

            with console.status("[yellow]Thinking…[/yellow]", spinner="dots"):
                try:
                    with turn_span(user_input, channel="cli"):
                        reply = agent_chat(user_input)
                except Exception as exc:
                    console.print(f"[red]Error:[/red] {exc}")
                    continue

            console.print(
                Panel(Markdown(reply), title="[bold green]Agent[/bold green]", expand=False)
            )
    finally:
        current_session_id.reset(sid_token)
        current_thread_id.reset(tid_token)


if __name__ == "__main__":
    cli()
