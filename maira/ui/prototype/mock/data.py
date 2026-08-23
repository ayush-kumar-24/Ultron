"""Mock data for the standalone UI prototype."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Profile:
  name: str = "Ayush"
  avatar_initials: str = "A"
  voice: str = "Voice A"
  onboarded: bool = False


MOCK_PROFILE = Profile()

MOCK_QUICK_ACTIONS = [
  {"id": "workspace", "label": "Open my workspace", "icon": "folder"},
  {"id": "plan", "label": "Plan my day", "icon": "calendar"},
  {"id": "search", "label": "Search my files", "icon": "search"},
  {"id": "pending", "label": "What's pending?", "icon": "list"},
]

MOCK_CONVERSATION = [
  {
    "id": "m1",
    "role": "user",
    "content": "How's my day looking?",
  },
  {
    "id": "m2",
    "role": "assistant",
    "content": (
      "You have three important things planned today.\n\n"
      "Continue developing Maira,\n"
      "finish the current system testing,\n"
      "and review tomorrow's goals.\n\n"
      "I can organize these into a focused schedule if you'd like."
    ),
  },
]

MOCK_STREAM_REPLIES = [
  "I've noted that. Want me to turn it into a task or save it to memory?",
  "Done — I've organized that into a clear next step for you.",
  "Here's what I suggest: focus on the highest-leverage item first, then batch the rest.",
  "Understood. I can open your workspace or draft a short plan whenever you're ready.",
]

MOCK_MEMORIES = [
  {
    "id": "mem1",
    "title": "Working on Maira project",
    "body": "Building a personal AI operating system named Maira.",
    "category": "Projects",
    "importance": "High",
    "created": "Today",
    "tags": ["Important", "Project"],
  },
  {
    "id": "mem2",
    "title": "Prefers offline AI",
    "body": "User prefers fully local, offline-first AI experiences.",
    "category": "Preferences",
    "importance": "High",
    "created": "Yesterday",
    "tags": ["Preference"],
  },
  {
    "id": "mem3",
    "title": "Building Maira as a personal AI OS",
    "body": "Long-term goal is a second-brain companion that executes, not just answers.",
    "category": "Projects",
    "importance": "Medium",
    "created": "2 days ago",
    "tags": ["Project"],
  },
  {
    "id": "mem4",
    "title": "Prefers minimal interfaces",
    "body": "UI should stay calm, dark, and free of dashboard clutter.",
    "category": "Preferences",
    "importance": "Medium",
    "created": "3 days ago",
    "tags": ["Preference"],
  },
  {
    "id": "mem5",
    "title": "Currently testing local models",
    "body": "Evaluating Ollama models for daily offline use.",
    "category": "Important",
    "importance": "High",
    "created": "Today",
    "tags": ["Important"],
  },
]

MOCK_TASKS = [
  {"id": "t1", "title": "Build Maira memory", "section": "Today", "time": "11:00 AM", "done": False, "priority": "High"},
  {"id": "t2", "title": "Test voice system", "section": "Today", "time": "2:00 PM", "done": False, "priority": "Medium"},
  {"id": "t3", "title": "Review architecture", "section": "Upcoming", "time": "Tomorrow", "done": False, "priority": "Medium"},
  {"id": "t4", "title": "Build automation flow", "section": "Upcoming", "time": "Fri", "done": False, "priority": "Low"},
  {"id": "t5", "title": "Setup project structure", "section": "Completed", "time": "Yesterday", "done": True, "priority": "High"},
]

MOCK_NOTES = [
  {
    "id": "n1",
    "title": "Maira Architecture",
    "updated": "Today",
    "body": (
      "# Maira Architecture\n\n"
      "- Offline-first personal AI OS\n"
      "- Modular brain, memory, voice, automation\n"
      "- PySide6 desktop shell\n"
      "- Local LLM via Ollama\n"
    ),
  },
  {
    "id": "n2",
    "title": "Voice Research",
    "updated": "Yesterday",
    "body": (
      "# Voice Research\n\n"
      "Providers to evaluate:\n"
      "- Kokoro (local)\n"
      "- Sarvam\n"
      "- Chatterbox\n"
    ),
  },
  {
    "id": "n3",
    "title": "Ideas",
    "updated": "2 days ago",
    "body": "Command palette + ambient home glow as signature moments.",
  },
  {
    "id": "n4",
    "title": "Today's Thoughts",
    "updated": "Today",
    "body": "Ship the UI prototype first. Backend integration comes after approval.",
  },
]

MOCK_ACTIVITY = [
  {"id": "a1", "time": "10:42 AM", "text": "Maira opened VS Code"},
  {"id": "a2", "time": "10:39 AM", "text": 'Maira remembered: "Working on Maira project"'},
  {"id": "a3", "time": "10:12 AM", "text": "Conversation started"},
  {"id": "a4", "time": "09:05 AM", "text": "Daily briefing generated"},
  {"id": "a5", "time": "08:30 AM", "text": "Voice mode activated"},
]

MOCK_AUTOMATIONS = [
  {"id": "au1", "title": "Morning Workspace", "schedule": "Every day at 9:00 AM", "enabled": True},
  {"id": "au2", "title": "Daily Briefing", "schedule": "Every day at 9:15 AM", "enabled": True},
  {"id": "au3", "title": "Weekly Review", "schedule": "Every Sunday", "enabled": False},
]

MOCK_SETTINGS: dict[str, Any] = {
  "general": {
    "name": "Ayush",
    "theme": "Dark",
    "startup": "Open Home",
    "language": "English",
  },
  "ai": {
    "model": "llama3.2",
    "provider": "Ollama (Local)",
    "temperature": 0.7,
    "context": "8k",
  },
  "voice": {
    "provider": "Kokoro (Local) — default",
    "voice": "af_heart (female)",
    "speed": 50,
    "volume": 70,
    "auto_speak": True,
    "interrupt_on_speech": True,
    "wake_word": False,
  },
  "memory": {
    "enable": True,
    "automatic": True,
    "retention": "Forever",
  },
  "privacy": {
    "offline_mode": True,
    "data_location": "./data",
    "logs": True,
  },
  "automation": {
    "permissions": "Confirm sensitive",
    "confirmation": True,
  },
  "developer": {
    "debug": False,
    "diagnostics": False,
  },
}

MOCK_SYSTEM_STATUS = [
  {"id": "brain", "label": "Brain", "state": "Ready"},
  {"id": "memory", "label": "Memory", "state": "Ready"},
  {"id": "voice", "label": "Voice", "state": "Ready"},
  {"id": "automation", "label": "Automation", "state": "Ready"},
  {"id": "ollama", "label": "Ollama", "state": "Ready"},
]

MOCK_COMMANDS = [
  {"id": "workspace", "label": "Start my workspace", "hint": "Automation"},
  {"id": "plan", "label": "Plan my day", "hint": "Tasks"},
  {"id": "memory", "label": "Search memory", "hint": "Memory"},
  {"id": "task", "label": "Create task", "hint": "Tasks"},
  {"id": "note", "label": "Create note", "hint": "Notes"},
  {"id": "voice", "label": "Dictate (mic)", "hint": "Chat"},
  {"id": "settings", "label": "Open settings", "hint": "Settings"},
  {"id": "search", "label": "Global search", "hint": "Search"},
  {"id": "status", "label": "System status", "hint": "Status"},
  {"id": "error_demo", "label": "Show offline AI error", "hint": "Demo"},
]

MOCK_SEARCH_RESULTS = [
  {"id": "s1", "category": "Conversations", "title": "How's my day looking?", "subtitle": "Chat · Today"},
  {"id": "s2", "category": "Memory", "title": "Working on Maira project", "subtitle": "Projects · High"},
  {"id": "s3", "category": "Notes", "title": "Maira Architecture", "subtitle": "Updated today"},
  {"id": "s4", "category": "Tasks", "title": "Build Maira memory", "subtitle": "Today · 11:00 AM"},
  {"id": "s5", "category": "Files", "title": "docs/VISION.md", "subtitle": "Local file"},
]

MOCK_ERRORS = {
  "ollama": {
    "title": "Maira can't reach the local AI model.",
    "body": "Make sure your local model is running.",
  },
  "model": {
    "title": "The selected model isn't available.",
    "body": "Choose another model in Settings, or install it locally.",
  },
  "voice": {
    "title": "Voice is unavailable right now.",
    "body": "Check your microphone and voice provider settings.",
  },
  "memory": {
    "title": "Memory couldn't be loaded.",
    "body": "Your memories are safe. Try again in a moment.",
  },
  "network": {
    "title": "You're offline — and that's fine.",
    "body": "Maira is built for local use. Core features still work.",
  },
  "general": {
    "title": "Something went wrong.",
    "body": "Try again. If it keeps happening, check Diagnostics.",
  },
}


def clone_defaults() -> dict[str, Any]:
  return {
    "profile": deepcopy(MOCK_PROFILE.__dict__),
    "conversation": deepcopy(MOCK_CONVERSATION),
    "memories": deepcopy(MOCK_MEMORIES),
    "tasks": deepcopy(MOCK_TASKS),
    "notes": deepcopy(MOCK_NOTES),
    "activity": deepcopy(MOCK_ACTIVITY),
    "automations": deepcopy(MOCK_AUTOMATIONS),
    "settings": deepcopy(MOCK_SETTINGS),
    "status": deepcopy(MOCK_SYSTEM_STATUS),
  }
