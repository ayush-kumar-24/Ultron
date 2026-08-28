"""Conversations and POST /chat/stream — wraps BrainService over the event bus."""

from __future__ import annotations

import json
import queue
import threading
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from loguru import logger

from maira.api.deps import get_brain, get_conversations, get_event_bus, get_memory
from maira.api.mapping import (
  conversation_to_api,
  iso,
  memory_category_from_api,
  memory_to_api,
  message_to_api,
  title_from_text,
)
from maira.api.schemas import ChatStreamIn, ConversationCreate, ConversationPatch, MessageMemoryIn
from maira.core.domain.value_objects import MessageRole
from maira.modules.brain.service import ConversationNotFoundError
from maira.modules.brain.streaming import TOPIC_COMPLETE, TOPIC_ERROR, TOPIC_TOKEN

router = APIRouter(tags=["chat"])


def _sse(payload: dict) -> str:
  return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/conversations")
def list_conversations() -> list[dict]:
  return [conversation_to_api(item) for item in get_conversations().list_conversations()]


@router.post("/conversations")
def create_conversation(body: ConversationCreate) -> dict:
  title = (body.title or "").strip() or "New conversation"
  created = get_conversations().create_conversation(title, project_id=body.projectId)
  return conversation_to_api(created)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
  conversation = get_conversations().get_conversation(conversation_id)
  if conversation is None:
    raise HTTPException(status_code=404, detail="Conversation not found")
  return conversation_to_api(conversation)


@router.patch("/conversations/{conversation_id}")
def patch_conversation(conversation_id: str, body: ConversationPatch) -> dict:
  dump = body.model_dump(exclude_unset=True)
  updated = get_conversations().update_conversation(
    conversation_id,
    title=dump.get("title"),
    pinned=dump.get("pinned"),
    project_id=dump.get("projectId"),
    clear_project="projectId" in dump and dump["projectId"] is None,
  )
  if updated is None:
    raise HTTPException(status_code=404, detail="Conversation not found")
  return conversation_to_api(updated)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> Response:
  repo = get_conversations()
  if not repo.delete_conversation(conversation_id):
    raise HTTPException(status_code=404, detail="Conversation not found")
  brain = get_brain()
  try:
    active = brain.get_active_conversation()
    if active.id == conversation_id:
      latest = repo.get_latest_conversation()
      if latest is not None:
        brain.open_conversation(latest.id)
      else:
        brain.new_conversation()
  except Exception as exc:  # noqa: BLE001
    logger.warning("Could not reset active conversation after delete: {}", exc)
  return Response(status_code=204)


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: str) -> list[dict]:
  repo = get_conversations()
  if repo.get_conversation(conversation_id) is None:
    raise HTTPException(status_code=404, detail="Conversation not found")
  return [message_to_api(item) for item in repo.get_messages(conversation_id)]


@router.post("/messages/{message_id}/memory")
def save_message_memory(message_id: str, body: MessageMemoryIn) -> dict:
  message = get_conversations().get_message(message_id)
  if message is None:
    raise HTTPException(status_code=404, detail="Message not found")
  text = (body.text or message.content).strip()
  if not text:
    raise HTTPException(status_code=400, detail="Memory text is empty")
  memory = get_memory()
  try:
    entry = memory.store(
      category=memory_category_from_api("conversations"),
      title=title_from_text(text),
      body=text,
      source="Saved from chat",
      importance="medium",
    )
  except TypeError:
    entry = memory.store(
      category=memory_category_from_api("conversations"),
      title=title_from_text(text),
      body=text,
    )
  return memory_to_api(entry)


@router.post("/chat/stream")
def chat_stream(body: ChatStreamIn) -> StreamingResponse:
  text = (body.text or "").strip()
  if not text:
    raise HTTPException(status_code=400, detail="Message is empty")

  repo = get_conversations()
  conversation_id = (body.conversationId or "").strip()
  if not conversation_id:
    project_id = body.context.projectId if body.context else None
    created = repo.create_conversation(title_from_text(text), project_id=project_id)
    conversation_id = created.id
  elif repo.get_conversation(conversation_id) is None:
    raise HTTPException(status_code=404, detail="Conversation not found")

  def generate():
    bus = get_event_bus()
    events: queue.Queue[tuple[str, object]] = queue.Queue()

    def on_token(payload) -> None:
      token = payload.get("token", "") if isinstance(payload, dict) else str(payload)
      events.put(("token", token))

    def on_complete(payload) -> None:
      content = payload.get("content", "") if isinstance(payload, dict) else str(payload)
      events.put(("complete", content))

    def on_error(payload) -> None:
      message = payload.get("message", "The model failed") if isinstance(payload, dict) else str(payload)
      events.put(("error", message))

    bus.subscribe(TOPIC_TOKEN, on_token)
    bus.subscribe(TOPIC_COMPLETE, on_complete)
    bus.subscribe(TOPIC_ERROR, on_error)

    def run() -> None:
      try:
        brain = get_brain()
        send = getattr(brain, "send_in_conversation", None)
        if callable(send):
          send(conversation_id, text)
        else:
          brain.open_conversation(conversation_id)
          brain.send_message(text)
      except ConversationNotFoundError:
        events.put(("error", "Conversation not found"))
      except Exception as exc:  # noqa: BLE001
        logger.exception("Chat stream failed")
        events.put(("fail", str(exc) or "Ultron hit an internal error"))
      finally:
        events.put(("end", None))

    worker = threading.Thread(target=run, name="ultron-chat-stream", daemon=True)
    worker.start()

    user_payload = {
      "id": str(uuid.uuid4()),
      "role": "user",
      "text": text,
      "at": iso(datetime.now(timezone.utc)),
    }
    yield _sse({"type": "user", "payload": user_payload})
    yield _sse({"type": "state", "state": "thinking"})

    finished = False
    speaking = False
    try:
      while True:
        kind, payload = events.get()
        if kind == "end":
          break
        if kind == "token":
          if not speaking:
            speaking = True
            yield _sse({"type": "state", "state": "speaking"})
          yield _sse({"type": "token", "text": payload})
        elif kind == "complete":
          conversation = repo.get_conversation(conversation_id)
          messages = repo.get_messages(conversation_id)
          assistant = next(
            (item for item in reversed(messages) if item.role == MessageRole.ASSISTANT),
            None,
          )
          if assistant is None:
            assistant_payload = {
              "id": str(uuid.uuid4()),
              "role": "assistant",
              "text": str(payload or ""),
              "at": iso(datetime.now(timezone.utc)),
            }
          else:
            assistant_payload = message_to_api(assistant)
          yield _sse({
            "type": "done",
            "payload": {
              "message": assistant_payload,
              "conversation": conversation_to_api(conversation) if conversation else {
                "id": conversation_id,
                "title": title_from_text(text),
                "projectId": None,
                "updatedAt": iso(datetime.now(timezone.utc)),
                "pinned": False,
              },
            },
          })
          finished = True
        elif kind in {"error", "fail"}:
          status = 503 if kind == "error" else 500
          yield _sse({
            "type": "error",
            "status": status,
            "message": str(payload),
            "detail": str(payload),
          })
          finished = True
      if not finished:
        yield _sse({
          "type": "error",
          "status": 500,
          "message": "The model did not finish",
          "detail": "The model did not finish",
        })
    finally:
      bus.unsubscribe(TOPIC_TOKEN, on_token)
      bus.unsubscribe(TOPIC_COMPLETE, on_complete)
      bus.unsubscribe(TOPIC_ERROR, on_error)
      worker.join(timeout=0.1)

  return StreamingResponse(
    generate(),
    media_type="text/event-stream",
    headers={
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  )
