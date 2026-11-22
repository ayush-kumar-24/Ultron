"""Describe Ultron's real services as agents. One place, so the list cannot drift."""

from __future__ import annotations

from maira.modules.orchestration.registry import AgentRegistry, AgentSpec


def subscribe_activity(registry: AgentRegistry, bus, memory=None) -> None:
  """Count work done through chat and voice, not only through the Agents page."""

  def on(topic: str, handler) -> None:
    def safe(payload) -> None:
      try:
        handler(payload if isinstance(payload, dict) else {})
      except Exception:  # noqa: BLE001 - bookkeeping must never break the sender
        pass

    bus.subscribe(topic, safe)

  def short(text: object, limit: int = 120) -> str:
    return " ".join(str(text or "").split())[:limit]

  on("agent.ran", lambda p: registry.record(
    "action", short(p.get("goal")), ok=bool(p.get("ok")), error=None if p.get("ok") else short(p.get("message"), 300)
  ))
  on("desktop.ran", lambda p: registry.record(
    "system", short(p.get("message")) or "Desktop action", ok=p.get("ok") is not False,
    error=None if p.get("ok") is not False else short(p.get("message"), 300),
  ))
  on("skill.used", lambda p: registry.record("skills", f"Used /{p.get('name', 'skill')}", ok=True))
  on("planner.changed", lambda p: registry.record(
    "planning", {"chat": "Updated tasks from chat", "reminder": "Completed a task from its reminder",
                 "roll_over": "Moved unfinished tasks to today"}[p["reason"]], ok=True,
  ) if p.get("reason") in {"chat", "reminder", "roll_over"} else None)
  on("automation.changed", lambda p: registry.record("automation", "Scheduled from chat", ok=True)
     if p.get("reason") in {"chat", "created"} else None)
  on("screen.read", lambda p: registry.record("vision", "Read the screen", ok=True))
  on("screen.error", lambda p: registry.record("vision", "Read the screen", ok=False, error=short(p.get("message"), 300)))

  if memory is not None and hasattr(memory, "on_store"):
    memory.on_store = lambda entry: registry.record("memory", f"Saved: {short(entry.title or entry.body, 80)}", ok=True)


def _always() -> tuple[bool, str]:
  return True, "ready"


def register_agents(registry: AgentRegistry, container, settings) -> None:
  def model_name() -> str:
    llm = container.try_resolve("llm")
    name = getattr(llm, "model", None) or settings.ollama.model
    return f"local · {name}"

  def llm_available() -> tuple[bool, str]:
    llm = container.try_resolve("llm")
    if llm is None:
      return False, "no model client"
    return (True, "ready") if llm.is_available() else (False, "Ollama is not running")

  def action_tools() -> list[str]:
    # Tool names come from the live agent so this always matches what it can really do.
    agent = container.try_resolve("agent")
    tools = getattr(agent, "_tools", None)
    try:
      return [tool.name for tool in tools()] if callable(tools) else []
    except Exception:  # noqa: BLE001
      return []

  def action_available() -> tuple[bool, str]:
    agent = container.try_resolve("agent")
    if agent is None or not getattr(agent, "enabled", False):
      return False, "the action agent is turned off in settings"
    ok, why = llm_available()
    if not ok:
      return ok, why
    wanted = str(getattr(agent, "model", "") or "")
    if wanted:
      # Say so plainly when the agent's model was never downloaded, instead of failing mid-job.
      try:
        from maira.modules.voice.voice_tools import ollama_models  # noqa: PLC0415

        installed = ollama_models(settings.ollama.host) or []
      except Exception:  # noqa: BLE001
        installed = []
      if installed and wanted not in installed and f"{wanted}:latest" not in installed:
        return False, f"its model {wanted} is not installed - run 'ollama pull {wanted}' or pick another in Settings > Agent"
    return True, "ready"

  def skill_names() -> list[str]:
    skills = container.try_resolve("skills")
    store = getattr(skills, "store", None)
    try:
      return [f"/{skill.name}" for skill in store.skills(enabled_only=True)][:24] if store else []
    except Exception:  # noqa: BLE001
      return []

  def skills_available() -> tuple[bool, str]:
    skills = container.try_resolve("skills")
    if skills is None or not getattr(skills, "enabled", False):
      return False, "skills are turned off in settings"
    return True, "ready"

  def service_available(key: str):
    def check() -> tuple[bool, str]:
      service = container.try_resolve(key)
      if service is None:
        return False, "not installed"
      result = service.is_available()
      if isinstance(result, tuple):
        return bool(result[0]), str(result[1])
      return (True, "ready") if result else (False, "not available on this machine")

    return check

  agent_settings = getattr(settings, "agent", None)
  agent_model = getattr(agent_settings, "model", "")

  registry.register(AgentSpec(
    "core", "Ultron Core", "Orchestrator",
    "Understands what you ask, decides which agent handles it, and checks the result.",
    lambda: ["conversation", "routing", "verification", "context"], model_name, llm_available,
  ))
  registry.register(AgentSpec(
    "action", "Action Agent", "Files, apps and messages",
    "Does jobs on this PC - files, apps, music, email and WhatsApp - and asks before anything risky.",
    action_tools, lambda: f"local · {agent_model}" if agent_model else model_name(), action_available,
    permissions=["READ", "WRITE", "EXECUTE", "ASK FIRST"],
  ))
  registry.register(AgentSpec(
    "memory", "Memory Agent", "Persistent memory",
    "Stores what matters, recalls it when relevant, and keeps it searchable.",
    lambda: ["store", "recall", "keyword search", "semantic search"], lambda: "local", _always,
    idle_status="idle",
  ))
  registry.register(AgentSpec(
    "planning", "Planning Agent", "Tasks, reminders and the daily plan",
    "Turns plain language into tasks and reminders, and lays out a realistic day.",
    lambda: ["tasks", "reminders", "plan my day", "briefing", "roll-over"], lambda: "fast path", _always,
  ))
  registry.register(AgentSpec(
    "automation", "Automation Agent", "Scheduled workflows",
    "Runs recurring jobs at their time, with the window open or closed.",
    lambda: ["schedule", "recurrence", "run now", "history"], lambda: "fast path", _always,
    idle_status="monitoring",
  ))
  registry.register(AgentSpec(
    "research", "Research Agent", "Sourced answers",
    "Searches what Ultron already holds and writes a report that says where each claim came from.",
    lambda: ["local search", "compare", "synthesise", "report"], model_name, llm_available,
    idle_status="idle",
  ))
  registry.register(AgentSpec(
    "knowledge", "Knowledge Agent", "Documents and notes",
    "Keeps your documents, summarises them, and makes them available to the other agents.",
    lambda: ["library", "summarise", "search", "save to memory"], model_name, _always,
    idle_status="idle",
  ))
  registry.register(AgentSpec(
    "skills", "Skills", "Adopted capabilities",
    "Skills installed from GitHub. Used automatically when a request matches, or with /name.",
    skill_names, model_name, skills_available, idle_status="idle",
  ))
  registry.register(AgentSpec(
    "vision", "Vision Agent", "Screen understanding",
    "Looks at the screen once, only when asked, and reads it on this device.",
    lambda: ["capture", "read text"], lambda: "Windows OCR · local", service_available("vision"),
    idle_status="idle", permissions=["ON REQUEST ONLY"],
  ))
  registry.register(AgentSpec(
    "system", "System Agent", "Desktop control",
    "Opens apps and sites, types and clicks - the instant commands that skip the model.",
    lambda: ["open app", "open url", "type", "hotkey", "click"], lambda: "fast path",
    service_available("desktop"), permissions=["EXECUTE"],
  ))
