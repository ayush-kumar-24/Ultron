"""SQLite repository implementations for domain entities."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from loguru import logger

from maira.core.domain.entities import (
  AutomationJob,
  Conversation,
  MemoryEntry,
  Message,
  Note,
  Task,
)
from maira.core.domain.value_objects import (
  AutomationActionType,
  AutomationRecurrence,
  AutomationStatus,
  MemoryCategory,
  MessageRole,
  Priority,
  TaskStatus,
)
from maira.core.interfaces.storage import Storage


def _utc_now() -> datetime:
  return datetime.now(timezone.utc)


def _to_iso(value: datetime) -> str:
  if value.tzinfo is None:
    value = value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc).isoformat()


def _from_iso(value: str) -> datetime:
  parsed = datetime.fromisoformat(value)
  if parsed.tzinfo is None:
    return parsed.replace(tzinfo=timezone.utc)
  return parsed.astimezone(timezone.utc)


class ConversationRepository:
  def __init__(self, storage: Storage) -> None:
    self._storage = storage

  def transaction(self):
    return self._storage.transaction()

  def create_conversation(self, title: str = "New chat") -> Conversation:
    now = _utc_now()
    conversation = Conversation(
      id=str(uuid.uuid4()),
      title=title,
      created_at=now,
      updated_at=now,
    )
    self._storage.execute(
      """
      INSERT INTO conversations (id, title, created_at, updated_at)
      VALUES (?, ?, ?, ?)
      """,
      (
        conversation.id,
        conversation.title,
        _to_iso(conversation.created_at),
        _to_iso(conversation.updated_at),
      ),
    )
    return conversation

  def get_conversation(self, conversation_id: str) -> Conversation | None:
    row = self._storage.fetchone(
      """
      SELECT id, title, created_at, updated_at
      FROM conversations
      WHERE id = ?
      """,
      (conversation_id,),
    )
    return self._row_to_conversation(row) if row else None

  def get_latest_conversation(self) -> Conversation | None:
    row = self._storage.fetchone(
      """
      SELECT id, title, created_at, updated_at
      FROM conversations
      ORDER BY updated_at DESC, rowid DESC
      LIMIT 1
      """
    )
    return self._row_to_conversation(row) if row else None

  def list_conversations(self) -> list[Conversation]:
    rows = self._storage.fetchall(
      """
      SELECT id, title, created_at, updated_at
      FROM conversations
      ORDER BY updated_at DESC, rowid DESC
      """
    )
    return [self._row_to_conversation(row) for row in rows]

  def update_title(self, conversation_id: str, title: str) -> None:
    now = _utc_now()
    self._storage.execute(
      """
      UPDATE conversations
      SET title = ?, updated_at = ?
      WHERE id = ?
      """,
      (title, _to_iso(now), conversation_id),
    )

  def touch(self, conversation_id: str) -> None:
    self._storage.execute(
      """
      UPDATE conversations
      SET updated_at = ?
      WHERE id = ?
      """,
      (_to_iso(_utc_now()), conversation_id),
    )

  def add_message(self, conversation_id: str, message: Message) -> Message:
    position_row = self._storage.fetchone(
      "SELECT COALESCE(MAX(position), -1) FROM messages WHERE conversation_id = ?",
      (conversation_id,),
    )
    position = int(position_row[0]) + 1 if position_row else 0
    message_id = message.id or str(uuid.uuid4())
    timestamp = message.timestamp or _utc_now()

    self._storage.execute(
      """
      INSERT INTO messages (id, conversation_id, role, content, created_at, position)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      (
        message_id,
        conversation_id,
        message.role.value,
        message.content,
        _to_iso(timestamp),
        position,
      ),
    )
    self.touch(conversation_id)

    return Message(
      id=message_id,
      conversation_id=conversation_id,
      role=message.role,
      content=message.content,
      timestamp=timestamp,
    )

  def get_messages(self, conversation_id: str) -> list[Message]:
    rows = self._storage.fetchall(
      """
      SELECT id, conversation_id, role, content, created_at
      FROM messages
      WHERE conversation_id = ?
      ORDER BY position ASC
      """,
      (conversation_id,),
    )
    return [
      Message(
        id=str(row[0]),
        conversation_id=str(row[1]),
        role=MessageRole(str(row[2])),
        content=str(row[3]),
        timestamp=_from_iso(str(row[4])),
      )
      for row in rows
    ]

  @staticmethod
  def _row_to_conversation(row: tuple) -> Conversation:
    return Conversation(
      id=str(row[0]),
      title=str(row[1]),
      created_at=_from_iso(str(row[2])),
      updated_at=_from_iso(str(row[3])),
    )


class TaskRepository:
  def __init__(self, storage: Storage) -> None:
    self._storage = storage

  def create(
    self,
    title: str,
    *,
    priority: Priority = Priority.MEDIUM,
    due_at: datetime | None = None,
  ) -> Task:
    now = _utc_now()
    task = Task(
      id=str(uuid.uuid4()),
      title=title.strip(),
      status=TaskStatus.OPEN,
      priority=priority,
      due_at=due_at,
      created_at=now,
      updated_at=now,
    )
    self._storage.execute(
      """
      INSERT INTO tasks (id, title, status, priority, due_at, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      """,
      (
        task.id,
        task.title,
        task.status.value,
        task.priority.value,
        _to_iso(due_at) if due_at else None,
        _to_iso(task.created_at),
        _to_iso(task.updated_at),
      ),
    )
    return task

  def list_tasks(self) -> list[Task]:
    rows = self._storage.fetchall(
      """
      SELECT id, title, status, priority, due_at, created_at, updated_at
      FROM tasks
      ORDER BY
        CASE status WHEN 'open' THEN 0 ELSE 1 END,
        CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
        updated_at DESC
      """
    )
    return [self._row_to_task(row) for row in rows]

  def get(self, task_id: str) -> Task | None:
    row = self._storage.fetchone(
      """
      SELECT id, title, status, priority, due_at, created_at, updated_at
      FROM tasks
      WHERE id = ?
      """,
      (task_id,),
    )
    return self._row_to_task(row) if row else None

  def set_status(self, task_id: str, status: TaskStatus) -> Task | None:
    self._storage.execute(
      """
      UPDATE tasks
      SET status = ?, updated_at = ?
      WHERE id = ?
      """,
      (status.value, _to_iso(_utc_now()), task_id),
    )
    return self.get(task_id)

  def set_priority(self, task_id: str, priority: Priority) -> Task | None:
    self._storage.execute(
      """
      UPDATE tasks
      SET priority = ?, updated_at = ?
      WHERE id = ?
      """,
      (priority.value, _to_iso(_utc_now()), task_id),
    )
    return self.get(task_id)

  def update_title(self, task_id: str, title: str) -> Task | None:
    self._storage.execute(
      """
      UPDATE tasks
      SET title = ?, updated_at = ?
      WHERE id = ?
      """,
      (title.strip(), _to_iso(_utc_now()), task_id),
    )
    return self.get(task_id)

  def delete(self, task_id: str) -> None:
    self._storage.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

  @staticmethod
  def _row_to_task(row: tuple) -> Task:
    due_raw = row[4]
    return Task(
      id=str(row[0]),
      title=str(row[1]),
      status=TaskStatus(str(row[2])),
      priority=Priority(str(row[3])),
      due_at=_from_iso(str(due_raw)) if due_raw else None,
      created_at=_from_iso(str(row[5])),
      updated_at=_from_iso(str(row[6])),
    )


class NoteRepository:
  def __init__(self, storage: Storage) -> None:
    self._storage = storage

  def create(self, title: str, body: str = "") -> Note:
    now = _utc_now()
    note = Note(
      id=str(uuid.uuid4()),
      title=title.strip() or "Untitled",
      body=body,
      created_at=now,
      updated_at=now,
    )
    self._storage.execute(
      """
      INSERT INTO notes (id, title, body, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?)
      """,
      (
        note.id,
        note.title,
        note.body,
        _to_iso(note.created_at),
        _to_iso(note.updated_at),
      ),
    )
    return note

  def list_notes(self) -> list[Note]:
    rows = self._storage.fetchall(
      """
      SELECT id, title, body, created_at, updated_at
      FROM notes
      ORDER BY updated_at DESC
      """
    )
    return [self._row_to_note(row) for row in rows]

  def get(self, note_id: str) -> Note | None:
    row = self._storage.fetchone(
      """
      SELECT id, title, body, created_at, updated_at
      FROM notes
      WHERE id = ?
      """,
      (note_id,),
    )
    return self._row_to_note(row) if row else None

  def update(self, note_id: str, *, title: str, body: str) -> Note | None:
    self._storage.execute(
      """
      UPDATE notes
      SET title = ?, body = ?, updated_at = ?
      WHERE id = ?
      """,
      (title.strip() or "Untitled", body, _to_iso(_utc_now()), note_id),
    )
    return self.get(note_id)

  def delete(self, note_id: str) -> None:
    self._storage.execute("DELETE FROM notes WHERE id = ?", (note_id,))

  @staticmethod
  def _row_to_note(row: tuple) -> Note:
    return Note(
      id=str(row[0]),
      title=str(row[1]),
      body=str(row[2]),
      created_at=_from_iso(str(row[3])),
      updated_at=_from_iso(str(row[4])),
    )


class MemoryRepository:
  def __init__(self, storage: Storage) -> None:
    self._storage = storage

  def create(self, *, category: MemoryCategory, title: str, body: str) -> MemoryEntry:
    now = _utc_now()
    entry = MemoryEntry(
      id=str(uuid.uuid4()),
      category=category,
      title=title.strip() or "Untitled",
      body=body.strip(),
      created_at=now,
      updated_at=now,
    )
    self._storage.execute(
      """
      INSERT INTO memories (id, category, title, body, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      (
        entry.id,
        entry.category.value,
        entry.title,
        entry.body,
        _to_iso(entry.created_at),
        _to_iso(entry.updated_at),
      ),
    )
    return entry

  def get(self, memory_id: str) -> MemoryEntry | None:
    row = self._storage.fetchone(
      """
      SELECT id, category, title, body, created_at, updated_at
      FROM memories
      WHERE id = ?
      """,
      (memory_id,),
    )
    return self._row_to_memory(row) if row else None

  def list_memories(self, category: MemoryCategory | None = None) -> list[MemoryEntry]:
    if category is None:
      rows = self._storage.fetchall(
        """
        SELECT id, category, title, body, created_at, updated_at
        FROM memories
        ORDER BY updated_at DESC
        """
      )
    else:
      rows = self._storage.fetchall(
        """
        SELECT id, category, title, body, created_at, updated_at
        FROM memories
        WHERE category = ?
        ORDER BY updated_at DESC
        """,
        (category.value,),
      )
    return [self._row_to_memory(row) for row in rows]

  def search_keyword(
    self,
    query: str,
    *,
    category: MemoryCategory | None = None,
  ) -> list[MemoryEntry]:
    cleaned = query.strip()
    if not cleaned:
      return self.list_memories(category)

    like = f"%{cleaned}%"
    if category is None:
      rows = self._storage.fetchall(
        """
        SELECT id, category, title, body, created_at, updated_at
        FROM memories
        WHERE title LIKE ? OR body LIKE ?
        ORDER BY updated_at DESC
        """,
        (like, like),
      )
    else:
      rows = self._storage.fetchall(
        """
        SELECT id, category, title, body, created_at, updated_at
        FROM memories
        WHERE category = ? AND (title LIKE ? OR body LIKE ?)
        ORDER BY updated_at DESC
        """,
        (category.value, like, like),
      )
    return [self._row_to_memory(row) for row in rows]

  def update(
    self,
    memory_id: str,
    *,
    category: MemoryCategory,
    title: str,
    body: str,
  ) -> MemoryEntry | None:
    self._storage.execute(
      """
      UPDATE memories
      SET category = ?, title = ?, body = ?, updated_at = ?
      WHERE id = ?
      """,
      (
        category.value,
        title.strip() or "Untitled",
        body.strip(),
        _to_iso(_utc_now()),
        memory_id,
      ),
    )
    return self.get(memory_id)

  def delete(self, memory_id: str) -> None:
    self._storage.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

  @staticmethod
  def _row_to_memory(row: tuple) -> MemoryEntry:
    return MemoryEntry(
      id=str(row[0]),
      category=parse_memory_category(row[1]),
      title=str(row[2]),
      body=str(row[3]),
      created_at=_from_iso(str(row[4])),
      updated_at=_from_iso(str(row[5])),
    )


def parse_memory_category(raw: object) -> MemoryCategory:
  """Read a stored category leniently; one odd row must never crash startup."""
  value = str(raw or "").strip().lower()
  for candidate in (value, value[:-1] if value.endswith("s") else value):
    try:
      return MemoryCategory(candidate)
    except ValueError:
      continue
  logger.warning("Unknown memory category {!r}; treating as note", raw)
  return MemoryCategory.NOTE


class AutomationRepository:
  def __init__(self, storage: Storage) -> None:
    self._storage = storage

  def create(
    self,
    title: str,
    instruction: str,
    run_at: datetime,
    *,
    action_type: AutomationActionType = AutomationActionType.AGENT,
    action_payload: str = "{}",
    recurrence: AutomationRecurrence = AutomationRecurrence.NONE,
    enabled: bool = True,
  ) -> AutomationJob:
    now = _utc_now()
    job = AutomationJob(
      id=str(uuid.uuid4()),
      title=title.strip() or "Automation",
      instruction=instruction.strip(),
      action_type=action_type,
      action_payload=action_payload or "{}",
      run_at=run_at,
      recurrence=recurrence,
      enabled=enabled,
      status=AutomationStatus.PENDING,
      created_at=now,
      updated_at=now,
    )
    self._storage.execute(
      """
      INSERT INTO automations (
        id, title, instruction, action_type, action_payload,
        run_at, recurrence, enabled, status, last_run_at, last_error,
        created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
      """,
      (
        job.id,
        job.title,
        job.instruction,
        job.action_type.value,
        job.action_payload,
        _to_iso(job.run_at),
        job.recurrence.value,
        1 if job.enabled else 0,
        job.status.value,
        _to_iso(job.created_at),
        _to_iso(job.updated_at),
      ),
    )
    return job

  def list_jobs(self, *, include_done: bool = True) -> list[AutomationJob]:
    if include_done:
      rows = self._storage.fetchall(
        """
        SELECT id, title, instruction, action_type, action_payload,
               run_at, recurrence, enabled, status, last_run_at, last_error,
               created_at, updated_at
        FROM automations
        ORDER BY run_at ASC
        """
      )
    else:
      rows = self._storage.fetchall(
        """
        SELECT id, title, instruction, action_type, action_payload,
               run_at, recurrence, enabled, status, last_run_at, last_error,
               created_at, updated_at
        FROM automations
        WHERE status = 'pending'
        ORDER BY run_at ASC
        """
      )
    return [self._row_to_job(row) for row in rows]

  def get(self, job_id: str) -> AutomationJob | None:
    row = self._storage.fetchone(
      """
      SELECT id, title, instruction, action_type, action_payload,
             run_at, recurrence, enabled, status, last_run_at, last_error,
             created_at, updated_at
      FROM automations
      WHERE id = ?
      """,
      (job_id,),
    )
    return self._row_to_job(row) if row else None

  def set_enabled(self, job_id: str, enabled: bool) -> AutomationJob | None:
    self._storage.execute(
      """
      UPDATE automations
      SET enabled = ?, updated_at = ?
      WHERE id = ?
      """,
      (1 if enabled else 0, _to_iso(_utc_now()), job_id),
    )
    return self.get(job_id)

  def set_status(self, job_id: str, status: AutomationStatus) -> AutomationJob | None:
    self._storage.execute(
      """
      UPDATE automations
      SET status = ?, updated_at = ?
      WHERE id = ?
      """,
      (status.value, _to_iso(_utc_now()), job_id),
    )
    return self.get(job_id)

  def mark_ran(
    self,
    job_id: str,
    *,
    ok: bool,
    error: str | None = None,
    next_run_at: datetime | None = None,
  ) -> AutomationJob | None:
    now = _utc_now()
    if next_run_at is not None:
      self._storage.execute(
        """
        UPDATE automations
        SET status = ?, run_at = ?, last_run_at = ?, last_error = ?, updated_at = ?
        WHERE id = ?
        """,
        (
          AutomationStatus.PENDING.value,
          _to_iso(next_run_at),
          _to_iso(now),
          error,
          _to_iso(now),
          job_id,
        ),
      )
    else:
      status = AutomationStatus.DONE if ok else AutomationStatus.FAILED
      self._storage.execute(
        """
        UPDATE automations
        SET status = ?, last_run_at = ?, last_error = ?, updated_at = ?
        WHERE id = ?
        """,
        (status.value, _to_iso(now), error, _to_iso(now), job_id),
      )
    return self.get(job_id)

  def delete(self, job_id: str) -> None:
    self._storage.execute("DELETE FROM automations WHERE id = ?", (job_id,))

  def due_jobs(self, now: datetime) -> list[AutomationJob]:
    rows = self._storage.fetchall(
      """
      SELECT id, title, instruction, action_type, action_payload,
             run_at, recurrence, enabled, status, last_run_at, last_error,
             created_at, updated_at
      FROM automations
      WHERE enabled = 1 AND status = 'pending' AND run_at <= ?
      ORDER BY run_at ASC
      """,
      (_to_iso(now),),
    )
    return [self._row_to_job(row) for row in rows]

  @staticmethod
  def _row_to_job(row: tuple) -> AutomationJob:
    return AutomationJob(
      id=str(row[0]),
      title=str(row[1]),
      instruction=str(row[2]),
      action_type=AutomationActionType(str(row[3])),
      action_payload=str(row[4] or "{}"),
      run_at=_from_iso(str(row[5])),
      recurrence=AutomationRecurrence(str(row[6])),
      enabled=bool(int(row[7])),
      status=AutomationStatus(str(row[8])),
      last_run_at=_from_iso(str(row[9])) if row[9] else None,
      last_error=str(row[10]) if row[10] else None,
      created_at=_from_iso(str(row[11])),
      updated_at=_from_iso(str(row[12])),
    )
