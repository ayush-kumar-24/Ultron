# Ultron

Offline-first personal AI operating system for Windows (Python / PySide6 + Ollama).

Formerly developed as Maira — product name is now **Ultron**.

## Quick start

```bash
cd Ultron   # or your local folder
python -m maira
```

Requires [Ollama](https://ollama.com) with `llama3.2:latest`.

Optional extras:

```bash
pip install -e ".[voice]"
pip install -e ".[desktop]"
```

## What works today

- **Chat** — local LLM (Hinglish-friendly companion prompt)
- **Dictate** — Chat mic / Alt+V / hold Ctrl+Shift+V (speech → text, no TTS required)
- **Tasks & notes from chat or voice** — `add task pay bill tomorrow`, `task: call mom at 6pm urgent`, `what's pending`, `aaj ke tasks`, `done 2`, `pay bill ho gaya`, `delete task milk`, `note: call Rahul about project`
- **Tasks + reminders together** — a task with a time (`add task call mom at 6pm`) reminds you then; **Done** on that pop-up completes the task; finishing or deleting the task cancels its reminder; unfinished tasks from earlier days move to today. Settings under `tasks:`.
- **Home = your day at a glance** — today's tasks (overdue first), upcoming reminders and recent notes, updated live; buttons: Plan my day · What's pending? · Add a task · Set a reminder. Activity shows what really happened; Ctrl+F searches your tasks, notes and memory.
- **Daily briefing** — every morning (default 8:00) Ultron posts today's plan in chat, shows a notification and speaks a short summary: overdue items, today's tasks, reminders, and what to do first. Ask any time: `plan my day`, `aaj ka plan`. Set the time and your name under `briefing:` in the config.
- **Automations** — schedule from chat (`remind me in 2 minutes`, `open youtube at 9pm`)
- **Runs in the background** — closing the window hides Ultron to the system tray; reminders keep firing. Quit from the tray menu.
- **Reminder pop-ups** — Windows notifications with **Done** / **Snooze** (10 min) buttons; missed reminders say when they were due
- **Desktop control** — short commands (`play teri deewani`, `open notepad and type hello`)

## Background mode

- **Start with Windows:** right-click the tray icon → *Start with Windows*. Ultron then starts hidden in the tray when you sign in.
- **Launch without a console:** double-click `ultron.pyw` (or run `pythonw ultron.pyw --background` to start hidden).
- Only one Ultron runs at a time; launching it again just brings the window forward.
- Settings live under `background:` and `notifications:` in `config/default.yaml` (override in `data/config.yaml`).

## Voice docs

- [docs/VOICE_ARCHITECTURE.md](docs/VOICE_ARCHITECTURE.md)
- [docs/VOICE_SETUP.md](docs/VOICE_SETUP.md)
- [docs/VOICE_LATENCY.md](docs/VOICE_LATENCY.md)
- [docs/MEMORY_ARCHITECTURE.md](docs/MEMORY_ARCHITECTURE.md)
- [docs/PHASE2_MANUAL_TEST.md](docs/PHASE2_MANUAL_TEST.md)

## Live voice bench

```bash
python -m scripts.benchmark_voice_live
```
