"""Core application logic with async task execution and progress tracking."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
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
    from collections.abc import Callable


@dataclass
class TaskStats:
    """Statistics for task execution."""

    outer_iterations: int = 0
    middle_iterations: int = 0
    inner_iterations: int = 0
    early_terminations: int = 0
    total_time: float = 0.0
    messages: list[tuple[float, str]] = field(default_factory=list)

    def add_message(self, msg: str) -> None:
        """Add a timestamped message."""
        self.messages.append((time.time(), msg))


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


class TaskFlowApp:
    """Main application class for TaskFlow."""

    def __init__(
        self,
        outer_iterations: int = 100,
        middle_iterations: int = 10,
        max_inner_iterations: int = 20,
        sleep_base: float = 0.05,
    ) -> None:
        self.outer_iterations = outer_iterations
        self.middle_iterations = middle_iterations
        self.max_inner_iterations = max_inner_iterations
        self.sleep_base = sleep_base

        self.console = Console()
        self.stats = TaskStats()
        self.message_log = MessageLog()

        # Calculate total inner iterations per outer (middle * inner)
        inner_total = middle_iterations * max_inner_iterations
        self.progress_display = DualProgressDisplay(outer_iterations, inner_total)

        self.layout: Layout | None = None
        self.live: Live | None = None

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
        footer_text.append(f"Outer: {self.stats.outer_iterations}/{self.outer_iterations}", style="cyan")
        footer_text.append(" | ", style="dim")
        footer_text.append(f"Early Exits: {self.stats.early_terminations}", style="yellow")
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

    async def inner_loop(self, outer_idx: int, middle_idx: int) -> int:
        """
        Execute the innermost loop with potential early termination.

        Returns the number of iterations completed.
        """
        iterations_completed = 0

        for inner_idx in range(self.max_inner_iterations):
            self.stats.inner_iterations += 1
            iterations_completed += 1

            # Simulate work
            await asyncio.sleep(self.sleep_base * random.uniform(0.5, 1.5))

            # Occasional progress message
            if inner_idx % 5 == 0 and inner_idx > 0:
                self.message_log.add(
                    f"Inner loop [{outer_idx+1}.{middle_idx+1}.{inner_idx+1}]: "
                    f"Processing batch {inner_idx // 5 + 1}...",
                    "PROGRESS",
                )

            # Update inner progress bar
            self.progress_display.update_inner(1)
            self.update_display()

            # Random early termination (approximately 15% chance per iteration)
            if random.random() < 0.03:
                self.stats.early_terminations += 1
                remaining = self.max_inner_iterations - inner_idx - 1
                # Advance progress by remaining amount to show completion
                self.progress_display.update_inner(remaining)
                self.message_log.add(
                    f"Early exit at [{outer_idx+1}.{middle_idx+1}.{inner_idx+1}] - "
                    f"Condition met, skipping {remaining} remaining iterations",
                    "WARNING",
                )
                self.update_display()
                break

        return iterations_completed

    async def middle_loop(self, outer_idx: int) -> None:
        """Execute the middle loop."""
        self.message_log.add(
            f"Starting middle loop batch for outer iteration {outer_idx + 1}",
            "START",
        )

        for middle_idx in range(self.middle_iterations):
            self.stats.middle_iterations += 1

            # Simulate some work before inner loop
            await asyncio.sleep(self.sleep_base * 0.5)

            if middle_idx % 3 == 0:
                self.message_log.add(
                    f"Middle loop [{outer_idx+1}.{middle_idx+1}]: "
                    f"Initializing sub-task group {middle_idx + 1}/{self.middle_iterations}",
                    "PROGRESS",
                )
                self.update_display()

            # Execute inner loop
            await self.inner_loop(outer_idx, middle_idx)

        self.message_log.add(
            f"Completed all middle iterations for outer {outer_idx + 1}",
            "COMPLETE",
        )
        self.update_display()

    async def outer_loop(self) -> None:
        """Execute the outermost loop."""
        self.message_log.add(
            f"Beginning main task execution with {self.outer_iterations} iterations",
            "START",
        )
        self.message_log.add(
            f"Configuration: {self.middle_iterations} middle loops, "
            f"up to {self.max_inner_iterations} inner iterations each",
            "INFO",
        )
        self.update_display()

        for outer_idx in range(self.outer_iterations):
            self.stats.outer_iterations += 1

            # Reset inner progress for this outer iteration
            inner_total = self.middle_iterations * self.max_inner_iterations
            self.progress_display.reset_inner(inner_total)

            self.message_log.add(
                f"Outer iteration {outer_idx + 1}/{self.outer_iterations} started - "
                f"Processing {self.middle_iterations} sub-tasks with {self.max_inner_iterations} steps each",
                "START",
            )
            self.update_display()

            # Execute middle loop
            await self.middle_loop(outer_idx)

            # Update outer progress
            self.progress_display.update_outer(1)

            # Milestone messages for outer loop
            if (outer_idx + 1) % max(1, self.outer_iterations // 10) == 0:
                progress_pct = ((outer_idx + 1) / self.outer_iterations) * 100
                self.message_log.add(
                    f"Milestone reached: {progress_pct:.0f}% of outer iterations complete "
                    f"({outer_idx + 1}/{self.outer_iterations})",
                    "COMPLETE",
                )
                self.update_display()

        self.message_log.add("All outer iterations completed successfully!", "COMPLETE")
        self.update_display()

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

    def display_summary(self) -> None:
        """Display the final summary."""
        self.stats.total_time = time.time() - self.message_log.start_time

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
        hours, remainder = divmod(int(self.stats.total_time), 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        summary_table.add_row("Total Execution Time", time_str)
        summary_table.add_row("Outer Iterations Completed", str(self.stats.outer_iterations))
        summary_table.add_row("Middle Iterations Completed", str(self.stats.middle_iterations))
        summary_table.add_row("Inner Iterations Completed", str(self.stats.inner_iterations))
        summary_table.add_row("Early Terminations", str(self.stats.early_terminations))

        # Calculate efficiency
        max_inner = self.outer_iterations * self.middle_iterations * self.max_inner_iterations
        efficiency = (self.stats.inner_iterations / max_inner) * 100 if max_inner > 0 else 0
        summary_table.add_row("Iteration Efficiency", f"{efficiency:.1f}%")

        # Average iterations per second
        if self.stats.total_time > 0:
            iter_per_sec = self.stats.inner_iterations / self.stats.total_time
            summary_table.add_row("Avg Iterations/Second", f"{iter_per_sec:.2f}")

        self.console.print()
        self.console.print(Panel(summary_table, border_style="magenta", padding=(1, 2)))
        self.console.print()

    async def run(self) -> None:
        """Run the main application."""
        # Show splash screen
        self.display_splash_screen()

        # Clear and prepare full-screen layout
        self.console.clear()
        self.layout = self.create_layout()

        # Initialize progress display
        self.progress_display.start()

        try:
            with Live(
                self.layout,
                console=self.console,
                refresh_per_second=10,
                screen=True,
            ) as live:
                self.live = live
                self.update_display()

                # Run the main task loops
                await self.outer_loop()

                # Show completion status
                self.update_display(status="Completed")
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            self.message_log.add("Operation cancelled by user", "WARNING")
            self.update_display(status="Cancelled")
            await asyncio.sleep(0.5)

        finally:
            self.live = None

        # Display final summary
        self.console.clear()
        self.display_summary()

        # Show recent messages
        self.console.print(
            Panel(
                "[bold cyan]Recent Log Messages[/bold cyan]",
                border_style="cyan",
            )
        )

        recent = self.stats.messages[-10:] if len(self.stats.messages) > 10 else self.message_log.messages[-10:]
        for timestamp, level, msg in self.message_log.messages[-10:]:
            elapsed = timestamp - self.message_log.start_time
            time_str = MessageLog._format_elapsed(elapsed)
            self.console.print(f"  [dim]{time_str}[/dim] [{level}] {msg}")

        self.console.print()
