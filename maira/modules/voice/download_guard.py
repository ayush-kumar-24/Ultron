"""Refuse automatic multi-GB model downloads."""

from __future__ import annotations


class ModelDownloadBlocked(RuntimeError):
  """Raised when a provider would exceed the local download policy."""


def assert_download_allowed(
  *,
  estimated_gb: float,
  max_gb: float,
  provider: str,
  allow: bool,
) -> None:
  if allow:
    return
  if estimated_gb <= max_gb:
    return
  raise ModelDownloadBlocked(
    f"This voice model ({provider}) requires approximately {estimated_gb:.1f} GB "
    f"and is disabled by the current local resource policy "
    f"(max_model_download_gb={max_gb:g}). "
    "Enable explicitly only after confirming you want the download."
  )


def unavailable_message(*, estimated_gb: float, max_gb: float, provider: str) -> str:
  return (
    f"This voice model ({provider}) requires approximately {estimated_gb:.1f} GB "
    f"and is disabled by the current local resource policy "
    f"(max {max_gb:g} GB)."
  )
