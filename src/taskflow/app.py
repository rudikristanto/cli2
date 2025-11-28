"""Core application - wires together business logic and display components."""

from __future__ import annotations

import asyncio

from taskflow.display import TaskFlowDisplay
from taskflow.executor import TaskExecutor


class TaskFlowApp:
    """Main application class for TaskFlow - coordinates executor and display."""

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

        # Create display component
        self.display = TaskFlowDisplay(
            outer_iterations=outer_iterations,
            middle_iterations=middle_iterations,
            max_inner_iterations=max_inner_iterations,
        )

        # Create executor with display as callbacks
        self.executor = TaskExecutor(
            outer_iterations=outer_iterations,
            middle_iterations=middle_iterations,
            max_inner_iterations=max_inner_iterations,
            sleep_base=sleep_base,
            callbacks=self.display,
        )

    async def run(self) -> None:
        """Run the main application."""
        # Show splash screen
        self.display.display_splash_screen()

        # Start live display
        live = self.display.start_live_display()

        try:
            with live:
                self.display.update_display()

                # Run the main task loops
                stats = await self.executor.execute()

                # Show completion status
                self.display.update_display(status="Completed")
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            self.display.on_log_message("Operation cancelled by user", "WARNING")
            self.display.update_display(status="Cancelled")
            await asyncio.sleep(0.5)
            stats = self.executor.stats
            stats.finalize()

        finally:
            self.display.stop_live_display()

        # Display final summary
        self.display.clear()
        self.display.display_summary(stats)
        self.display.display_recent_messages()
