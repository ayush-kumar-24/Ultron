"""Voice conversation mode: 〰 button → hands-free loop, captions, exit paths."""

from __future__ import annotations

import threading

from maira.core.bus.event_bus import EventBus
from maira.modules.voice.service import TOPIC_ERROR, TOPIC_REPLY, TOPIC_STATUS, TOPIC_TRANSCRIPT
from maira.ui.prototype.integration.voice_bridge import ProtoVoiceBridge
from maira.ui.prototype.screens.chat import ChatScreen


class FakeVoice:
  def __init__(self) -> None:
    self.calls: list[str] = []
    self.in_conversation = False

  def is_available(self) -> bool:
    return True

  def start_conversation(self) -> None:
    self.calls.append("start")
    self.in_conversation = True

  def stop_conversation(self) -> None:
    self.calls.append("stop")
    self.in_conversation = False

  def start_dictation(self) -> None:
    self.calls.append("dictate")

  def stop_dictation(self) -> None:
    self.calls.append("dictate-stop")

  def cancel_dictation(self) -> None:
    self.calls.append("dictate-cancel")


def _setup(qtbot):
  bus = EventBus()
  voice = FakeVoice()
  chat = ChatScreen()
  qtbot.addWidget(chat)
  chat.set_live_mode(True)
  bridge = ProtoVoiceBridge(voice, bus, chat)
  return bus, voice, chat, bridge


def _publish_from_thread(bus: EventBus, topic: str, payload: dict) -> None:
  worker = threading.Thread(target=bus.publish, args=(topic, payload))
  worker.start()
  worker.join()


def test_talk_button_starts_and_stops_conversation(qtbot) -> None:
  _bus, voice, chat, _bridge = _setup(qtbot)
  chat.input.talk_btn.clicked.emit()
  assert chat.voice_mode
  assert chat.stage.currentWidget() is chat.voice_page
  assert voice.calls == ["start"]
  chat.input.talk_btn.clicked.emit()
  assert not chat.voice_mode
  assert chat.stage.currentWidget() is chat.chat_page
  assert voice.calls == ["start", "stop"]


def test_states_and_captions_follow_the_conversation(qtbot) -> None:
  bus, _voice, chat, _bridge = _setup(qtbot)
  chat.set_voice_mode(True)
  stage = chat.voice_stage

  _publish_from_thread(bus, TOPIC_STATUS, {"status": "listening"})
  qtbot.waitUntil(lambda: stage.status.text() == "Listening…", timeout=3000)
  _publish_from_thread(bus, TOPIC_TRANSCRIPT, {"text": "what's pending"})
  qtbot.waitUntil(lambda: stage.you.text() == "Aap: what's pending", timeout=3000)
  _publish_from_thread(bus, TOPIC_STATUS, {"status": "thinking"})
  qtbot.waitUntil(lambda: stage.status.text() == "Soch rahi hoon…", timeout=3000)
  _publish_from_thread(bus, TOPIC_STATUS, {"status": "speaking"})
  _publish_from_thread(bus, TOPIC_REPLY, {"text": "Pending tasks (1): Call mom"})
  qtbot.waitUntil(lambda: stage.reply.text() == "Pending tasks (1): Call mom", timeout=3000)
  # Dictation UI stays untouched during a conversation.
  assert not chat.dictating


def test_errors_stay_on_the_voice_screen(qtbot) -> None:
  bus, _voice, chat, _bridge = _setup(qtbot)
  chat.set_voice_mode(True)
  _publish_from_thread(bus, TOPIC_ERROR, {"message": "No reply received."})
  qtbot.waitUntil(lambda: chat.voice_stage.hint.text() == "No reply received.", timeout=3000)
  assert chat.voice_mode
  assert chat.error.isHidden()


def test_loop_ending_by_itself_leaves_voice_mode(qtbot) -> None:
  bus, voice, chat, _bridge = _setup(qtbot)
  chat.set_voice_mode(True)
  voice.in_conversation = False  # e.g. microphone disconnected
  _publish_from_thread(bus, TOPIC_STATUS, {"status": "idle"})
  qtbot.waitUntil(lambda: not chat.voice_mode, timeout=3000)


def test_idle_between_turns_keeps_voice_mode(qtbot) -> None:
  bus, _voice, chat, _bridge = _setup(qtbot)
  chat.set_voice_mode(True)
  _publish_from_thread(bus, TOPIC_STATUS, {"status": "idle"})
  qtbot.wait(100)
  assert chat.voice_mode


def test_dictation_still_works_outside_voice_mode(qtbot) -> None:
  _bus, voice, chat, _bridge = _setup(qtbot)
  chat.input.mic_btn.clicked.emit()
  assert voice.calls == ["dictate"]
  assert not chat.voice_mode


def test_starting_conversation_cancels_dictation(qtbot) -> None:
  _bus, voice, chat, _bridge = _setup(qtbot)
  chat.input.mic_btn.clicked.emit()
  chat.set_voice_mode(True)
  assert "dictate-cancel" in voice.calls and voice.calls[-1] == "start"
  assert not chat.dictating


def test_window_shortcut_toggles_and_escape_ends(qtbot) -> None:
  from maira.ui.prototype.shell.main_window import PrototypeWindow

  window = PrototypeWindow(skip_onboarding=True)
  qtbot.addWidget(window)
  chat = window.screens["chat"]
  chat.set_voice_backend(True)
  window.navigate("home")
  window.toggle_conversation()
  assert chat.voice_mode and window.stack.currentWidget() is chat
  window._escape()  # noqa: SLF001
  assert not chat.voice_mode


def test_unavailable_voice_leaves_voice_mode_and_explains(qtbot) -> None:
  bus, voice, chat, _bridge = _setup(qtbot)

  def refuse() -> None:
    voice.calls.append("start")
    bus.publish(TOPIC_ERROR, {"message": 'Voice is unavailable. Install extras with: pip install -e ".[voice]"'})

  voice.start_conversation = refuse
  chat.set_voice_mode(True)
  assert not chat.voice_mode
  qtbot.waitUntil(lambda: not chat.error.isHidden(), timeout=3000)
