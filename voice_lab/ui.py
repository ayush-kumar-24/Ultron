"""Simple PySide6 side-by-side Voice Lab UI (standalone, not in main Maira)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
  QApplication,
  QComboBox,
  QHBoxLayout,
  QLabel,
  QMainWindow,
  QMessageBox,
  QPushButton,
  QScrollArea,
  QVBoxLayout,
  QWidget,
)

from voice_lab import config
from voice_lab.benchmark import load_results
from voice_lab.runner import run_comparison

_PROVIDER_LABELS = {
  "kokoro": "Kokoro (default)",
  "indic_parler": "Indic Parler (Divya)",
  "veena": "Veena (kavya)",
  "chatterbox": "Chatterbox",
}


class GenerateWorker(QThread):
  finished_ok = Signal(object)
  failed = Signal(str)

  def __init__(self, scripts: list[str]) -> None:
    super().__init__()
    self._scripts = scripts

  def run(self) -> None:
    try:
      results = run_comparison(scripts=self._scripts)
      self.finished_ok.emit(results)
    except Exception as exc:  # noqa: BLE001
      self.failed.emit(str(exc))


class VoiceLabWindow(QMainWindow):
  def __init__(self) -> None:
    super().__init__()
    self.setWindowTitle("Maira Voice Lab")
    self.resize(780, 640)
    self._player = QMediaPlayer(self)
    self._audio = QAudioOutput(self)
    self._player.setAudioOutput(self._audio)
    self._queue: list[Path] = []
    self._worker: GenerateWorker | None = None
    self._player.mediaStatusChanged.connect(self._on_media_status)
    self._build_ui()
    self._refresh_stats()

  def _build_ui(self) -> None:
    outer = QWidget()
    self.setCentralWidget(outer)
    shell = QVBoxLayout(outer)
    shell.setContentsMargins(0, 0, 0, 0)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    shell.addWidget(scroll)

    root = QWidget()
    scroll.setWidget(root)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)

    title = QLabel("MAIRA VOICE LAB")
    title.setStyleSheet("font-size: 22px; font-weight: 700;")
    layout.addWidget(title)

    script_row = QHBoxLayout()
    script_row.addWidget(QLabel("Test Script"))
    self._script = QComboBox()
    self._script.addItem("English", "english")
    self._script.addItem("Hindi", "hindi")
    self._script.addItem("Hinglish", "hinglish")
    self._script.currentIndexChanged.connect(self._refresh_stats)
    script_row.addWidget(self._script, stretch=1)
    layout.addLayout(script_row)

    play_row = QHBoxLayout()
    self._play_buttons = {}
    for name in config.LAB_PROVIDERS:
      label = f"Play {_PROVIDER_LABELS.get(name, name)}"
      button = QPushButton(label)
      button.clicked.connect(lambda checked=False, n=name: self._play_provider(n))
      self._play_buttons[name] = button
      play_row.addWidget(button)
    layout.addLayout(play_row)

    self._stat_labels: dict[str, QLabel] = {}
    for name in config.LAB_PROVIDERS:
      box = QVBoxLayout()
      heading = QLabel(_PROVIDER_LABELS.get(name, name))
      heading.setStyleSheet("font-weight: 600; font-size: 14px;")
      stats = QLabel("Latency: —\nStatus: —")
      stats.setWordWrap(True)
      box.addWidget(heading)
      box.addWidget(stats)
      layout.addLayout(box)
      self._stat_labels[name] = stats

    action_row = QHBoxLayout()
    self._generate_btn = QPushButton("Generate All")
    self._generate_btn.clicked.connect(self._generate_all)
    action_row.addWidget(self._generate_btn)

    play_all = QPushButton("Play All Sequentially")
    play_all.clicked.connect(self._play_all)
    action_row.addWidget(play_all)

    open_folder = QPushButton("Open Output Folder")
    open_folder.clicked.connect(self._open_output)
    action_row.addWidget(open_folder)
    layout.addLayout(action_row)

    self._status = QLabel("Ready. Generate All runs English + Hindi + Hinglish for every available provider.")
    self._status.setWordWrap(True)
    layout.addWidget(self._status)
    layout.addStretch(1)

  def _script_id(self) -> str:
    return str(self._script.currentData())

  def _audio_path(self, provider: str) -> Path:
    return config.OUTPUT_DIR / f"{provider}_{self._script_id()}.wav"

  def _refresh_stats(self) -> None:
    results = load_results(config.RESULTS_PATH)
    script_id = self._script_id()
    script_block = results.get("scripts", {}).get(script_id, {})
    for name, label in self._stat_labels.items():
      payload = script_block.get(name) or results.get(name) or {}
      status = payload.get("status", "not generated")
      latency = payload.get("latency_seconds")
      error = payload.get("error")
      latency_text = f"{latency}s" if latency is not None else "—"
      status_text = status if not error else f"{status}: {error}"
      label.setText(f"Latency: {latency_text}\nStatus: {status_text}")
      path = self._audio_path(name)
      self._play_buttons[name].setEnabled(path.exists())

  def _generate_all(self) -> None:
    if self._worker and self._worker.isRunning():
      return
    self._generate_btn.setEnabled(False)
    self._status.setText("Generating all providers x english/hindi/hinglish… (large models may take a while)")
    self._worker = GenerateWorker(list(config.SCRIPTS.keys()))
    self._worker.finished_ok.connect(self._on_generate_done)
    self._worker.failed.connect(self._on_generate_failed)
    self._worker.start()

  def _on_generate_done(self, _results: object) -> None:
    self._generate_btn.setEnabled(True)
    self._status.setText(f"Generation complete. Results: {config.RESULTS_PATH}")
    self._refresh_stats()

  def _on_generate_failed(self, message: str) -> None:
    self._generate_btn.setEnabled(True)
    self._status.setText(f"Generation failed: {message}")
    QMessageBox.warning(self, "Voice Lab", message)

  def _play_provider(self, name: str) -> None:
    path = self._audio_path(name)
    if not path.exists():
      QMessageBox.information(self, "Voice Lab", f"Missing file: {path.name}\nRun Generate All first.")
      return
    self._queue = []
    self._play_file(path)

  def _play_all(self) -> None:
    paths = [self._audio_path(n) for n in config.LAB_PROVIDERS]
    existing = [p for p in paths if p.exists()]
    if not existing:
      QMessageBox.information(self, "Voice Lab", "No audio files found. Run Generate All first.")
      return
    self._queue = existing[1:]
    self._play_file(existing[0])

  def _play_file(self, path: Path) -> None:
    self._status.setText(f"Playing {path.name}")
    self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
    self._player.play()

  def _on_media_status(self, status) -> None:
    from PySide6.QtMultimedia import QMediaPlayer

    if status == QMediaPlayer.MediaStatus.EndOfMedia and self._queue:
      nxt = self._queue.pop(0)
      self._play_file(nxt)

  def _open_output(self) -> None:
    config.ensure_output_dir()
    folder = str(config.OUTPUT_DIR.resolve())
    if sys.platform.startswith("win"):
      subprocess.Popen(["explorer", folder])
    elif sys.platform == "darwin":
      subprocess.Popen(["open", folder])
    else:
      subprocess.Popen(["xdg-open", folder])


def launch_ui() -> int:
  app = QApplication.instance() or QApplication(sys.argv)
  window = VoiceLabWindow()
  window.show()
  return app.exec()


if __name__ == "__main__":
  raise SystemExit(launch_ui())
