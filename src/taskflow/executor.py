"""Business logic for TaskFlow - handles task execution without UI concerns."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    pass


@dataclass
class TaskStats:
    """Statistics for task execution."""

    outer_iterations: int = 0
    middle_iterations: int = 0
    inner_iterations: int = 0
    early_terminations: int = 0
    total_time: float = 0.0
    start_time: float = field(default_factory=time.time)
    messages: list[tuple[float, str]] = field(default_factory=list)

    def add_message(self, msg: str) -> None:
        """Add a timestamped message."""
        self.messages.append((time.time(), msg))

    def finalize(self) -> None:
        """Finalize stats by calculating total time."""
        self.total_time = time.time() - self.start_time


class ExecutorCallbacks(Protocol):
    """Protocol defining callbacks for executor events."""

    def on_log_message(self, message: str, level: str = "INFO") -> None:
        """Called when a log message is generated."""
        ...

    def on_outer_progress(self, current: int, total: int) -> None:
        """Called when outer loop makes progress."""
        ...

    def on_inner_progress(self, advance: int = 1) -> None:
        """Called when inner loop makes progress."""
        ...

    def on_reset_inner(self, new_total: int) -> None:
        """Called when inner progress needs to be reset."""
        ...

    def on_early_termination(self, remaining: int) -> None:
        """Called when an early termination occurs."""
        ...


class NullCallbacks:
    """No-op callbacks for headless execution."""

    def on_log_message(self, message: str, level: str = "INFO") -> None:
        pass

    def on_outer_progress(self, current: int, total: int) -> None:
        pass

    def on_inner_progress(self, advance: int = 1) -> None:
        pass

    def on_reset_inner(self, new_total: int) -> None:
        pass

    def on_early_termination(self, remaining: int) -> None:
        pass


class TaskExecutor:
    """Executes the nested task loops - pure business logic without UI."""

    def __init__(
        self,
        outer_iterations: int = 100,
        middle_iterations: int = 10,
        max_inner_iterations: int = 20,
        sleep_base: float = 0.05,
        callbacks: ExecutorCallbacks | None = None,
    ) -> None:
        self.outer_iterations = outer_iterations
        self.middle_iterations = middle_iterations
        self.max_inner_iterations = max_inner_iterations
        self.sleep_base = sleep_base

        self.stats = TaskStats()
        self.callbacks = callbacks or NullCallbacks()

    def _log(self, message: str, level: str = "INFO") -> None:
        """Log a message through callbacks."""
        self.stats.add_message(message)
        self.callbacks.on_log_message(message, level)

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
                self._log(
                    f"Inner loop [{outer_idx+1}.{middle_idx+1}.{inner_idx+1}]: "
                    f"Processing batch {inner_idx // 5 + 1}...",
                    "PROGRESS",
                )

            # Update inner progress bar
            self.callbacks.on_inner_progress(1)

            # Random early termination (approximately 15% chance per iteration)
            if random.random() < 0.03:
                self.stats.early_terminations += 1
                remaining = self.max_inner_iterations - inner_idx - 1
                # Notify about early termination
                self.callbacks.on_early_termination(remaining)
                self._log(
                    f"Early exit at [{outer_idx+1}.{middle_idx+1}.{inner_idx+1}] - "
                    f"Condition met, skipping {remaining} remaining iterations",
                    "WARNING",
                )
                break

        return iterations_completed

    async def middle_loop(self, outer_idx: int) -> None:
        """Execute the middle loop."""
        self._log(
            f"Starting middle loop batch for outer iteration {outer_idx + 1}",
            "START",
        )

        for middle_idx in range(self.middle_iterations):
            self.stats.middle_iterations += 1

            # Simulate some work before inner loop
            await asyncio.sleep(self.sleep_base * 0.5)

            if middle_idx % 3 == 0:
                self._log(
                    f"Middle loop [{outer_idx+1}.{middle_idx+1}]: "
                    f"Initializing sub-task group {middle_idx + 1}/{self.middle_iterations}",
                    "PROGRESS",
                )

            # Execute inner loop
            await self.inner_loop(outer_idx, middle_idx)

        self._log(
            f"Completed all middle iterations for outer {outer_idx + 1}",
            "COMPLETE",
        )

    async def execute(self) -> TaskStats:
        """Execute the main task loops and return statistics."""
        self.stats = TaskStats()

        self._log(
            f"Beginning main task execution with {self.outer_iterations} iterations",
            "START",
        )
        self._log(
            f"Configuration: {self.middle_iterations} middle loops, "
            f"up to {self.max_inner_iterations} inner iterations each",
            "INFO",
        )

        for outer_idx in range(self.outer_iterations):
            self.stats.outer_iterations += 1

            # Reset inner progress for this outer iteration
            inner_total = self.middle_iterations * self.max_inner_iterations
            self.callbacks.on_reset_inner(inner_total)

            self._log(
                f"Outer iteration {outer_idx + 1}/{self.outer_iterations} started - "
                f"Processing {self.middle_iterations} sub-tasks with "
                f"{self.max_inner_iterations} steps each",
                "START",
            )

            # Execute middle loop
            await self.middle_loop(outer_idx)

            # Update outer progress
            self.callbacks.on_outer_progress(outer_idx + 1, self.outer_iterations)

            # Milestone messages for outer loop
            if (outer_idx + 1) % max(1, self.outer_iterations // 10) == 0:
                progress_pct = ((outer_idx + 1) / self.outer_iterations) * 100
                self._log(
                    f"Milestone reached: {progress_pct:.0f}% of outer iterations complete "
                    f"({outer_idx + 1}/{self.outer_iterations})",
                    "COMPLETE",
                )

        self._log("All outer iterations completed successfully!", "COMPLETE")
        self.stats.finalize()
        return self.stats
