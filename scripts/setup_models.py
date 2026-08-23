"""Download or verify local model assets (Ollama, Whisper, Kokoro, embeddings)."""

import argparse
import sys

from maira.app.settings import load_settings
from maira.infrastructure.llm.ollama.client import OllamaClient


def check_ollama() -> int:
  settings = load_settings()
  client = OllamaClient(
    host=settings.ollama.host,
    model=settings.ollama.model,
    timeout_seconds=settings.ollama.timeout_seconds,
  )

  if not client.is_available():
    print(f"Ollama is not reachable at {settings.ollama.host}")
    print("Install from https://ollama.com and run: ollama serve")
    return 1

  models = client.list_models()
  print(f"Ollama OK at {settings.ollama.host}")
  print(f"Configured model: {settings.ollama.model}")

  if models:
    print("Installed models:")
    for name in models:
      marker = " (configured)" if name == settings.ollama.model or name.startswith(
        f"{settings.ollama.model}:"
      ) else ""
      print(f"  - {name}{marker}")
  else:
    print("No models installed. Run: ollama pull llama3.2")
    return 1

  configured_present = any(
    name == settings.ollama.model or name.startswith(f"{settings.ollama.model}:")
    for name in models
  )
  if not configured_present:
    print(f"Configured model '{settings.ollama.model}' not found.")
    print(f"Run: ollama pull {settings.ollama.model}")
    return 1

  return 0


def check_embeddings() -> int:
  settings = load_settings()
  model_name = settings.memory.embedding_model
  try:
    from sentence_transformers import SentenceTransformer
  except ImportError:
    print("sentence-transformers is not installed.")
    print('Run: pip install -e ".[memory]"')
    return 1

  try:
    print(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)
    vector = model.encode(["hello maira"], normalize_embeddings=True)[0]
    print(f"Embedding OK ({len(vector)} dimensions)")
  except Exception as exc:  # noqa: BLE001
    print(f"Failed to load embedding model: {exc}")
    return 1

  try:
    import chromadb  # noqa: F401
  except ImportError:
    print("chromadb is not installed.")
    print('Run: pip install -e ".[memory]"')
    return 1

  print("ChromaDB import OK")
  return 0


def check_voice() -> int:
  settings = load_settings()
  failed = False

  try:
    import sounddevice as sd  # noqa: F401
    import numpy  # noqa: F401
  except ImportError:
    print("Audio dependencies missing (sounddevice/numpy).")
    print('Run: pip install -e ".[voice]"')
    return 1

  try:
    devices = sd.query_devices()
    print(f"Audio devices OK ({len(devices)} found)")
  except Exception as exc:  # noqa: BLE001
    print(f"Audio device query failed: {exc}")
    failed = True

  try:
    from faster_whisper import WhisperModel
  except ImportError:
    print("faster-whisper is not installed.")
    print('Run: pip install -e ".[voice]"')
    return 1

  try:
    print(
      f"Loading Whisper model '{settings.voice.whisper_model}' "
      f"({settings.voice.whisper_device}/{settings.voice.whisper_compute_type})"
    )
    model = WhisperModel(
      settings.voice.whisper_model,
      device=settings.voice.whisper_device,
      compute_type=settings.voice.whisper_compute_type,
    )
    _ = model
    print("Whisper OK")
  except Exception as exc:  # noqa: BLE001
    print(f"Failed to load Whisper: {exc}")
    failed = True

  try:
    from kokoro import KPipeline

    print(f"Loading Kokoro TTS voice '{settings.voice.tts_voice}' (PC default)...")
    pipeline = KPipeline(lang_code=settings.voice.tts_lang, repo_id="hexgrad/Kokoro-82M")
    _ = pipeline
    print(f"Kokoro TTS OK (engine={settings.voice.tts_engine}, voice={settings.voice.tts_voice})")
  except ImportError:
    print("Kokoro is not installed (required PC default TTS).")
    print('Run: pip install -e ".[voice]"')
    failed = True
  except Exception as exc:  # noqa: BLE001
    print(f"Failed to load Kokoro: {exc}")
    failed = True

  return 1 if failed else 0


def main() -> None:
  parser = argparse.ArgumentParser(description="Verify Maira local model dependencies")
  parser.add_argument(
    "--check",
    choices=["ollama", "embeddings", "voice", "all"],
    default="ollama",
    help="Dependency to verify (default: ollama)",
  )
  args = parser.parse_args()

  if args.check == "ollama":
    sys.exit(check_ollama())
  if args.check == "embeddings":
    sys.exit(check_embeddings())
  if args.check == "voice":
    sys.exit(check_voice())

  ollama_code = check_ollama()
  print("---")
  embeddings_code = check_embeddings()
  print("---")
  voice_code = check_voice()
  sys.exit(0 if ollama_code == 0 and embeddings_code == 0 and voice_code == 0 else 1)


if __name__ == "__main__":
  main()
