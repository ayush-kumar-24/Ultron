"""Run a skill's own script — only after the user says yes, never through a shell."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_RUN_BLOCK = re.compile(r"```run[ \t]*\r?\n(.+?)\r?\n?```", re.DOTALL)
_SHELL_BLOCK = re.compile(r"```(?:bash|sh|shell|console|powershell|ps1|cmd|bat)?[ \t]*\r?\n(.+?)\r?\n?```", re.DOTALL)
_SAFE_FLAGS = {"-u", "-B"}  # anything else (-c, -m, -e, --eval, -Command …) could run inline code
_PYTHON = {"python", "python3", "py", "python.exe", "python3.exe", "py.exe"}
_NODE = {"node", "node.exe"}
_SHELLS = {"bash", "sh", "bash.exe", "sh.exe"}
_POWERSHELL = {"powershell", "pwsh", "powershell.exe", "pwsh.exe"}
MAX_OUTPUT = 6000


class RunError(ValueError):
  """The command is not allowed or cannot run on this PC."""


@dataclass(frozen=True)
class RunPlan:
  argv: list[str]
  script: str  # relative to the skill folder
  display: str  # what the user approves


@dataclass(frozen=True)
class RunResult:
  code: int
  output: str
  seconds: float
  timed_out: bool = False

  @property
  def ok(self) -> bool:
    return self.code == 0 and not self.timed_out


def extract_command(reply: str, scripts: list[str]) -> str | None:
  """The command in a ```run block, or a one-line shell block that runs one of the skill's scripts."""
  match = _RUN_BLOCK.search(reply)
  if match:
    lines = [ln.strip() for ln in match.group(1).splitlines() if ln.strip() and not ln.strip().startswith("#")]
    return lines[0] if lines else None
  names = {Path(s).name for s in scripts}
  for block in _SHELL_BLOCK.finditer(reply):
    lines = [ln.strip().lstrip("$> ").strip() for ln in block.group(1).splitlines() if ln.strip()]
    if len(lines) == 1 and any(name in lines[0] for name in names):
      return lines[0]
  return None


def _python() -> str:
  exe = Path(sys.executable)
  if exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
    return str(exe.with_name("python.exe"))  # pythonw has no console output
  return str(exe)


def _which(*names: str) -> str:
  for name in names:
    found = shutil.which(name)
    if found:
      return found
  raise RunError(f"{names[0]} is not installed on this PC.")


def _interpreter_for(script: Path, python: str | None = None) -> list[str]:
  suffix = script.suffix.lower()
  if suffix == ".py":
    return [python or _python()]
  if suffix in (".js", ".mjs", ".cjs"):
    return [_which("node")]
  if suffix == ".ts":
    return [_which("tsx", "ts-node")]
  if suffix in (".sh", ".bash"):
    return [_which("bash", "sh")]
  if suffix == ".ps1":
    return [_which("pwsh", "powershell"), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
  if suffix in (".bat", ".cmd"):
    if os.name != "nt":
      raise RunError("Batch files only run on Windows.")
    return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c"]
  if suffix == ".rb":
    return [_which("ruby")]
  if suffix == ".pl":
    return [_which("perl")]
  raise RunError(f"Don't know how to run {script.name}.")


def plan_run(command: str, skill_dir: Path, scripts: list[str], *, python: str | None = None) -> RunPlan:
  """Check that the command runs one of this skill's scripts, and build argv (no shell)."""
  try:
    parts = shlex.split(command.replace("\\", "/"))
  except ValueError as exc:
    raise RunError(f"Can't read that command: {exc}") from exc
  if not parts:
    raise RunError("Empty command.")
  if any(ch in command for ch in ("|", "&&", ";", "`", "$(", ">")):
    raise RunError("Only a single script can run (no pipes, redirects or chained commands).")

  first = Path(parts[0]).name.lower()
  args = parts[1:]
  if first in _PYTHON | _NODE | _SHELLS | _POWERSHELL:
    while args and args[0].startswith("-"):
      if args[0] not in _SAFE_FLAGS:
        raise RunError("Only a script file of this skill can run (no interpreter options or inline code).")
      args = args[1:]
    if not args:
      raise RunError("No script in that command.")
    script_arg, rest = args[0], args[1:]
  else:
    script_arg, rest = parts[0], args

  root = skill_dir.resolve()
  script = (root / script_arg).resolve()
  if not script.is_relative_to(root) or not script.is_file():
    raise RunError(f"{script_arg} is not a script of this skill.")
  rel = script.relative_to(root).as_posix()
  if rel not in scripts:
    raise RunError(f"{rel} is not one of this skill's scripts.")

  argv = [*_interpreter_for(script, python), str(script), *rest]
  shown = " ".join(shlex.quote(a) for a in rest)
  return RunPlan(argv=argv, script=rel, display=f"{Path(argv[0]).stem} {rel} {shown}".strip())


def execute(plan: RunPlan, *, cwd: Path, timeout: int) -> RunResult:
  cwd.mkdir(parents=True, exist_ok=True)
  env = dict(os.environ)
  env["PYTHONIOENCODING"] = "utf-8"
  env["PYTHONUNBUFFERED"] = "1"
  flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
  started = time.monotonic()
  try:
    done = subprocess.run(
      plan.argv,
      cwd=str(cwd),
      env=env,
      stdin=subprocess.DEVNULL,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      timeout=timeout,
      creationflags=flags,
      check=False,
    )
    output = done.stdout.decode("utf-8", errors="replace")
    code, timed_out = done.returncode, False
  except subprocess.TimeoutExpired as exc:
    output = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else ""
    code, timed_out = -1, True
  except OSError as exc:
    output, code, timed_out = f"Could not start: {exc}", -1, False
  if len(output) > MAX_OUTPUT:
    half = MAX_OUTPUT // 2
    output = output[:half] + "\n…(output shortened)…\n" + output[-half:]
  return RunResult(code=code, output=output.strip(), seconds=round(time.monotonic() - started, 1), timed_out=timed_out)


def missing_module(output: str) -> str | None:
  match = re.search(r"No module named '([\w.]+)'", output)
  return match.group(1).split(".")[0] if match else None
