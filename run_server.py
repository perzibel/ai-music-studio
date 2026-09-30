"""Entry point for MCP clients: works regardless of the client's working directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from studio.server import main  # noqa: E402

main()
