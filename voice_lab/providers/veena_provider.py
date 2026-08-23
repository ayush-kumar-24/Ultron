"""Maya Research Veena — open Hindi/English/Hinglish TTS (kavya female default)."""

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

MODEL_ID = "maya-research/veena-tts"
_CACHE_PROBE = "model.safetensors.index.json"
_ESTIMATED_GB = 7.5
_MAX_GB = float(getattr(config, "MAX_MODEL_DOWNLOAD_GB", 1) or 1)

# Special tokens from Veena model card
START_OF_SPEECH = 128257
END_OF_SPEECH = 128258
START_OF_HUMAN = 128259
END_OF_HUMAN = 128260
START_OF_AI = 128261
END_OF_AI = 128262
AUDIO_CODE_BASE_OFFSET = 128266


class VeenaProvider(TTSProvider):
  def __init__(self) -> None:
    self._latency: float | None = None
    self._model = None
    self._tokenizer = None
    self._snac = None
    self._device = config.VEENA_DEVICE
    self._speaker = config.VEENA_SPEAKER
    self._allow_download = config.VEENA_ALLOW_DOWNLOAD
    self._sample_rate = 24000

  def get_provider_name(self) -> str:
    return "veena"

  def get_latency(self) -> float | None:
    return self._latency

  def is_available(self) -> tuple[bool, str]:
    cached = hf_cached(MODEL_ID, _CACHE_PROBE) or hf_cached(MODEL_ID, "model.safetensors")
    if not cached and not self._allow_download and _ESTIMATED_GB > _MAX_GB:
      return False, unavailable_message(
        estimated_gb=_ESTIMATED_GB, max_gb=_MAX_GB, provider="veena"
      )
    try:
      import torch  # noqa: F401
      import transformers  # noqa: F401
      import snac  # noqa: F401
    except ImportError as exc:
      return (
        False,
        "Veena deps missing. Install: pip install transformers snac accelerate bitsandbytes "
        f"(missing: {exc}). GPU strongly recommended (~3B params).",
      )

    if not cached and not self._allow_download:
      return (
        False,
        unavailable_message(estimated_gb=_ESTIMATED_GB, max_gb=_MAX_GB, provider="veena"),
      )
    detail = "weights cached" if cached else "download permitted"
    return True, f"ready ({detail}, speaker={self._speaker}, device={self._device})"

  def _ensure_model(self) -> None:
    if self._model is not None:
      return
    import torch
    from snac import SNAC
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not (hf_cached(MODEL_ID, _CACHE_PROBE) or hf_cached(MODEL_ID, "model.safetensors")):
      if self._allow_download:
        print("[veena] Downloading maya-research/veena-tts (multi-GB). Please wait...")
      else:
        raise RuntimeError("Veena download not permitted")

    device = self._device
    if device == "auto":
      device = "cuda" if torch.cuda.is_available() else "cpu"
    self._device = device

    load_kwargs: dict = {"trust_remote_code": True}
    if device.startswith("cuda"):
      try:
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
          load_in_4bit=True,
          bnb_4bit_compute_dtype=torch.bfloat16,
        )
        load_kwargs["device_map"] = "auto"
      except Exception:  # noqa: BLE001
        load_kwargs["torch_dtype"] = torch.float16
        load_kwargs["device_map"] = "auto"
    else:
      print("[veena] Running on CPU — expect slow generation.")
      load_kwargs["torch_dtype"] = torch.float32

    self._model = AutoModelForCausalLM.from_pretrained(MODEL_ID, **load_kwargs)
    self._tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    snac_device = "cuda" if str(device).startswith("cuda") else "cpu"
    self._snac = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval().to(snac_device)

  def synthesize(self, text: str, *, script_id: str = "english") -> SynthesisResult:
    ok, reason = self.is_available()
    if not ok:
      raise RuntimeError(reason)

    import torch

    self._ensure_model()
    assert self._model is not None and self._tokenizer is not None and self._snac is not None

    speaker = self._speaker
    prompt = f"<spk_{speaker}> {text}"
    prompt_tokens = self._tokenizer.encode(prompt, add_special_tokens=False)
    input_tokens = [
      START_OF_HUMAN,
      *prompt_tokens,
      END_OF_HUMAN,
      START_OF_AI,
      START_OF_SPEECH,
    ]
    model_device = getattr(self._model, "device", None)
    if model_device is None:
      try:
        model_device = next(self._model.parameters()).device
      except Exception:  # noqa: BLE001
        model_device = torch.device("cpu")
    input_ids = torch.tensor([input_tokens], device=model_device)
    max_tokens = min(int(len(text) * 1.3) * 7 + 21, 700)

    started = time.perf_counter()
    try:
      with torch.no_grad():
        output = self._model.generate(
          input_ids,
          max_new_tokens=max_tokens,
          do_sample=True,
          temperature=0.4,
          top_p=0.9,
          repetition_penalty=1.05,
          pad_token_id=self._tokenizer.pad_token_id,
          eos_token_id=[END_OF_SPEECH, END_OF_AI],
        )
    except Exception as exc:  # noqa: BLE001
      raise RuntimeError(f"Veena synthesis failed: {exc}") from exc
    self._latency = time.perf_counter() - started

    generated_ids = output[0][len(input_tokens) :].tolist()
    snac_tokens = [
      token_id
      for token_id in generated_ids
      if AUDIO_CODE_BASE_OFFSET <= token_id < (AUDIO_CODE_BASE_OFFSET + 7 * 4096)
    ]
    if not snac_tokens:
      raise RuntimeError("Veena generated no audio tokens")

    audio = self._decode_snac(snac_tokens)
    audio_bytes = float32_to_wav_bytes(audio, self._sample_rate)
    return SynthesisResult(
      audio_bytes=audio_bytes,
      sample_rate=self._sample_rate,
      format="wav",
      meta={"model": MODEL_ID, "speaker": speaker, "script_id": script_id},
    )

  def _decode_snac(self, snac_tokens: list[int]):
    import torch

    if not snac_tokens or len(snac_tokens) % 7 != 0:
      # Truncate to multiple of 7
      snac_tokens = snac_tokens[: len(snac_tokens) - (len(snac_tokens) % 7)]
      if not snac_tokens:
        raise RuntimeError("Invalid SNAC token sequence from Veena")

    snac_device = next(self._snac.parameters()).device
    codes_lvl: list[list[int]] = [[], [], []]
    offsets = [AUDIO_CODE_BASE_OFFSET + i * 4096 for i in range(7)]
    for i in range(0, len(snac_tokens), 7):
      codes_lvl[0].append(snac_tokens[i] - offsets[0])
      codes_lvl[1].append(snac_tokens[i + 1] - offsets[1])
      codes_lvl[1].append(snac_tokens[i + 4] - offsets[4])
      codes_lvl[2].append(snac_tokens[i + 2] - offsets[2])
      codes_lvl[2].append(snac_tokens[i + 3] - offsets[3])
      codes_lvl[2].append(snac_tokens[i + 5] - offsets[5])
      codes_lvl[2].append(snac_tokens[i + 6] - offsets[6])

    hierarchical = [
      torch.tensor(level, dtype=torch.int32, device=snac_device).unsqueeze(0)
      for level in codes_lvl
    ]
    with torch.no_grad():
      audio = self._snac.decode(hierarchical)
    return audio.detach().cpu().numpy().squeeze()

  def save_audio(self, text: str, output_path: str | Path, *, script_id: str = "english") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result = self.synthesize(text, script_id=script_id)
    path.write_bytes(result.audio_bytes)
    return path
