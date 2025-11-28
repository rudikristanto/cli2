"""UI/Display components for TaskFlow - handles all screen and progress rendering."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from taskflow import __app_name__, __version__

if TYPE_CHECKING:
    from taskflow.executor import TaskStats


class MessageLog:
    """A scrollable message log that wraps text and fills vertical space."""

    def __init__(self, max_messages: int = 100) -> None:
        self.messages: list[tuple[float, str, str]] = []  # (timestamp, level, message)
        self.max_messages = max_messages
        self.start_time = time.time()

    def add(self, message: str, level: str = "INFO") -> None:
        """Add a message to the log."""
        self.messages.append((time.time(), level, message))
        if len(self.messages) > self.max_messages:
            self.messages.pop(0)

    def render(self, height: int = 20) -> Panel:
        """Render the message log as a Rich Panel with word wrapping."""
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column("Time", style="dim cyan", width=10, no_wrap=True)
        table.add_column("Level", width=7, no_wrap=True)
        table.add_column("Message", overflow="fold")  # fold enables word wrapping

        level_styles = {
            "INFO": "white",
            "START": "bold green",
            "PROGRESS": "yellow",
            "COMPLETE": "bold blue",
            "WARNING": "bold yellow",
            "SUMMARY": "bold magenta",
        }

        # Show most recent messages that fit in the available height
        visible_messages = self.messages[-(height - 2) :] if height > 2 else self.messages[-5:]

        for timestamp, level, message in visible_messages:
            elapsed = timestamp - self.start_time
            time_str = self._format_elapsed(elapsed)
            style = level_styles.get(level, "white")
            table.add_row(time_str, Text(level, style=style), Text(message, overflow="fold"))

        # Fill remaining space with empty rows if needed
        remaining = max(0, (height - 2) - len(visible_messages))
        for _ in range(remaining):
            table.add_row("", "", "")

        return Panel(
            table,
            title="[bold cyan]Task Log[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        """Format elapsed time as HH:MM:SS."""
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class DualProgressDisplay:
    """Manages dual progress bars with independent time tracking."""

    def __init__(self, outer_total: int, inner_total_per_outer: int) -> None:
        self.outer_total = outer_total
        self.inner_total_per_outer = inner_total_per_outer

        # Outer progress bar (tracks first loop)
        self.outer_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40, complete_style="blue", finished_style="green"),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TextColumn("[cyan]Elapsed:[/cyan]"),
            TimeElapsedColumn(),
            expand=True,
        )

        # Inner progress bar (tracks combined second and third loops)
        self.inner_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold yellow]{task.description}"),
            BarColumn(bar_width=40, complete_style="yellow", finished_style="green"),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TextColumn("[cyan]Elapsed:[/cyan]"),
            TimeElapsedColumn(),
            expand=True,
        )

        self.outer_task_id: int | None = None
        self.inner_task_id: int | None = None

    def start(self) -> None:
        """Initialize progress tasks."""
        self.outer_task_id = self.outer_progress.add_task(
            "Outer Loop Progress", total=self.outer_total
        )
        self.inner_task_id = self.inner_progress.add_task(
            "Inner Loop Progress", total=self.inner_total_per_outer
        )

    def update_outer(self, advance: int = 1) -> None:
        """Update outer progress bar."""
        if self.outer_task_id is not None:
            self.outer_progress.update(self.outer_task_id, advance=advance)

    def update_inner(self, advance: int = 1) -> None:
        """Update inner progress bar."""
        if self.inner_task_id is not None:
            self.inner_progress.update(self.inner_task_id, advance=advance)

    def reset_inner(self, new_total: int | None = None) -> None:
        """Reset inner progress bar for new outer iteration."""
        if self.inner_task_id is not None:
            total = new_total if new_total is not None else self.inner_total_per_outer
            self.inner_progress.reset(self.inner_task_id, total=total)
            self.inner_progress.update(self.inner_task_id, completed=0)

    def set_inner_total(self, total: int) -> None:
        """Set the total for inner progress."""
        if self.inner_task_id is not None:
            self.inner_progress.update(self.inner_task_id, total=total)

    def render(self) -> Panel:
        """Render both progress bars in a panel."""
        return Panel(
            Group(self.outer_progress, self.inner_progress),
            title="[bold green]Progress[/bold green]",
            border_style="green",
            padding=(1, 2),
        )


class TaskFlowDisplay:
    """Handles all display/rendering for the TaskFlow application."""

    def __init__(
        self,
        outer_iterations: int,
        middle_iterations: int,
        max_inner_iterations: int,
    ) -> None:
        self.outer_iterations = outer_iterations
        self.middle_iterations = middle_iterations
        self.max_inner_iterations = max_inner_iterations

        self.console = Console()
        self.message_log = MessageLog()

        # Calculate total inner iterations per outer (middle * inner)
        inner_total = middle_iterations * max_inner_iterations
        self.progress_display = DualProgressDisplay(outer_iterations, inner_total)

        self.layout: Layout | None = None
        self.live: Live | None = None

        # Track stats for footer display
        self._current_outer: int = 0
        self._early_terminations: int = 0

    def create_layout(self) -> Layout:
        """Create the full-screen layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="progress", size=7),
            Layout(name="messages"),
            Layout(name="footer", size=3),
        )
        return layout

    def render_header(self) -> Panel:
        """Render the header panel."""
        title = Text()
        title.append(f" {__app_name__} ", style="bold white on blue")
        title.append(f" v{__version__} ", style="bold cyan")
        title.append(" | ", style="dim")
        title.append("Full-Screen Task Runner", style="italic")

        return Panel(title, style="bold", border_style="blue")

    def render_footer(self, status: str = "Running") -> Panel:
        """Render the footer panel with current status."""
        footer_text = Text()
        footer_text.append("Status: ", style="bold")
        footer_text.append(status, style="bold green" if status == "Running" else "bold yellow")
        footer_text.append(" | ", style="dim")
        footer_text.append(f"Outer: {self._current_outer}/{self.outer_iterations}", style="cyan")
        footer_text.append(" | ", style="dim")
        footer_text.append(f"Early Exits: {self._early_terminations}", style="yellow")
        footer_text.append(" | ", style="dim")
        footer_text.append("Press Ctrl+C to cancel", style="dim italic")

        return Panel(footer_text, border_style="blue")

    def update_display(self, status: str = "Running") -> None:
        """Update the live display."""
        if self.layout is None:
            return

        self.layout["header"].update(self.render_header())
        self.layout["progress"].update(self.progress_display.render())

        # Get terminal height and calculate message area height
        terminal_height = self.console.size.height
        message_height = max(10, terminal_height - 13)  # Subtract header, progress, footer
        self.layout["messages"].update(self.message_log.render(height=message_height))
        self.layout["footer"].update(self.render_footer(status))

    def display_splash_screen(self) -> None:
        """Display the splash screen."""
        self.console.clear()

        splash = Table.grid(padding=1, expand=True)
        splash.add_column(justify="center")

        # ASCII art logo (using simple ASCII for Windows compatibility)
        logo = r"""
  _____         _    _____ _
 |_   _|_ _ ___| | _|  ___| | _____      __
   | |/ _` / __| |/ / |_  | |/ _ \ \ /\ / /
   | | (_| \__ \   <|  _| | | (_) \ V  V /
   |_|\__,_|___/_|\_\_|   |_|\___/ \_/\_/
        """

        splash.add_row(Text(logo, style="bold cyan"))
        splash.add_row("")
        splash.add_row(Text(f"Version {__version__}", style="bold yellow"))
        splash.add_row(Text("A Beautiful Full-Screen CLI Task Runner", style="italic"))
        splash.add_row("")
        splash.add_row(Text("Initializing...", style="dim"))

        panel = Panel(
            splash,
            border_style="cyan",
            padding=(2, 4),
        )

        self.console.print(panel, justify="center")
        time.sleep(2)

    def display_summary(self, stats: TaskStats) -> None:
        """Display the final summary."""
        summary_table = Table(
            title="Execution Summary",
            show_header=True,
            header_style="bold magenta",
            border_style="magenta",
            expand=True,
        )
        summary_table.add_column("Metric", style="cyan", width=30)
        summary_table.add_column("Value", style="green", justify="right")

        # Format total time
        hours, remainder = divmod(int(stats.total_time), 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        summary_table.add_row("Total Execution Time", time_str)
        summary_table.add_row("Outer Iterations Completed", str(stats.outer_iterations))
        summary_table.add_row("Middle Iterations Completed", str(stats.middle_iterations))
        summary_table.add_row("Inner Iterations Completed", str(stats.inner_iterations))
        summary_table.add_row("Early Terminations", str(stats.early_terminations))

        # Calculate efficiency
        max_inner = (
            self.outer_iterations * self.middle_iterations * self.max_inner_iterations
        )
        efficiency = (stats.inner_iterations / max_inner) * 100 if max_inner > 0 else 0
        summary_table.add_row("Iteration Efficiency", f"{efficiency:.1f}%")

        # Average iterations per second
        if stats.total_time > 0:
            iter_per_sec = stats.inner_iterations / stats.total_time
            summary_table.add_row("Avg Iterations/Second", f"{iter_per_sec:.2f}")

        self.console.print()
        self.console.print(Panel(summary_table, border_style="magenta", padding=(1, 2)))
        self.console.print()

    def display_recent_messages(self) -> None:
        """Display the recent log messages."""
        self.console.print(
            Panel(
                "[bold cyan]Recent Log Messages[/bold cyan]",
                border_style="cyan",
            )
        )

        for timestamp, level, msg in self.message_log.messages[-10:]:
            elapsed = timestamp - self.message_log.start_time
            time_str = MessageLog._format_elapsed(elapsed)
            self.console.print(f"  [dim]{time_str}[/dim] [{level}] {msg}")

        self.console.print()

    # === Callback methods for executor events ===

    def on_log_message(self, message: str, level: str = "INFO") -> None:
        """Handle log message event from executor."""
        self.message_log.add(message, level)
        self.update_display()

    def on_outer_progress(self, current: int, total: int) -> None:
        """Handle outer progress update."""
        self._current_outer = current
        self.progress_display.update_outer(1)
        self.update_display()

    def on_inner_progress(self, advance: int = 1) -> None:
        """Handle inner progress update."""
        self.progress_display.update_inner(advance)
        self.update_display()

    def on_reset_inner(self, new_total: int) -> None:
        """Handle inner progress reset for new outer iteration."""
        self.progress_display.reset_inner(new_total)
        self.update_display()

    def on_early_termination(self, remaining: int) -> None:
        """Handle early termination event."""
        self._early_terminations += 1
        self.progress_display.update_inner(remaining)
        self.update_display()

    def start_live_display(self) -> Live:
        """Start the live display context."""
        self.console.clear()
        self.layout = self.create_layout()
        self.progress_display.start()
        self.live = Live(
            self.layout,
            console=self.console,
            refresh_per_second=10,
            screen=True,
        )
        return self.live

    def stop_live_display(self) -> None:
        """Stop the live display."""
        self.live = None

    def clear(self) -> None:
        """Clear the console."""
        self.console.clear()
