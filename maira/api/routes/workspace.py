"""Projects, goals, and knowledge — the workspace pages."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Response

from maira.api.deps import (
  get_llm,
  get_conversations,
  get_goals,
  get_knowledge,
  get_memory,
  get_projects,
  get_tasks,
)
from maira.api.mapping import (
  conversation_to_api,
  goal_to_api,
  knowledge_to_api,
  memory_to_api,
  project_to_api,
  task_to_api,
)
from maira.api.schemas import GoalCreate, GoalPatch, KnowledgeCreate, ProjectCreate, ProjectPatch

router = APIRouter(tags=["workspace"])

SUMMARY_PROMPT = (
  "Summarise the following note in three short sentences. "
  "Plain text, no preamble.\n\n"
)


def _moment(value: str | None) -> datetime | None:
  if not value:
    return None
  try:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=f"Invalid date '{value}'") from exc
  return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# -- projects ----------------------------------------------------------------


@router.get("/projects")
def list_projects() -> list[dict]:
  tasks = get_tasks().list_tasks()
  open_by_project: dict[str, int] = {}
  for task in tasks:
    if task.project_id and task.stage != "done":
      open_by_project[task.project_id] = open_by_project.get(task.project_id, 0) + 1
  return [
    project_to_api(project, open_tasks=open_by_project.get(project.id, 0))
    for project in get_projects().list_projects()
  ]


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate) -> dict:
  if not body.name.strip():
    raise HTTPException(status_code=422, detail="A project needs a name")
  project = get_projects().create(
    body.name,
    description=body.description or "",
    color=body.color or "info",
    tags=body.tags or [],
  )
  return project_to_api(project)


@router.get("/projects/{project_id}")
def read_project(project_id: str) -> dict:
  project = get_projects().get(project_id)
  if project is None:
    raise HTTPException(status_code=404, detail="Project not found")

  tasks = [task for task in get_tasks().list_tasks() if task.project_id == project_id]
  conversations = [
    item for item in get_conversations().list_conversations() if item.project_id == project_id
  ]
  goals = [goal for goal in get_goals().list_goals() if goal.project_id == project_id]
  files = [item for item in get_knowledge().list_items() if item.project_id == project_id]
  name = project.name.lower()
  memories = [
    entry for entry in get_memory().list_memories() if name in f"{entry.title} {entry.body}".lower()
  ]

  open_tasks = sum(1 for task in tasks if task.stage != "done")
  return {
    **project_to_api(project, open_tasks=open_tasks),
    "tasks": [task_to_api(task) for task in tasks],
    "conversations": [conversation_to_api(item) for item in conversations],
    "goals": [goal_to_api(goal, project_name=project.name) for goal in goals],
    "files": [knowledge_to_api(item) for item in files],
    "memories": [memory_to_api(entry) for entry in memories[:10]],
    "research": [],
    "activity": [],
  }


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: ProjectPatch) -> dict:
  project = get_projects().update(
    project_id,
    name=body.name,
    description=body.description,
    status=body.status,
    progress=body.progress,
  )
  if project is None:
    raise HTTPException(status_code=404, detail="Project not found")
  return project_to_api(project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str) -> Response:
  if not get_projects().delete(project_id):
    raise HTTPException(status_code=404, detail="Project not found")
  return Response(status_code=204)


# -- goals -------------------------------------------------------------------


@router.get("/goals")
def list_goals() -> list[dict]:
  names = {project.id: project.name for project in get_projects().list_projects()}
  return [
    goal_to_api(goal, project_name=names.get(goal.project_id or ""))
    for goal in get_goals().list_goals()
  ]


@router.post("/goals", status_code=201)
def create_goal(body: GoalCreate) -> dict:
  if not body.title.strip():
    raise HTTPException(status_code=422, detail="A goal needs a title")
  milestones = []
  for index, item in enumerate(body.milestones or []):
    if isinstance(item, dict):
      milestones.append(item)
    else:
      milestones.append({"t": str(item), "done": False, "current": index == 0})

  goal = get_goals().create(
    body.title,
    objective=body.objective or "",
    deadline=_moment(body.deadline),
    project_id=body.projectId,
    milestones=milestones,
  )
  return goal_to_api(goal)


@router.patch("/goals/{goal_id}")
def update_goal(goal_id: str, body: GoalPatch) -> dict:
  milestones = None
  if body.milestones is not None:
    milestones = [item for item in body.milestones if isinstance(item, dict)]
  goal = get_goals().update(
    goal_id,
    title=body.title,
    objective=body.objective,
    progress=body.progress,
    milestones=milestones,
  )
  if goal is None:
    raise HTTPException(status_code=404, detail="Goal not found")
  return goal_to_api(goal)


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: str) -> Response:
  if not get_goals().delete(goal_id):
    raise HTTPException(status_code=404, detail="Goal not found")
  return Response(status_code=204)


# -- knowledge ---------------------------------------------------------------


@router.get("/knowledge")
def list_knowledge(
  type: str | None = Query(default=None),
  q: str | None = Query(default=None),
) -> list[dict]:
  items = get_knowledge().list_items()
  if type and type != "all":
    items = [item for item in items if item.type == type]
  needle = (q or "").strip().lower()
  if needle:
    items = [
      item
      for item in items
      if needle in item.title.lower()
      or needle in item.body.lower()
      or any(needle in tag.lower() for tag in item.tags)
    ]
  return [knowledge_to_api(item) for item in items]


@router.post("/knowledge", status_code=201)
def create_knowledge(body: KnowledgeCreate) -> dict:
  if not body.title.strip():
    raise HTTPException(status_code=422, detail="A knowledge item needs a title")
  item = get_knowledge().create(
    body.title,
    type=body.type or "doc",
    source=body.source or "Upload",
    body=body.body or "",
    tags=body.tags or [],
    project_id=body.projectId,
  )
  return knowledge_to_api(item)


@router.get("/knowledge/{item_id}")
def read_knowledge(item_id: str) -> dict:
  item = get_knowledge().get(item_id)
  if item is None:
    raise HTTPException(status_code=404, detail="Item not found")
  return {**knowledge_to_api(item), "body": item.body}


@router.delete("/knowledge/{item_id}", status_code=204)
def delete_knowledge(item_id: str) -> Response:
  if not get_knowledge().delete(item_id):
    raise HTTPException(status_code=404, detail="Item not found")
  return Response(status_code=204)


@router.post("/knowledge/{item_id}/summarize")
def summarize_knowledge(item_id: str) -> dict:
  """Summarise with the local model — the same brain chat uses."""
  knowledge = get_knowledge()
  item = knowledge.get(item_id)
  if item is None:
    raise HTTPException(status_code=404, detail="Item not found")
  if not item.body.strip():
    raise HTTPException(status_code=422, detail="Nothing to summarise — this item has no text")

  llm = get_llm()
  if not hasattr(llm, "chat_stream"):  # pragma: no cover - defensive
    raise HTTPException(status_code=503, detail="The local model is unavailable")

  try:
    summary = "".join(
      llm.chat_stream(
        [{"role": "user", "content": SUMMARY_PROMPT + item.body[:6000]}],
        options={"temperature": 0.2},
      )
    ).strip()
  except Exception as exc:  # noqa: BLE001 - surfaced as a clean API error
    raise HTTPException(status_code=503, detail=f"Could not summarise: {exc}") from exc

  if not summary:
    raise HTTPException(status_code=503, detail="The model returned an empty summary")

  updated = knowledge.set_summary(item_id, summary)
  return knowledge_to_api(updated or item)


@router.post("/knowledge/{item_id}/memory", status_code=201)
def knowledge_to_memory(item_id: str) -> dict:
  from maira.api.mapping import memory_category_from_api, title_from_text

  item = get_knowledge().get(item_id)
  if item is None:
    raise HTTPException(status_code=404, detail="Item not found")

  text = item.summary or item.body or item.title
  entry = get_memory().store(
    category=memory_category_from_api("learned"),
    title=title_from_text(item.title),
    body=text[:2000],
    source=f"Knowledge · {item.title}",
  )
  return memory_to_api(entry)
