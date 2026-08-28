"""Memory CRUD matching the frontend contract. Deletes are permanent."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Response

from maira.api.deps import get_memory
from maira.api.mapping import (
  API_MEMORY_CATEGORIES,
  category_filter_values,
  memory_category_from_api,
  memory_category_to_api,
  memory_to_api,
  title_from_text,
)
from maira.api.schemas import MemoryCreate, MemoryPatch

router = APIRouter(tags=["memory"])


def _list_entries(*, category: str | None, q: str | None):
  memory = get_memory()
  query = (q or "").strip()
  if query:
    entries = memory.search(query) if hasattr(memory, "search") else memory.search_keyword(query)
  else:
    entries = memory.list_memories()

  if category and category != "all":
    allowed = category_filter_values(category)
    entries = [item for item in entries if memory_category_to_api(item.category) in allowed or item.category.value in allowed]

  entries.sort(key=lambda item: (not item.pinned, -(item.created_at.timestamp() if item.created_at else 0)))
  return entries


@router.get("/memories")
def list_memories(
  category: str | None = Query(default=None),
  q: str | None = Query(default=None),
) -> list[dict]:
  if category and category not in {"all", *API_MEMORY_CATEGORIES}:
    raise HTTPException(status_code=400, detail="Unknown memory category")
  return [memory_to_api(item) for item in _list_entries(category=category, q=q)]


@router.get("/memory/stats")
def memory_stats() -> dict:
  entries = list(get_memory().list_memories())
  total = len(entries)
  pinned = sum(1 for item in entries if item.pinned)
  now = datetime.now().astimezone()
  start = datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
  if start.tzinfo is None:
    start = start.replace(tzinfo=timezone.utc)
  learned_today = 0
  by_category: dict[str, int] = {}
  for item in entries:
    created = item.created_at
    if created.tzinfo is None:
      created = created.replace(tzinfo=timezone.utc)
    if created >= start.astimezone(created.tzinfo):
      learned_today += 1
    key = memory_category_to_api(item.category)
    by_category[key] = by_category.get(key, 0) + 1
  return {
    "total": total,
    "recall": 100 if total else 0,
    "learnedToday": learned_today,
    "pinned": pinned,
    "byCategory": by_category,
  }


@router.post("/memories")
def create_memory(body: MemoryCreate) -> dict:
  text = (body.text or "").strip()
  if not text:
    raise HTTPException(status_code=400, detail="Memory text is empty")
  category = memory_category_from_api(body.category)
  importance = (body.importance or "medium").lower()
  if importance not in {"high", "medium", "low"}:
    importance = "medium"
  memory = get_memory()
  try:
    entry = memory.store(
      category=category,
      title=title_from_text(text),
      body=text,
      source="Teach Ultron",
      importance=importance,
    )
  except TypeError:
    entry = memory.store(category=category, title=title_from_text(text), body=text)
  return memory_to_api(entry)


@router.patch("/memories/{memory_id}")
def patch_memory(memory_id: str, body: MemoryPatch) -> dict:
  memory = get_memory()
  current = memory.get(memory_id)
  if current is None:
    raise HTTPException(status_code=404, detail="Memory not found")
  dump = body.model_dump(exclude_unset=True)
  fields: dict = {}
  if "text" in dump and dump["text"] is not None:
    text = str(dump["text"]).strip()
    if not text:
      raise HTTPException(status_code=400, detail="Memory text is empty")
    fields["title"] = title_from_text(text)
    fields["body"] = text
  if "category" in dump and dump["category"]:
    fields["category"] = memory_category_from_api(str(dump["category"]))
  if "importance" in dump and dump["importance"]:
    fields["importance"] = str(dump["importance"])
  if "pinned" in dump:
    fields["pinned"] = bool(dump["pinned"])
  if "source" in dump and dump["source"] is not None:
    fields["source"] = str(dump["source"])
  patch = getattr(memory, "patch", None)
  if callable(patch) and fields:
    updated = patch(memory_id, **fields)
  else:
    updated = memory.update(
      memory_id,
      category=fields.get("category", current.category),
      title=fields.get("title", current.title),
      body=fields.get("body", current.body),
    )
  if updated is None:
    raise HTTPException(status_code=404, detail="Memory not found")
  return memory_to_api(updated)


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str) -> Response:
  memory = get_memory()
  if memory.get(memory_id) is None:
    raise HTTPException(status_code=404, detail="Memory not found")
  memory.delete(memory_id)
  if memory.get(memory_id) is not None:
    raise HTTPException(status_code=500, detail="Memory could not be deleted")
  return Response(status_code=204)
