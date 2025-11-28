# TaskFlow

A beautiful full-screen CLI task runner with dual progress tracking, built with Python 3.13 and Rich.

## Features

- **Full-screen mode** with elegant layout
- **Splash screen** displaying app name and version
- **Dual progress bars**:
  - Outer progress: Tracks main loop iterations
  - Inner progress: Tracks combined middle/inner loop progress (resets per outer iteration)
- **Independent time tracking** for each progress bar
- **Real-time message log** with word wrapping
- **Async/await programming model**
- **Summary statistics** at completion
- **Early termination simulation** with random short-circuits

## Requirements

- Python 3.13+
- Poetry (for dependency management)

## Installation

### Option 1: Using Poetry (Recommended)

```bash
# Install Poetry if you haven't already
pip install poetry

# Install dependencies
poetry install

# Run the application
poetry run taskflow
```

### Option 2: Using pip directly

```bash
# Create and activate a virtual environment
python -m venv .venv

# On Windows
.venv\Scripts\activate

# On macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install rich click

# Run directly
python -m taskflow.cli
```

## Usage

### Basic Run

```bash
# With Poetry
poetry run taskflow

# Or if installed globally
taskflow
```

### Command Line Options

```bash
taskflow [OPTIONS]

Options:
  -o, --outer INTEGER RANGE   Number of outer loop iterations (1-1000)  [default: 100]
  -m, --middle INTEGER RANGE  Number of middle loop iterations (1-10)   [default: 5]
  -i, --inner INTEGER RANGE   Maximum inner loop iterations (1-20)      [default: 10]
  -s, --sleep FLOAT RANGE     Base sleep time in seconds (0.01-1.0)     [default: 0.05]
  -v, --version              Show version and exit
  --help                     Show this message and exit
```

### Examples

```bash
# Quick demo with fewer iterations
poetry run taskflow -o 10 -m 3 -i 5

# Full run with 1000 outer iterations
poetry run taskflow -o 1000 -m 10 -i 20

# Slower execution for better visibility
poetry run taskflow -o 50 -s 0.2

# Show version
poetry run taskflow --version
```

## Architecture

```
src/taskflow/
├── __init__.py    # Package metadata (version, name)
├── app.py         # Core application logic
│   ├── TaskStats       # Statistics tracking dataclass
│   ├── MessageLog      # Scrollable message log with wrapping
│   ├── DualProgressDisplay  # Dual progress bar management
│   └── TaskFlowApp     # Main application class
└── cli.py         # CLI entry point with Click
```

## Loop Structure

1. **Outer Loop** (0-1000 iterations)
   - Tracked by first progress bar
   - Each iteration resets the inner progress bar

2. **Middle Loop** (0-10 iterations per outer)
   - Combined with inner loop in second progress bar

3. **Inner Loop** (1-20 iterations per middle)
   - Can terminate early randomly (~3% chance per iteration)
   - Updates second progress bar on each iteration

## Terminal Requirements

Minimum terminal size: 80x24 characters

For best experience, use a terminal that supports:
- 256 colors or true color
- Unicode characters
- Full-screen mode (alternate screen buffer)

## Development

```bash
# Install dev dependencies
poetry install

# Run with verbose output
poetry run python -m taskflow.cli -o 20 -m 5 -i 10

# Format code (if ruff is installed)
poetry run ruff format src/
poetry run ruff check src/ --fix
```

## License

MIT License
