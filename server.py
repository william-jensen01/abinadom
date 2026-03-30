"""
MCP Server — LDS Scripture Citation Index

Exposes the ChromaDB vector collections to Claude Desktop via stdio transport.
Phase 9 builds startup validation only; tools are added in Phase 10.

Startup sequence:
  1. Resolve ChromaDB path to absolute (CORE-01)
  2. Validate path exists and all 4 collections are present and non-empty (CORE-01/CORE-03)
  3. Ollama health check via live embedding call (CORE-02)
  4. Load all 4 collections into AppContext (CORE-03)
  5. Yield AppContext to tool calls via FastMCP lifespan

All logging goes to stderr only (INTG-01). Stdout is reserved for MCP JSON-RPC.
"""
import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import chromadb
from mcp.server.fastmcp import FastMCP

from config.pipeline_config import CHROMADB_COLLECTION_NAMES
from extractors.phase6_chromadb_loader import get_embedding_function

# ---------------------------------------------------------------------------
# Logging — must be configured before anything else writes to stderr (INTG-01)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context dataclass — carries live resources for tool calls
# ---------------------------------------------------------------------------


@dataclass
class AppContext:
    client: chromadb.ClientAPI
    collections: dict  # str -> chromadb.Collection


# ---------------------------------------------------------------------------
# Startup helpers — each raises SystemExit(1) on failure
# ---------------------------------------------------------------------------


def _resolve_chromadb_path() -> str:
    """
    Return the absolute path to the ChromaDB directory.

    Default: <project_root>/data/chromadb (resolved from __file__, so it works
    regardless of the working directory Claude Desktop uses when spawning the
    server process).

    Override: Set CHROMADB_PATH env var to any path.
    """
    default = Path(__file__).parent.resolve() / "data" / "chromadb"
    raw = os.environ.get("CHROMADB_PATH", str(default))
    return str(Path(raw).resolve())


def _check_ollama() -> None:
    """
    Verify Ollama is running and nomic-embed-text is available.

    Uses a live embedding call (D-04) — an HTTP ping would only confirm the
    daemon is up, not that the model is loaded. Fails fast with an actionable
    error message on any exception.
    """
    try:
        ef = get_embedding_function()
        ef(["health check"])
        logger.info("Ollama health check passed (nomic-embed-text ready)")
    except Exception as e:
        err = str(e)
        if "nomic-embed-text" in err or "model" in err.lower():
            print(
                "ERROR: Ollama model not available. Run: ollama pull nomic-embed-text",
                file=sys.stderr,
            )
        else:
            print(
                "ERROR: Ollama unreachable at http://localhost:11434. Start Ollama and retry.",
                file=sys.stderr,
            )
        sys.exit(1)


def _load_collections(client: chromadb.ClientAPI) -> dict:
    """
    Load all 4 ChromaDB collections using get_collection() (not get_or_create_collection).

    Fails fast with SystemExit(1) if any collection is missing or empty.
    Returns a dict mapping logical key -> chromadb.Collection.
    """
    collections = {}
    for key, name in CHROMADB_COLLECTION_NAMES.items():
        try:
            col = client.get_collection(name=name)
        except Exception:
            print(
                f"ERROR: ChromaDB collection '{name}' not found. "
                "Run the pipeline (scripts/run_pipeline.py) first.",
                file=sys.stderr,
            )
            sys.exit(1)
        count = col.count()
        if count == 0:
            print(
                f"ERROR: Collection '{name}' exists but has 0 records. "
                "Re-run the pipeline to populate it.",
                file=sys.stderr,
            )
            sys.exit(1)
        logger.info("Loaded collection '%s' (%d records)", name, count)
        collections[key] = col
    return collections


def _startup() -> AppContext:
    """
    Run all startup validation checks and return an initialized AppContext.

    Called from lifespan before the first tool call is accepted.
    Any failure raises SystemExit(1) with a message to stderr.
    """
    path = _resolve_chromadb_path()
    logger.info("ChromaDB path: %s", path)

    if not Path(path).exists():
        print(
            f"ERROR: ChromaDB directory not found at {path}. "
            "Run the pipeline (scripts/run_pipeline.py) first.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = chromadb.PersistentClient(path=path)
    _check_ollama()
    collections = _load_collections(client)
    return AppContext(client=client, collections=collections)


# ---------------------------------------------------------------------------
# FastMCP server — lifespan runs startup validation (CORE-03 integration)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server: FastMCP):
    try:
        ctx = _startup()
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: Unexpected startup failure: {e}", file=sys.stderr)
        sys.exit(1)
    try:
        yield ctx
    finally:
        pass  # ChromaDB PersistentClient needs no explicit close


mcp = FastMCP("lds-scripture-index", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Entry point — stdio transport, no stdout output before MCP loop (INTG-01)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
