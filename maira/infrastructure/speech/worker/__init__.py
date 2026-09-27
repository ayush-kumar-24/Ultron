"""Heavy TTS models (Chatterbox, Indic Parler) run in their own Python environments.

Each model pins library versions that clash with each other and with the app
(e.g. transformers 5.2.0 vs 4.46.1), so each lives in ``voice_envs/<name>`` and
runs ``tts_worker.py`` as a child process. See ``scripts/setup_voice.py``.
"""
