"""TTS worker process — runs inside a model's own virtual environment.

Standalone on purpose: only the standard library, numpy and the model's own
packages are imported (never the Ultron app), so the model's pinned library
versions cannot clash with the app.

Protocol: one JSON object per line.
stdin  <- {"type": "init", "engine": "chatterbox"|"indic_parler"|"fake", ...options}
          {"type": "synth", "id": 1, "text": "..."}
stdout -> {"type": "ready", "sample_rate": 24000, "device": "cuda"}
          {"type": "audio", "id": 1, "sample_rate": 24000, "data": "<base64 float32>"}
          {"type": "error", "id": 1 | null, "message": "..."}
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import traceback

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _protocol_stream():
  """Keep a private handle to the real stdout; send library prints to stderr."""
  proto = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
  os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
  sys.stdout = sys.stderr
  return proto


def _device(requested: str) -> str:
  if requested and requested != "auto":
    return requested
  import torch  # noqa: PLC0415

  return "cuda" if torch.cuda.is_available() else "cpu"


class ChatterboxEngine:
  """Resemble AI Chatterbox Multilingual (MIT). 23 languages incl. Hindi."""

  def __init__(self, options: dict) -> None:
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # noqa: PLC0415

    self.device = _device(str(options.get("device") or "auto"))
    self._model = ChatterboxMultilingualTTS.from_pretrained(device=self.device)
    self.sample_rate = int(self._model.sr)
    self._language = str(options.get("language") or "auto")
    self._exaggeration = float(options.get("exaggeration", 0.5))
    reference = options.get("reference_audio")
    if reference:
      # Any clean 5-15 s clip of the voice you want (e.g. a female Hindi speaker).
      self._model.prepare_conditionals(str(reference), exaggeration=self._exaggeration)

  def _language_for(self, text: str) -> str:
    if self._language != "auto":
      return self._language
    return "hi" if _DEVANAGARI.search(text) else "en"

  def synthesize(self, text: str):
    wav = self._model.generate(text, language_id=self._language_for(text), exaggeration=self._exaggeration)
    return wav.squeeze(0).detach().cpu().numpy()


class IndicParlerEngine:
  """AI4Bharat Indic Parler-TTS (Apache 2.0). Named Indian speakers, e.g. Divya."""

  MODEL_ID = "ai4bharat/indic-parler-tts"

  def __init__(self, options: dict) -> None:
    import torch  # noqa: PLC0415
    from parler_tts import ParlerTTSForConditionalGeneration  # noqa: PLC0415
    from transformers import AutoTokenizer  # noqa: PLC0415

    self._torch = torch
    device = _device(str(options.get("device") or "auto"))
    self.device = "cuda:0" if device == "cuda" else device
    self._model = ParlerTTSForConditionalGeneration.from_pretrained(self.MODEL_ID).to(self.device)
    self._prompt_tokenizer = AutoTokenizer.from_pretrained(self.MODEL_ID)
    self._description_tokenizer = AutoTokenizer.from_pretrained(self._model.config.text_encoder._name_or_path)
    self.sample_rate = int(getattr(self._model.config, "sampling_rate", 44100))
    speaker = str(options.get("speaker") or "Divya")
    self._description = str(
      options.get("description")
      or f"{speaker}'s voice is warm, clear and conversational, with a moderate speed and pitch, "
      "and a very close recording that almost has no background noise."
    )

  def synthesize(self, text: str):
    desc = self._description_tokenizer(self._description, return_tensors="pt").to(self.device)
    prompt = self._prompt_tokenizer(text, return_tensors="pt").to(self.device)
    with self._torch.inference_mode():
      generation = self._model.generate(
        input_ids=desc.input_ids,
        attention_mask=desc.attention_mask,
        prompt_input_ids=prompt.input_ids,
        prompt_attention_mask=prompt.attention_mask,
      )
    return generation.detach().cpu().numpy().squeeze()


class FakeEngine:
  """For tests: a short tone per character. Also prints to stdout like chatty libraries do."""

  def __init__(self, options: dict) -> None:
    print("fake engine loading... (this line must not break the protocol)")
    if options.get("fail_init"):
      raise RuntimeError("fake init failure")
    self.device = "cpu"
    self.sample_rate = 16000

  def synthesize(self, text: str):
    import numpy as np  # noqa: PLC0415

    print(f"synthesizing {text!r}")
    if text == "boom":
      raise RuntimeError("fake synth failure")
    n = max(1, len(text)) * 160
    return (0.1 * np.sin(np.arange(n, dtype="float32") / 5.0)).astype("float32")


ENGINES = {"chatterbox": ChatterboxEngine, "indic_parler": IndicParlerEngine, "fake": FakeEngine}


def main() -> int:
  proto = _protocol_stream()

  def send(message: dict) -> None:
    proto.write(json.dumps(message) + "\n")
    proto.flush()

  engine = None
  for line in sys.stdin:
    line = line.strip()
    if not line:
      continue
    try:
      message = json.loads(line)
    except json.JSONDecodeError:
      continue
    kind = message.get("type")
    if kind == "init":
      try:
        engine = ENGINES[str(message.get("engine"))](message)
        send({"type": "ready", "sample_rate": engine.sample_rate, "device": engine.device})
      except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        send({"type": "error", "id": None, "message": f"{type(exc).__name__}: {exc}"})
    elif kind == "synth":
      request_id = message.get("id")
      if engine is None:
        send({"type": "error", "id": request_id, "message": "engine not initialised"})
        continue
      try:
        import numpy as np  # noqa: PLC0415

        audio = np.asarray(engine.synthesize(str(message.get("text") or "")), dtype="float32").reshape(-1)
        send(
          {
            "type": "audio",
            "id": request_id,
            "sample_rate": engine.sample_rate,
            "data": base64.b64encode(audio.tobytes()).decode("ascii"),
          }
        )
      except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        send({"type": "error", "id": request_id, "message": f"{type(exc).__name__}: {exc}"})
  return 0  # stdin closed: Ultron quit


if __name__ == "__main__":
  sys.exit(main())
