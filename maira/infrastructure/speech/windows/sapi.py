"""Speak with the voice that ships with Windows (System.Speech via PowerShell).

Used for announcements such as the daily briefing when the Kokoro voice
model is not installed. Runs in a separate process, so it cannot clash with
Qt and never blocks the app.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading

from loguru import logger

# Text arrives on stdin, so quotes or symbols in it cannot break the command.
# Prefers an Indian English / Hindi voice when Windows has one installed.
_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$v = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -in @('en-IN','hi-IN') } | Select-Object -First 1
if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }
$s.Rate = 0
$s.Speak([Console]::In.ReadToEnd())
"""


class WindowsSpeech:
  def __init__(self, *, executable: str | None = None, supported: bool | None = None) -> None:
    self._supported = (os.name == "nt") if supported is None else supported
    self._executable = executable or shutil.which("powershell") or shutil.which("pwsh")
    self._lock = threading.Lock()
    self._process: subprocess.Popen | None = None

  def is_available(self) -> bool:
    return self._supported and self._executable is not None

  def speak(self, text: str) -> bool:
    """Start speaking in the background. Returns False if it could not start."""
    if not text.strip() or not self.is_available():
      return False
    with self._lock:
      self.stop()
      try:
        self._process = subprocess.Popen(  # noqa: S603
          [self._executable, "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
          stdin=subprocess.PIPE,
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
          text=True,
          encoding="utf-8",
          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert self._process.stdin is not None
        self._process.stdin.write(text)
        self._process.stdin.close()
      except (OSError, ValueError):
        logger.exception("Windows speech failed to start")
        self._process = None
        return False
    logger.info("Speaking with the Windows voice ({} chars)", len(text))
    return True

  def stop(self) -> None:
    process = self._process
    self._process = None
    if process is not None and process.poll() is None:
      process.kill()
