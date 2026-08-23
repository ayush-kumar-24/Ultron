"""ChromaDB persistent client — local embedding index on disk."""

from __future__ import annotations

from pathlib import Path

from loguru import logger


def create_chroma_client(path: Path | str):
  """Create a persistent Chroma client, or raise if chromadb is missing."""
  import chromadb

  root = Path(path)
  root.mkdir(parents=True, exist_ok=True)
  logger.info("Opening ChromaDB at {}", root)
  return chromadb.PersistentClient(path=str(root))
