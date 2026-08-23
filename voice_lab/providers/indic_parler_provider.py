"""AI4Bharat Indic Parler-TTS — open Indic female voices (Divya default)."""

from __future__ import annotations

import time
from pathlib import Path

from voice_lab import config
from voice_lab.audio_util import float32_to_wav_bytes, hf_cached
from voice_lab.providers.base import SynthesisResult, TTSProvider

try:
  from maira.modules.voice.download_guard import unavailable_message
except Exception:  # noqa: BLE001
  def unavailable_message(*, estimated_gb: float, max_gb: float, provider: str) -> str:
    return (
      f"This voice model ({provider}) requires approximately {estimated_gb:.1f} GB "
      f"and is disabled by the current local resource policy (max {max_gb:g} GB)."
    )

MODEL_ID = "ai4bharat/indic-parler-tts"
# Common weight file used to detect an existing HF cache without downloading.
_CACHE_PROBE = "model.safetensors.index.json"
_ESTIMATED_GB = 3.75
_MAX_GB = float(getattr(config, "MAX_MODEL_DOWNLOAD_GB", 1) or 1)


class IndicParlerProvider(TTSProvider):
  def __init__(self) -> None:
    self._latency: float | None = None
    self._model = None
    self._prompt_tokenizer = None
    self._description_tokenizer = None
    self._device = config.PARLER_DEVICE
    self._speaker = config.PARLER_SPEAKER
    self._allow_download = config.PARLER_ALLOW_DOWNLOAD
    self._sample_rate = 44100

  def get_provider_name(self) -> str:
    return "indic_parler"

  def get_latency(self) -> float | None:
    return self._latency

  def is_available(self) -> tuple[bool, str]:
    if not self._allow_download:
      # Hard resource policy: multi-GB models are unavailable unless explicitly allowed.
      cached = hf_cached(MODEL_ID, _CACHE_PROBE) or hf_cached(MODEL_ID, "model.safetensors")
      if not cached and _ESTIMATED_GB > _MAX_GB:
        return False, unavailable_message(
          estimated_gb=_ESTIMATED_GB, max_gb=_MAX_GB, provider="indic_parler"
        )
    try:
      import parler_tts  # noqa: F401
      import torch  # noqa: F401
      import transformers  # noqa: F401
    except ImportError as exc:
      return (
        False,
        "Indic Parler-TTS deps missing. Install: "
        "pip install git+https://github.com/huggingface/parler-tts.git "
        f"(missing: {exc})",
      )

    cached = hf_cached(MODEL_ID, _CACHE_PROBE) or hf_cached(MODEL_ID, "model.safetensors")
    if not cached and not self._allow_download:
      return (
        False,
        unavailable_message(estimated_gb=_ESTIMATED_GB, max_gb=_MAX_GB, provider="indic_parler"),
      )
    detail = "weights cached" if cached else "download permitted"
    return True, f"ready ({detail}, speaker={self._speaker}, device={self._device})"

  def _ensure_model(self) -> None:
    if self._model is not None:
      return
    import torch
    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer

    if not (hf_cached(MODEL_ID, _CACHE_PROBE) or hf_cached(MODEL_ID, "model.safetensors")):
      if self._allow_download:
        print("[indic_parler] Downloading ai4bharat/indic-parler-tts (large). Please wait...")
      else:
        raise RuntimeError("Parler download not permitted")

    device = self._device
    if device == "auto":
      device = "cuda:0" if torch.cuda.is_available() else "cpu"
    self._device = device

    self._model = ParlerTTSForConditionalGeneration.from_pretrained(MODEL_ID).to(device)
    self._prompt_tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    enc_name = self._model.config.text_encoder._name_or_path
    self._description_tokenizer = AutoTokenizer.from_pretrained(enc_name)
    self._sample_rate = int(getattr(self._model.config, "sampling_rate", 44100))

  def _description(self) -> str:
    return (
      f"{self._speaker}'s voice is clear and conversational, with a moderate speed "
      "and pitch, and a very close recording that almost has no background noise."
    )

  def synthesize(self, text: str, *, script_id: str = "english") -> SynthesisResult:
    ok, reason = self.is_available()
    if not ok:
      raise RuntimeError(reason)

    self._ensure_model()
    assert self._model is not None
    assert self._prompt_tokenizer is not None
    assert self._description_tokenizer is not None

    description = self._description()
    desc_inputs = self._description_tokenizer(description, return_tensors="pt").to(self._device)
    prompt_inputs = self._prompt_tokenizer(text, return_tensors="pt").to(self._device)

    started = time.perf_counter()
    try:
      generation = self._model.generate(
        input_ids=desc_inputs.input_ids,
        attention_mask=desc_inputs.attention_mask,
        prompt_input_ids=prompt_inputs.input_ids,
        prompt_attention_mask=prompt_inputs.attention_mask,
      )
    except Exception as exc:  # noqa: BLE001
      raise RuntimeError(f"Indic Parler synthesis failed: {exc}") from exc
    self._latency = time.perf_counter() - started

    audio = generation.detach().cpu().numpy().squeeze()
    audio_bytes = float32_to_wav_bytes(audio, self._sample_rate)
    return SynthesisResult(
      audio_bytes=audio_bytes,
      sample_rate=self._sample_rate,
      format="wav",
      meta={"model": MODEL_ID, "speaker": self._speaker, "script_id": script_id},
    )

  def save_audio(self, text: str, output_path: str | Path, *, script_id: str = "english") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result = self.synthesize(text, script_id=script_id)
    path.write_bytes(result.audio_bytes)
    return path
