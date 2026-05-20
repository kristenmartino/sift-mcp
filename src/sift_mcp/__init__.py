__version__ = "0.1.0"

# Load .env from the sift-mcp project root regardless of cwd. MCP clients
# (Claude Desktop, Claude Code, MCP Inspector) launch this as a subprocess
# from their own cwd, so `load_dotenv()` with no args misses the file.
from pathlib import Path
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
# override=True: the .env file is the source of truth for this project.
# Without it, an empty/stale value already in the shell env silently shadows
# what's in .env and produces "key not set" errors that are hard to trace.
load_dotenv(_ENV_PATH, override=True)
