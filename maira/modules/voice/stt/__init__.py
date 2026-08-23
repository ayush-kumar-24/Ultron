"""Speech-to-text submodule."""



from __future__ import annotations



from maira.core.interfaces.speech_providers import STTProvider

from maira.infrastructure.speech.whisper.engine import WhisperEngine





class SpeechToText:

  def __init__(self, engine: WhisperEngine | STTProvider, *, language: str | None = None) -> None:

    self._engine = engine

    self._language = language



  @classmethod

  def from_provider(cls, provider: STTProvider) -> SpeechToText:

    return cls(provider)



  def is_available(self) -> bool:

    if isinstance(self._engine, STTProvider):

      return self._engine.is_available()[0]

    return self._engine.is_available()



  def warm_up(self) -> None:

    self._engine.warm_up()



  def transcribe(self, audio) -> str:

    if isinstance(self._engine, STTProvider):

      return self._engine.transcribe(audio)

    return self._engine.transcribe(audio, language=self._language)


