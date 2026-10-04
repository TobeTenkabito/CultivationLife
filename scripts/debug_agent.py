"""Launch the local debug CLI/MCP bridge from any working directory."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cultivation_life.debug.agent import main


if __name__ == '__main__':
    raise SystemExit(main())
