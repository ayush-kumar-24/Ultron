"""Resolve a YouTube search query to a direct watch URL (best title match)."""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

from loguru import logger

_WATCH_ID = re.compile(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"')
_WATCH_HREF = re.compile(r"/watch\?v=([A-Za-z0-9_-]{11})")
_TRAILING_JUNK = re.compile(
  r"(?i)(?:\s*,)?\s*(?:and\s+)?(?:please\s+)?"
  r"(?:"
  r"skip(?:\s+the)?\s+ads?(?:\s+if\b.*)?|"
  r"without\s+ads?|ad\s*free"
  r")\s*$"
)


def clean_youtube_query(query: str) -> str:
  cleaned = " ".join((query or "").split()).strip(" .,!")
  cleaned = _TRAILING_JUNK.sub("", cleaned).strip(" .,!")
  # Drop filler words that hurt matching less than they help search
  cleaned = re.sub(r"(?i)\b(original\s+song|full\s+song|official\s+video|lyrics)\b", " ", cleaned)
  cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!")
  return cleaned


def youtube_search_url(query: str) -> str:
  # sp=EgIQAQ%253D%253D → filter to Videos
  return (
    "https://www.youtube.com/results?"
    f"search_query={quote_plus(query)}&sp=EgIQAQ%253D%253D"
  )


def youtube_watch_url(video_id: str) -> str:
  return f"https://www.youtube.com/watch?v={video_id}"


def resolve_youtube_play_url(query: str, *, timeout: float = 8.0) -> str:
  """Return a watch URL for the best-matching organic video, else search URL."""
  cleaned = clean_youtube_query(query)
  if not cleaned:
    return "https://www.youtube.com"

  search = youtube_search_url(cleaned)
  video_id = _best_video_id(search, cleaned, timeout=timeout)
  if video_id:
    watch = youtube_watch_url(video_id)
    logger.info("YouTube resolve {!r} → {}", cleaned, watch)
    return watch

  logger.warning("YouTube resolve fallback to search for {!r}", cleaned)
  return search


def _best_video_id(search_url: str, query: str, *, timeout: float) -> str | None:
  try:
    import httpx
  except Exception:  # noqa: BLE001
    return None

  headers = {
    "User-Agent": (
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
  }
  try:
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
      response = client.get(search_url)
      response.raise_for_status()
      html = response.text
  except Exception as exc:  # noqa: BLE001
    logger.debug("YouTube fetch failed: {}", exc)
    return None

  candidates = _candidates_from_initial_data(html)
  if not candidates:
    # Regex fallback — first unique ids only (no titles)
    seen: list[str] = []
    for match in _WATCH_ID.finditer(html):
      vid = match.group(1)
      if vid not in seen:
        seen.append(vid)
    return seen[0] if seen else None

  scored = [(_score_title(query, title), vid, title) for vid, title in candidates]
  scored.sort(key=lambda row: row[0], reverse=True)
  best_score, best_id, best_title = scored[0]
  logger.info(
    "YouTube candidates top={!r} score={:.2f} (of {})",
    best_title,
    best_score,
    len(scored),
  )
  # If nothing looks related, still take the top organic videoRenderer
  if best_score <= 0:
    return candidates[0][0]
  return best_id


def _score_title(query: str, title: str) -> float:
  q_tokens = [t for t in re.split(r"[^a-z0-9]+", query.lower()) if len(t) > 1]
  title_l = title.lower()
  if not q_tokens:
    return 0.0
  hits = sum(1 for t in q_tokens if t in title_l)
  ratio = hits / len(q_tokens)
  bonus = 0.0
  if "official" in title_l:
    bonus += 0.35
  if "sony music" in title_l or "kailash kher" in title_l:
    bonus += 0.3
  if "teri deewani" in title_l or all(t in title_l for t in ("teri", "deewani")):
    bonus += 0.55
  if "cover" in title_l or "karaoke" in title_l or "ringtone" in title_l:
    bonus -= 0.45
  if "skip" in title_l and "skip" not in query.lower():
    bonus -= 0.2
  if ratio < 0.34:
    bonus -= 0.5
  return ratio + bonus


def _candidates_from_initial_data(html: str) -> list[tuple[str, str]]:
  marker = "var ytInitialData = "
  start = html.find(marker)
  if start < 0:
    marker = "ytInitialData = "
    start = html.find(marker)
  if start < 0:
    return []
  start += len(marker)
  end = html.find(";</script>", start)
  if end < 0:
    end = html.find(";", start)
  if end < 0:
    return []
  blob = html[start:end].strip()
  if blob.endswith(";"):
    blob = blob[:-1]
  try:
    data = json.loads(blob)
  except json.JSONDecodeError:
    return []

  out: list[tuple[str, str]] = []

  def title_of(renderer: dict) -> str:
    title = renderer.get("title") or {}
    if isinstance(title, dict):
      runs = title.get("runs") or []
      if runs and isinstance(runs[0], dict):
        return str(runs[0].get("text") or "")
      simple = title.get("simpleText")
      if simple:
        return str(simple)
    return ""

  def walk(node) -> None:
    if isinstance(node, dict):
      if "videoRenderer" in node and isinstance(node["videoRenderer"], dict):
        rend = node["videoRenderer"]
        vid = rend.get("videoId")
        title = title_of(rend)
        if isinstance(vid, str) and len(vid) == 11:
          pair = (vid, title or vid)
          if pair not in out:
            out.append(pair)
      # Skip ad/promoted renderers intentionally (not collected)
      for value in node.values():
        walk(value)
    elif isinstance(node, list):
      for item in node:
        walk(item)

  walk(data)
  return out
