"""Infrastructure layer — adapters for external systems and I/O.

Implements core port interfaces using concrete libraries (SQLite, ChromaDB,
Ollama, Whisper, Kokoro, PyAutoGUI, Playwright, Loguru). Swappable
without changing module or UI code.
"""
