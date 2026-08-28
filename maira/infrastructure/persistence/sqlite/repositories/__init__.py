"""SQLite repository implementations for domain entities."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from maira.core.domain.entities import (
  AutomationRun,
  CalendarEvent,
  Notification,
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

  _CONVERSATION_COLUMNS = "id, title, created_at, updated_at, pinned, project_id"

  def create_conversation(
    self,
    title: str = "New chat",
    *,
    project_id: str | None = None,
    pinned: bool = False,
  ) -> Conversation:
    now = _utc_now()
    conversation = Conversation(
      id=str(uuid.uuid4()),
      title=title,
      created_at=now,
      updated_at=now,
      pinned=pinned,
      project_id=project_id,
    )
    self._storage.execute(
      """
      INSERT INTO conversations (id, title, created_at, updated_at, pinned, project_id)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      (
        conversation.id,
        conversation.title,
        _to_iso(conversation.created_at),
        _to_iso(conversation.updated_at),
        1 if conversation.pinned else 0,
        conversation.project_id,
      ),
    )
    return conversation

  def get_conversation(self, conversation_id: str) -> Conversation | None:
    row = self._storage.fetchone(
      f"""
      SELECT {self._CONVERSATION_COLUMNS}
      FROM conversations
      WHERE id = ?
      """,
      (conversation_id,),
    )
    return self._row_to_conversation(row) if row else None

  def get_latest_conversation(self) -> Conversation | None:
    row = self._storage.fetchone(
      f"""
      SELECT {self._CONVERSATION_COLUMNS}
      FROM conversations
      ORDER BY updated_at DESC, rowid DESC
      LIMIT 1
      """
    )
    return self._row_to_conversation(row) if row else None

  def list_conversations(self) -> list[Conversation]:
    rows = self._storage.fetchall(
      f"""
      SELECT {self._CONVERSATION_COLUMNS}
      FROM conversations
      ORDER BY pinned DESC, updated_at DESC, rowid DESC
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

  def update_conversation(
    self,
    conversation_id: str,
    *,
    title: str | None = None,
    pinned: bool | None = None,
    project_id: str | None = None,
    clear_project: bool = False,
  ) -> Conversation | None:
    current = self.get_conversation(conversation_id)
    if current is None:
      return None
    next_title = title if title is not None else current.title
    next_pinned = current.pinned if pinned is None else pinned
    next_project = current.project_id
    if clear_project:
      next_project = None
    elif project_id is not None:
      next_project = project_id
    self._storage.execute(
      """
      UPDATE conversations
      SET title = ?, pinned = ?, project_id = ?, updated_at = ?
      WHERE id = ?
      """,
      (
        next_title,
        1 if next_pinned else 0,
        next_project,
        _to_iso(_utc_now()),
        conversation_id,
      ),
    )
    return self.get_conversation(conversation_id)

  def delete_conversation(self, conversation_id: str) -> bool:
    existing = self.get_conversation(conversation_id)
    if existing is None:
      return False
    self._storage.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    return True

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
    return [self._row_to_message(row) for row in rows]

  def get_message(self, message_id: str) -> Message | None:
    row = self._storage.fetchone(
      """
      SELECT id, conversation_id, role, content, created_at
      FROM messages
      WHERE id = ?
      """,
      (message_id,),
    )
    return self._row_to_message(row) if row else None

  @staticmethod
  def _row_to_message(row: tuple) -> Message:
    return Message(
      id=str(row[0]),
      conversation_id=str(row[1]),
      role=MessageRole(str(row[2])),
      content=str(row[3]),
      timestamp=_from_iso(str(row[4])),
    )

  @staticmethod
  def _row_to_conversation(row: tuple) -> Conversation:
    pinned = bool(row[4]) if len(row) > 4 else False
    project_id = str(row[5]) if len(row) > 5 and row[5] else None
    return Conversation(
      id=str(row[0]),
      title=str(row[1]),
      created_at=_from_iso(str(row[2])),
      updated_at=_from_iso(str(row[3])),
      pinned=pinned,
      project_id=project_id,
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
    description: str = "",
    project_id: str | None = None,
    tags: list[str] | None = None,
    estimate: int = 30,
    recurrence: str | None = None,
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
      description=description,
      project_id=project_id,
      tags=list(tags or []),
      estimate=estimate,
      recurrence=recurrence,
      stage="todo",
    )
    self._storage.execute(
      """
      INSERT INTO tasks (
        id, title, status, priority, due_at, created_at, updated_at,
        description, project_id, tags, estimate, recurrence, completed_at, stage
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      """,
      (
        task.id,
        task.title,
        task.status.value,
        task.priority.value,
        _to_iso(due_at) if due_at else None,
        _to_iso(task.created_at),
        _to_iso(task.updated_at),
        task.description,
        task.project_id,
        json.dumps(task.tags),
        task.estimate,
        task.recurrence,
        None,
        task.stage,
      ),
    )
    return task

  def update_task(
    self,
    task_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    priority: Priority | None = None,
    stage: str | None = None,
    due_at: datetime | None = None,
    clear_due: bool = False,
    project_id: str | None = None,
    tags: list[str] | None = None,
    estimate: int | None = None,
  ) -> Task | None:
    """Patch any subset of a task. `stage` keeps the domain status in sync."""
    existing = self.get(task_id)
    if existing is None:
      return None

    sets: list[str] = []
    values: list[object] = []

    def assign(column: str, value: object) -> None:
      sets.append(f"{column} = ?")
      values.append(value)

    if title is not None:
      assign("title", title.strip())
    if description is not None:
      assign("description", description)
    if priority is not None:
      assign("priority", priority.value)
    if project_id is not None:
      assign("project_id", project_id)
    if tags is not None:
      assign("tags", json.dumps(list(tags)))
    if estimate is not None:
      assign("estimate", int(estimate))
    if clear_due:
      assign("due_at", None)
    elif due_at is not None:
      assign("due_at", _to_iso(due_at))

    if stage is not None:
      assign("stage", stage)
      done = stage == "done"
      assign("status", TaskStatus.DONE.value if done else TaskStatus.OPEN.value)
      if done and existing.completed_at is None:
        assign("completed_at", _to_iso(_utc_now()))
      elif not done:
        assign("completed_at", None)

    if not sets:
      return existing

    assign("updated_at", _to_iso(_utc_now()))
    values.append(task_id)
    self._storage.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", tuple(values))
    return self.get(task_id)

  def list_tasks(self) -> list[Task]:
    rows = self._storage.fetchall(
      """
      SELECT id, title, status, priority, due_at, created_at, updated_at, description, project_id, tags, estimate, recurrence, completed_at, stage
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
      SELECT id, title, status, priority, due_at, created_at, updated_at, description, project_id, tags, estimate, recurrence, completed_at, stage
      FROM tasks
      WHERE id = ?
      """,
      (task_id,),
    )
    return self._row_to_task(row) if row else None

  def set_status(self, task_id: str, status: TaskStatus) -> Task | None:
    done = status == TaskStatus.DONE
    self._storage.execute(
      """
      UPDATE tasks
      SET status = ?, stage = ?, completed_at = ?, updated_at = ?
      WHERE id = ?
      """,
      (
        status.value,
        "done" if done else "todo",
        _to_iso(_utc_now()) if done else None,
        _to_iso(_utc_now()),
        task_id,
      ),
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
    try:
      tags = json.loads(str(row[9] or "[]"))
    except json.JSONDecodeError:
      tags = []
    completed_raw = row[12]
    return Task(
      id=str(row[0]),
      title=str(row[1]),
      status=TaskStatus(str(row[2])),
      priority=Priority(str(row[3])),
      due_at=_from_iso(str(due_raw)) if due_raw else None,
      created_at=_from_iso(str(row[5])),
      updated_at=_from_iso(str(row[6])),
      description=str(row[7] or ""),
      project_id=str(row[8]) if row[8] else None,
      tags=tags if isinstance(tags, list) else [],
      estimate=int(row[10] or 30),
      recurrence=str(row[11]) if row[11] else None,
      completed_at=_from_iso(str(completed_raw)) if completed_raw else None,
      stage=str(row[13] or "todo"),
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

  _COLUMNS = (
    "id, category, title, body, created_at, updated_at, "
    "source, confidence, importance, pinned, last_accessed, access_count"
  )

  def create(
    self,
    *,
    category: MemoryCategory,
    title: str,
    body: str,
    source: str = "",
    confidence: float = 0.9,
    importance: str = "medium",
    pinned: bool = False,
  ) -> MemoryEntry:
    now = _utc_now()
    entry = MemoryEntry(
      id=str(uuid.uuid4()),
      category=category,
      title=title.strip() or "Untitled",
      body=body.strip(),
      created_at=now,
      updated_at=now,
      source=source,
      confidence=confidence,
      importance=importance,
      pinned=pinned,
      last_accessed=now,
      access_count=0,
    )
    self._storage.execute(
      f"""
      INSERT INTO memories ({self._COLUMNS})
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      """,
      (
        entry.id,
        entry.category.value,
        entry.title,
        entry.body,
        _to_iso(entry.created_at),
        _to_iso(entry.updated_at),
        entry.source,
        entry.confidence,
        entry.importance,
        1 if entry.pinned else 0,
        _to_iso(entry.last_accessed) if entry.last_accessed else None,
        entry.access_count,
      ),
    )
    return entry

  def get(self, memory_id: str) -> MemoryEntry | None:
    row = self._storage.fetchone(
      f"""
      SELECT {self._COLUMNS}
      FROM memories
      WHERE id = ?
      """,
      (memory_id,),
    )
    return self._row_to_memory(row) if row else None

  def list_memories(self, category: MemoryCategory | None = None) -> list[MemoryEntry]:
    if category is None:
      rows = self._storage.fetchall(
        f"""
        SELECT {self._COLUMNS}
        FROM memories
        ORDER BY pinned DESC, updated_at DESC
        """
      )
    else:
      rows = self._storage.fetchall(
        f"""
        SELECT {self._COLUMNS}
        FROM memories
        WHERE category = ?
        ORDER BY pinned DESC, updated_at DESC
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
        f"""
        SELECT {self._COLUMNS}
        FROM memories
        WHERE title LIKE ? OR body LIKE ? OR source LIKE ?
        ORDER BY pinned DESC, updated_at DESC
        """,
        (like, like, like),
      )
    else:
      rows = self._storage.fetchall(
        f"""
        SELECT {self._COLUMNS}
        FROM memories
        WHERE category = ? AND (title LIKE ? OR body LIKE ? OR source LIKE ?)
        ORDER BY pinned DESC, updated_at DESC
        """,
        (category.value, like, like, like),
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
    current = self.get(memory_id)
    if current is None:
      return None
    return self.patch(
      memory_id,
      category=category,
      title=title,
      body=body,
    )

  def patch(self, memory_id: str, **fields) -> MemoryEntry | None:
    current = self.get(memory_id)
    if current is None:
      return None
    category = fields["category"] if "category" in fields else current.category
    title = fields["title"] if "title" in fields else current.title
    body = fields["body"] if "body" in fields else current.body
    source = fields["source"] if "source" in fields else current.source
    confidence = fields["confidence"] if "confidence" in fields else current.confidence
    importance = fields["importance"] if "importance" in fields else current.importance
    pinned = fields["pinned"] if "pinned" in fields else current.pinned
    last_accessed = (
      fields["last_accessed"] if "last_accessed" in fields else current.last_accessed
    )
    access_count = (
      fields["access_count"] if "access_count" in fields else current.access_count
    )
    now = _utc_now()
    self._storage.execute(
      """
      UPDATE memories
      SET category = ?, title = ?, body = ?, source = ?, confidence = ?,
          importance = ?, pinned = ?, last_accessed = ?, access_count = ?, updated_at = ?
      WHERE id = ?
      """,
      (
        category.value if isinstance(category, MemoryCategory) else str(category),
        (title or "").strip() or "Untitled",
        (body or "").strip(),
        source or "",
        float(confidence),
        importance or "medium",
        1 if pinned else 0,
        _to_iso(last_accessed) if last_accessed else None,
        int(access_count),
        _to_iso(now),
        memory_id,
      ),
    )
    return self.get(memory_id)

  def delete(self, memory_id: str) -> None:
    self._storage.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

  @staticmethod
  def _row_to_memory(row: tuple) -> MemoryEntry:
    last_accessed_raw = row[10] if len(row) > 10 else None
    return MemoryEntry(
      id=str(row[0]),
      category=MemoryCategory(str(row[1])),
      title=str(row[2]),
      body=str(row[3]),
      created_at=_from_iso(str(row[4])),
      updated_at=_from_iso(str(row[5])),
      source=str(row[6]) if len(row) > 6 else "",
      confidence=float(row[7]) if len(row) > 7 and row[7] is not None else 0.9,
      importance=str(row[8]) if len(row) > 8 and row[8] else "medium",
      pinned=bool(row[9]) if len(row) > 9 else False,
      last_accessed=_from_iso(str(last_accessed_raw)) if last_accessed_raw else None,
      access_count=int(row[11]) if len(row) > 11 and row[11] is not None else 0,
    )


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


class CalendarEventRepository:
  """Calendar entries the web app shows — meetings, focus blocks, deadlines."""

  def __init__(self, storage: Storage) -> None:
    self._storage = storage

  def create(
    self,
    title: str,
    start_at: datetime,
    end_at: datetime | None = None,
    *,
    type: str = "meeting",
    project_id: str | None = None,
    task_id: str | None = None,
  ) -> CalendarEvent:
    event = CalendarEvent(
      id=str(uuid.uuid4()),
      title=title.strip(),
      start_at=start_at,
      end_at=end_at or start_at,
      type=type,
      project_id=project_id,
      task_id=task_id,
      created_at=_utc_now(),
    )
    self._storage.execute(
      """
      INSERT INTO calendar_events (id, title, start_at, end_at, type, project_id, task_id, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      """,
      (
        event.id,
        event.title,
        _to_iso(event.start_at),
        _to_iso(event.end_at),
        event.type,
        event.project_id,
        event.task_id,
        _to_iso(event.created_at),
      ),
    )
    return event

  def list_events(
    self,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
  ) -> list[CalendarEvent]:
    clauses: list[str] = []
    values: list[object] = []
    if start is not None:
      clauses.append("start_at >= ?")
      values.append(_to_iso(start))
    if end is not None:
      clauses.append("start_at <= ?")
      values.append(_to_iso(end))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = self._storage.fetchall(
      f"""
      SELECT id, title, start_at, end_at, type, project_id, task_id, created_at
      FROM calendar_events
      {where}
      ORDER BY start_at ASC
      """,
      tuple(values),
    )
    return [self._row_to_event(row) for row in rows]

  def get(self, event_id: str) -> CalendarEvent | None:
    row = self._storage.fetchone(
      """
      SELECT id, title, start_at, end_at, type, project_id, task_id, created_at
      FROM calendar_events
      WHERE id = ?
      """,
      (event_id,),
    )
    return self._row_to_event(row) if row else None

  def delete(self, event_id: str) -> bool:
    if self.get(event_id) is None:
      return False
    self._storage.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
    return True

  @staticmethod
  def _row_to_event(row: tuple) -> CalendarEvent:
    return CalendarEvent(
      id=str(row[0]),
      title=str(row[1]),
      start_at=_from_iso(str(row[2])),
      end_at=_from_iso(str(row[3])),
      type=str(row[4] or "meeting"),
      project_id=str(row[5]) if row[5] else None,
      task_id=str(row[6]) if row[6] else None,
      created_at=_from_iso(str(row[7])),
    )


class NotificationRepository:
  def __init__(self, storage: Storage) -> None:
    self._storage = storage

  def create(self, *, type: str, title: str, body: str = "") -> Notification:
    notification = Notification(
      id=str(uuid.uuid4()),
      type=type,
      title=title,
      body=body,
      created_at=_utc_now(),
      read=False,
    )
    self._storage.execute(
      """
      INSERT INTO notifications (id, type, title, body, created_at, read)
      VALUES (?, ?, ?, ?, ?, 0)
      """,
      (
        notification.id,
        notification.type,
        notification.title,
        notification.body,
        _to_iso(notification.created_at),
      ),
    )
    return notification

  def list_notifications(self, *, limit: int = 100) -> list[Notification]:
    rows = self._storage.fetchall(
      """
      SELECT id, type, title, body, created_at, read
      FROM notifications
      ORDER BY created_at DESC
      LIMIT ?
      """,
      (limit,),
    )
    return [self._row_to_notification(row) for row in rows]

  def get(self, notification_id: str) -> Notification | None:
    row = self._storage.fetchone(
      """
      SELECT id, type, title, body, created_at, read
      FROM notifications
      WHERE id = ?
      """,
      (notification_id,),
    )
    return self._row_to_notification(row) if row else None

  def set_read(self, notification_id: str, read: bool) -> Notification | None:
    if self.get(notification_id) is None:
      return None
    self._storage.execute(
      "UPDATE notifications SET read = ? WHERE id = ?",
      (1 if read else 0, notification_id),
    )
    return self.get(notification_id)

  def mark_all_read(self) -> int:
    unread = self._storage.fetchone("SELECT COUNT(*) FROM notifications WHERE read = 0")
    self._storage.execute("UPDATE notifications SET read = 1 WHERE read = 0")
    return int(unread[0]) if unread else 0

  def delete(self, notification_id: str) -> bool:
    if self.get(notification_id) is None:
      return False
    self._storage.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
    return True

  def unread_count(self) -> int:
    row = self._storage.fetchone("SELECT COUNT(*) FROM notifications WHERE read = 0")
    return int(row[0]) if row else 0

  @staticmethod
  def _row_to_notification(row: tuple) -> Notification:
    return Notification(
      id=str(row[0]),
      type=str(row[1]),
      title=str(row[2]),
      body=str(row[3] or ""),
      created_at=_from_iso(str(row[4])),
      read=bool(row[5]),
    )


class AutomationRunRepository:
  """History for the automations page: what ran, when, and what it said."""

  def __init__(self, storage: Storage) -> None:
    self._storage = storage

  def record(
    self,
    automation_id: str,
    *,
    status: str,
    duration_ms: int = 0,
    output: str = "",
  ) -> AutomationRun:
    run = AutomationRun(
      id=str(uuid.uuid4()),
      automation_id=automation_id,
      ran_at=_utc_now(),
      status=status,
      duration_ms=duration_ms,
      output=output,
    )
    self._storage.execute(
      """
      INSERT INTO automation_runs (id, automation_id, ran_at, status, duration_ms, output)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      (run.id, run.automation_id, _to_iso(run.ran_at), run.status, run.duration_ms, run.output),
    )
    column = "failure_count" if status == "failed" else "run_count"
    self._storage.execute(
      f"UPDATE automations SET {column} = {column} + 1 WHERE id = ?",
      (automation_id,),
    )
    return run

  def list_runs(self, automation_id: str | None = None, *, limit: int = 50) -> list[AutomationRun]:
    if automation_id:
      rows = self._storage.fetchall(
        """
        SELECT id, automation_id, ran_at, status, duration_ms, output
        FROM automation_runs
        WHERE automation_id = ?
        ORDER BY ran_at DESC
        LIMIT ?
        """,
        (automation_id, limit),
      )
    else:
      rows = self._storage.fetchall(
        """
        SELECT id, automation_id, ran_at, status, duration_ms, output
        FROM automation_runs
        ORDER BY ran_at DESC
        LIMIT ?
        """,
        (limit,),
      )
    return [
      AutomationRun(
        id=str(row[0]),
        automation_id=str(row[1]),
        ran_at=_from_iso(str(row[2])),
        status=str(row[3]),
        duration_ms=int(row[4] or 0),
        output=str(row[5] or ""),
      )
      for row in rows
    ]

  def counts(self, automation_id: str) -> tuple[int, int]:
    row = self._storage.fetchone(
      "SELECT run_count, failure_count FROM automations WHERE id = ?",
      (automation_id,),
    )
    if row is None:
      return (0, 0)
    return (int(row[0] or 0), int(row[1] or 0))
