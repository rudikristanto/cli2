"""CLI entry point for TaskFlow application."""

from __future__ import annotations

import asyncio
import sys

# Enable UTF-8 mode on Windows
if sys.platform == "win32":
    import os
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

import click
from rich.console import Console

from taskflow import __app_name__, __version__
from taskflow.app import TaskFlowApp


def print_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Print version and exit."""
    if not value or ctx.resilient_parsing:
        return
    console = Console()
    console.print(f"[bold cyan]{__app_name__}[/bold cyan] version [bold yellow]{__version__}[/bold yellow]")
    ctx.exit()


@click.command()
@click.option(
    "--outer", "-o",
    type=click.IntRange(1, 1000),
    default=100,
    help="Number of outer loop iterations (1-1000). Default: 100",
    show_default=True,
)
@click.option(
    "--middle", "-m",
    type=click.IntRange(1, 10),
    default=5,
    help="Number of middle loop iterations (1-10). Default: 5",
    show_default=True,
)
@click.option(
    "--inner", "-i",
    type=click.IntRange(1, 20),
    default=10,
    help="Maximum inner loop iterations (1-20). Default: 10",
    show_default=True,
)
@click.option(
    "--sleep", "-s",
    type=click.FloatRange(0.01, 1.0),
    default=0.05,
    help="Base sleep time in seconds (0.01-1.0). Default: 0.05",
    show_default=True,
)
@click.option(
    "--version", "-v",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
    help="Show version and exit.",
)
def main(
    outer: int,
    middle: int,
    inner: int,
    sleep: float,
) -> None:
    """
    TaskFlow - A beautiful full-screen CLI task runner.

    Executes nested async loops with dual progress tracking, splash screen,
    and detailed summary statistics.

    \b
    Examples:
        taskflow                     # Run with defaults
        taskflow -o 50 -m 3 -i 15    # Custom iteration counts
        taskflow --outer 200         # More outer iterations
        taskflow -s 0.1              # Slower execution for visibility
    """
    console = Console()

    # Warn about terminal size but don't exit
    if console.size.width < 80 or console.size.height < 24:
        console.print(
            "[bold yellow]Warning:[/bold yellow] Terminal size may be too small. "
            f"Current: {console.size.width}x{console.size.height}, "
            "Recommended: at least 80x24",
            style="yellow",
        )
        console.print("Continuing anyway...\n")

    # Display startup info
    console.print(f"\n[bold cyan]{__app_name__}[/bold cyan] v{__version__}")
    console.print(f"Configuration: outer={outer}, middle={middle}, inner={inner}, sleep={sleep}s")
    console.print("Starting in 1 second...\n")

    import time
    time.sleep(1)

    # Create and run the application
    app = TaskFlowApp(
        outer_iterations=outer,
        middle_iterations=middle,
        max_inner_iterations=inner,
        sleep_base=sleep,
    )

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)

    console.print("[bold green]TaskFlow completed successfully![/bold green]\n")


if __name__ == "__main__":
    main()
