"""Notes submodule — note CRUD helpers."""

from maira.core.domain.entities import Note
from maira.infrastructure.persistence.sqlite.repositories import NoteRepository


class NotesService:
  def __init__(self, repository: NoteRepository) -> None:
    self._repo = repository

  def list_notes(self) -> list[Note]:
    return self._repo.list_notes()

  def add_note(self, title: str, body: str = "") -> Note:
    return self._repo.create(title, body)

  def update_note(self, note_id: str, *, title: str, body: str) -> Note | None:
    return self._repo.update(note_id, title=title, body=body)

  def delete_note(self, note_id: str) -> None:
    self._repo.delete(note_id)

  def get_note(self, note_id: str) -> Note | None:
    return self._repo.get(note_id)
