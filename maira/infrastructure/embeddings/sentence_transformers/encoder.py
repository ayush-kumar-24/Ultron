"""Loads and runs a local Sentence Transformers model for vector encoding."""

from __future__ import annotations

from loguru import logger

from maira.core.interfaces.embeddings import EmbeddingEncoder


class SentenceTransformerEncoder(EmbeddingEncoder):
  def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
    self._model_name = model_name
    self._model = None
    self._failed = False

  @property
  def model_name(self) -> str:
    return self._model_name

  def is_available(self) -> bool:
    if self._failed:
      return False
    try:
      self._ensure_model()
      return self._model is not None
    except Exception as exc:  # noqa: BLE001
      logger.warning("Embedding encoder unavailable: {}", exc)
      self._failed = True
      return False

  def encode(self, text: str) -> list[float]:
    vectors = self.encode_batch([text])
    return vectors[0]

  def encode_batch(self, texts: list[str]) -> list[list[float]]:
    model = self._ensure_model()
    vectors = model.encode(texts, normalize_embeddings=True)
    return [list(map(float, row)) for row in vectors]

  def _ensure_model(self):
    if self._model is not None:
      return self._model
    from sentence_transformers import SentenceTransformer

    logger.info("Loading embedding model: {}", self._model_name)
    self._model = SentenceTransformer(self._model_name)
    return self._model
