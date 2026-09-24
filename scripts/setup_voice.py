"""Install a high-quality voice into its own Python environment.

  python -m scripts.setup_voice chatterbox      # Resemble AI Chatterbox Multilingual (MIT)
  python -m scripts.setup_voice indic_parler    # AI4Bharat Indic Parler-TTS (Apache 2.0)

Each voice pins library versions that clash with the others (and with the
app), so each gets voice_envs/<name>. An NVIDIA GPU is used automatically
when present (CUDA build of PyTorch); otherwise it runs on the CPU (slower).
The model itself (a few GB) downloads on first use and is then cached.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time

from maira.infrastructure.speech.worker.engine import voice_env_dir, voice_env_python

TORCH_VERSIONS = {"chatterbox": ("torch==2.6.0", "torchaudio==2.6.0"), "indic_parler": ("torch", "torchaudio")}
PACKAGES = {
  "chatterbox": ["chatterbox-tts"],
  "indic_parler": ["git+https://github.com/huggingface/parler-tts.git", "sentencepiece"],
}
CUDA_INDEX = "https://download.pytorch.org/whl/cu124"


def has_nvidia_gpu() -> bool:
  if shutil.which("nvidia-smi") is None:
    return False
  try:
    return subprocess.run(["nvidia-smi", "-L"], capture_output=True, timeout=20).returncode == 0
  except (OSError, subprocess.TimeoutExpired):
    return False


def run(cmd: list[str]) -> None:
  print("  $", " ".join(cmd), flush=True)
  subprocess.run(cmd, check=True)


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("voice", choices=sorted(PACKAGES))
  parser.add_argument("--cpu", action="store_true", help="install the CPU build even if a GPU is present")
  parser.add_argument("--recreate", action="store_true", help="delete and rebuild the environment")
  args = parser.parse_args()

  env_dir, python = voice_env_dir(args.voice), voice_env_python(args.voice)
  gpu = has_nvidia_gpu() and not args.cpu
  print(f"Voice: {args.voice}   environment: {env_dir}   device: {'NVIDIA GPU' if gpu else 'CPU'}")

  if args.recreate and env_dir.exists():
    shutil.rmtree(env_dir)
  if not python.exists():
    print("1/4 Creating environment...")
    run([sys.executable, "-m", "venv", str(env_dir)])
  pip = [str(python), "-m", "pip", "install", "--upgrade"]
  print("2/4 Updating pip...")
  run(pip + ["pip", "wheel", "setuptools"])
  print("3/4 Installing PyTorch...")
  torch_pkgs = list(TORCH_VERSIONS[args.voice])
  run(pip + torch_pkgs + (["--index-url", CUDA_INDEX] if gpu else []))
  print(f"4/4 Installing {args.voice} (can take several minutes)...")
  run(pip + PACKAGES[args.voice] + ["numpy"])

  print("\nInstalled. Loading the model once (downloads a few GB the first time)...")
  from maira.infrastructure.speech.worker.engine import WorkerTTSEngine  # noqa: PLC0415

  engine = WorkerTTSEngine(args.voice, options={"device": "cuda" if gpu else "cpu"})
  started = time.time()
  try:
    engine.warm_up()
    audio = engine.synthesize("Hello, main Ultron hoon.")[0]
    print(f"OK: voice ready on {engine.device}, test sentence {len(audio) / engine.sample_rate:.1f}s "
          f"of audio (took {time.time() - started:.0f}s including model load).")
  finally:
    engine.close()
  print(f"\nNext: set it in data\\config.yaml:\n  voice:\n    tts:\n      provider: {args.voice}\n"
        f"Then listen:  python -m scripts.test_voice --provider {args.voice}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
