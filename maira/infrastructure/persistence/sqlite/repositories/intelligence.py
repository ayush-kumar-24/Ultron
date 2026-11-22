"""SQLite repositories for research sessions, agent executions and work sessions."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from maira.core.interfaces.storage import Storage


def _now() -> datetime:
  return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
  if value.tzinfo is None:
    value = value.replace(tzinfo=timezone.utc)
  return value.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
  if not value:
    return None
  parsed = datetime.fromisoformat(value)
  return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass
class ResearchSession:
  id: str
  query: str
  status: str  # running | done | failed
  step: int
  sources: int
  project_id: str | None
  report: dict[str, Any] | None
  error: str | None
  created_at: datetime
  updated_at: datetime


@dataclass
class AgentExecution:
  id: str
  agent_id: str
  task: str
  status: str  # running | done | failed
  started_at: datetime
  ended_at: datetime | None = None
  duration_ms: int = 0
  error: str | None = None


@dataclass
class WorkSession:
  id: str
  type: str  # work | learning
  project: str
  started_at: datetime
  minutes: int
  recorded: bool = False
  summary: str = ""
  extra: dict[str, Any] = field(default_factory=dict)


class ResearchRepository:
  _COLUMNS = "id, query, status, step, sources, project_id, report, error, created_at, updated_at"

  def __init__(self, storage: Storage) -> None:
    self._storage = storage

  def create(self, query: str, *, project_id: str | None = None) -> ResearchSession:
    now = _now()
    session = ResearchSession(
      id=str(uuid.uuid4()), query=query, status="running", step=0, sources=0,
      project_id=project_id, report=None, error=None, created_at=now, updated_at=now,
    )
    self._storage.execute(
      f"INSERT INTO research_sessions ({self._COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
      (session.id, query, "running", 0, 0, project_id, _iso(now), _iso(now)),
    )
    return session

  def get(self, session_id: str) -> ResearchSession | None:
    row = self._storage.fetchone(
      f"SELECT {self._COLUMNS} FROM research_sessions WHERE id = ?", (session_id,)
    )
    return self._row(row) if row else None

  def list_sessions(self, *, project_id: str | None = None, limit: int = 100) -> list[ResearchSession]:
    if project_id:
      rows = self._storage.fetchall(
        f"SELECT {self._COLUMNS} FROM research_sessions WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
        (project_id, limit),
      )
    else:
      rows = self._storage.fetchall(
        f"SELECT {self._COLUMNS} FROM research_sessions ORDER BY created_at DESC LIMIT ?", (limit,)
      )
    return [self._row(row) for row in rows]

  def progress(self, session_id: str, *, step: int, sources: int) -> None:
    self._storage.execute(
      "UPDATE research_sessions SET step = ?, sources = ?, updated_at = ? WHERE id = ?",
      (step, sources, _iso(_now()), session_id),
    )

  def finish(self, session_id: str, report: dict[str, Any], *, step: int, sources: int) -> None:
    self._storage.execute(
      "UPDATE research_sessions SET status = 'done', step = ?, sources = ?, report = ?, error = NULL, "
      "updated_at = ? WHERE id = ?",
      (step, sources, json.dumps(report, ensure_ascii=False), _iso(_now()), session_id),
    )

  def fail(self, session_id: str, error: str) -> None:
    self._storage.execute(
      "UPDATE research_sessions SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
      (error, _iso(_now()), session_id),
    )

  def fail_interrupted(self) -> int:
    """Sessions left 'running' by a previous process can never finish - say so."""
    row = self._storage.fetchone("SELECT COUNT(*) FROM research_sessions WHERE status = 'running'")
    self._storage.execute(
      "UPDATE research_sessions SET status = 'failed', error = ?, updated_at = ? WHERE status = 'running'",
      ("Ultron was closed before this research finished.", _iso(_now())),
    )
    return int(row[0]) if row else 0

  def delete(self, session_id: str) -> bool:
    if self.get(session_id) is None:
      return False
    self._storage.execute("DELETE FROM research_sessions WHERE id = ?", (session_id,))
    return True

  def count(self) -> int:
    row = self._storage.fetchone("SELECT COUNT(*) FROM research_sessions")
    return int(row[0]) if row else 0

  @staticmethod
  def _row(row: tuple) -> ResearchSession:
    report = None
    if row[6]:
      try:
        report = json.loads(row[6])
      except (TypeError, ValueError):
        report = None
    return ResearchSession(
      id=str(row[0]), query=str(row[1]), status=str(row[2]), step=int(row[3] or 0),
      sources=int(row[4] or 0), project_id=row[5], report=report, error=row[7],
      created_at=_parse(row[8]) or _now(), updated_at=_parse(row[9]) or _now(),
    )


class AgentExecutionRepository:
  _COLUMNS = "id, agent_id, task, status, started_at, ended_at, duration_ms, error"

  def __init__(self, storage: Storage) -> None:
    self._storage = storage

  def start(self, agent_id: str, task: str) -> AgentExecution:
    execution = AgentExecution(
      id=str(uuid.uuid4()), agent_id=agent_id, task=task[:300], status="running", started_at=_now()
    )
    self._storage.execute(
      f"INSERT INTO agent_executions ({self._COLUMNS}) VALUES (?, ?, ?, 'running', ?, NULL, 0, NULL)",
      (execution.id, agent_id, execution.task, _iso(execution.started_at)),
    )
    return execution

  def finish(self, execution_id: str, *, ok: bool, error: str | None = None) -> None:
    row = self._storage.fetchone(
      "SELECT started_at FROM agent_executions WHERE id = ?", (execution_id,)
    )
    if row is None:
      return
    ended = _now()
    started = _parse(row[0]) or ended
    self._storage.execute(
      "UPDATE agent_executions SET status = ?, ended_at = ?, duration_ms = ?, error = ? WHERE id = ?",
      (
        "done" if ok else "failed",
        _iso(ended),
        max(0, int((ended - started).total_seconds() * 1000)),
        None if ok else (error or "Failed")[:500],
        execution_id,
      ),
    )

  def fail_interrupted(self) -> None:
    self._storage.execute(
      "UPDATE agent_executions SET status = 'failed', error = ?, ended_at = started_at WHERE status = 'running'",
      ("Ultron was closed before this finished.",),
    )

  def list_executions(self, agent_id: str | None = None, *, limit: int = 50) -> list[AgentExecution]:
    if agent_id:
      rows = self._storage.fetchall(
        f"SELECT {self._COLUMNS} FROM agent_executions WHERE agent_id = ? ORDER BY started_at DESC LIMIT ?",
        (agent_id, limit),
      )
    else:
      rows = self._storage.fetchall(
        f"SELECT {self._COLUMNS} FROM agent_executions ORDER BY started_at DESC LIMIT ?", (limit,)
      )
    return [self._row(row) for row in rows]

  def stats(self, agent_id: str) -> tuple[int, datetime | None]:
    row = self._storage.fetchone(
      "SELECT COUNT(*), MAX(started_at) FROM agent_executions WHERE agent_id = ?", (agent_id,)
    )
    if row is None:
      return 0, None
    return int(row[0] or 0), _parse(row[1])

  @staticmethod
  def _row(row: tuple) -> AgentExecution:
    return AgentExecution(
      id=str(row[0]), agent_id=str(row[1]), task=str(row[2]), status=str(row[3]),
      started_at=_parse(row[4]) or _now(), ended_at=_parse(row[5]),
      duration_ms=int(row[6] or 0), error=row[7],
    )


class WorkSessionRepository:
  _COLUMNS = "id, type, project, started_at, minutes, recorded, summary"

  def __init__(self, storage: Storage) -> None:
    self._storage = storage

  def record(
    self,
    *,
    type: str = "work",
    project: str = "",
    minutes: int,
    summary: str = "",
    started_at: datetime | None = None,
    recorded: bool = False,
  ) -> WorkSession:
    session = WorkSession(
      id=str(uuid.uuid4()),
      type=type if type in {"work", "learning"} else "work",
      project=project[:120],
      started_at=started_at or _now(),
      minutes=max(0, int(minutes)),
      recorded=recorded,
      summary=summary[:300],
    )
    self._storage.execute(
      f"INSERT INTO work_sessions ({self._COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
      (
        session.id, session.type, session.project, _iso(session.started_at),
        session.minutes, 1 if recorded else 0, session.summary,
      ),
    )
    return session

  def list_sessions(self, *, limit: int = 200) -> list[WorkSession]:
    rows = self._storage.fetchall(
      f"SELECT {self._COLUMNS} FROM work_sessions ORDER BY started_at DESC LIMIT ?", (limit,)
    )
    return [
      WorkSession(
        id=str(r[0]), type=str(r[1]), project=str(r[2] or ""), started_at=_parse(r[3]) or _now(),
        minutes=int(r[4] or 0), recorded=bool(r[5]), summary=str(r[6] or ""),
      )
      for r in rows
    ]
