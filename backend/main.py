"""
main.py — CLI entry-point (`poetry run eda`)

Usage:
    poetry run eda                        # interactive REPL
    poetry run eda "List my BQ datasets"  # single query
"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from agents.orchestrator import chat as agent_chat, get_agent

console = Console()

BANNER = """\
[bold blue]EDA Agent[/bold blue]  [dim]powered by Deep Agents + LangGraph[/dim]

Try:
  • "List my BigQuery datasets"
  • "Here's my data: https://docs.google.com/spreadsheets/d/..."
  • "Describe the sales table and show me revenue by region as a bar chart"
  • "Build an HTML report with those findings and upload it to Drive"

Type [bold]exit[/bold] to quit.\
"""


@click.command()
@click.argument("query", nargs=-1)
def cli(query: tuple[str, ...]):
    """Conversational EDA agent over BigQuery and Google Workspace."""
    if query:
        # Single-shot mode: `poetry run eda "some question"`
        get_agent()
        with console.status("[yellow]Thinking…[/yellow]", spinner="dots"):
            reply = agent_chat(" ".join(query))
        console.print(Markdown(reply))
        return

    # REPL mode
    console.print(Panel(BANNER, expand=False))
    get_agent()  # warm up eagerly

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
                reply = agent_chat(user_input)
            except Exception as exc:
                console.print(f"[red]Error:[/red] {exc}")
                continue

        console.print(Panel(Markdown(reply), title="[bold green]Agent[/bold green]", expand=False))


if __name__ == "__main__":
    cli()
