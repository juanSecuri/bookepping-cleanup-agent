"""
Local / free audio transcription → plain text for rule structuring.

Order:
  1. faster-whisper tiny (local) if available and WHISPER_BACKEND!=groq
  2. Groq Whisper free tier if GROQ_API_KEY set
Never requires OpenAI for structuring — caller uses local CoA rules.
"""
from __future__ import annotations

import gc
import logging
import os
from pathlib import Path

from src.config import get_settings
from src.domain.exceptions import ExtractionError

logger = logging.getLogger(__name__)

_SUPPORTED = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}
_whisper_model = None


def _unload_whisper() -> None:
    global _whisper_model
    _whisper_model = None
    gc.collect()


class LocalVoiceTranscriber:
    def transcribe(self, file_path: Path) -> tuple[str, str]:
        """Return (transcript, engine_label)."""
        ext = file_path.suffix.lower()
        if ext not in _SUPPORTED:
            raise ExtractionError(f"Unsupported audio '{ext}'. Supported: {_SUPPORTED}")
        if not file_path.exists():
            raise ExtractionError(f"Audio not found: {file_path}")

        backend = (os.getenv("WHISPER_BACKEND") or "auto").strip().lower()
        settings = get_settings()
        groq_key = settings.groq_api_key.get_secret_value() if settings.groq_api_key else ""

        errors: list[str] = []

        if backend in {"auto", "local", "faster-whisper"}:
            try:
                return self._faster_whisper(file_path), "faster-whisper-tiny"
            except Exception as exc:
                errors.append(f"faster-whisper: {exc}")
                _unload_whisper()
                if backend in {"local", "faster-whisper"}:
                    raise ExtractionError(
                        f"Local whisper failed on Render Free (RAM?): {exc}"
                    ) from exc

        if backend in {"auto", "groq"} and groq_key:
            try:
                return self._groq(file_path, groq_key), "groq-whisper"
            except Exception as exc:
                errors.append(f"groq: {exc}")
                if backend == "groq":
                    raise ExtractionError(f"Groq transcription failed: {exc}") from exc

        raise ExtractionError(
            "Audio transcription unavailable. "
            "Install faster-whisper (Docker) or set GROQ_API_KEY (free tier). "
            + (" | ".join(errors) if errors else "")
        )

    def _faster_whisper(self, file_path: Path) -> str:
        global _whisper_model
        from faster_whisper import WhisperModel

        if _whisper_model is None:
            # tiny + int8 ≈ viable on low RAM; still risk OOM on Free 512MB
            _whisper_model = WhisperModel(
                "tiny",
                device="cpu",
                compute_type="int8",
                cpu_threads=1,
            )
        segments, _info = _whisper_model.transcribe(
            str(file_path),
            language="es",
            beam_size=1,
            vad_filter=True,
        )
        text = " ".join(seg.text.strip() for seg in segments if seg.text).strip()
        _unload_whisper()
        if not text:
            raise ExtractionError("faster-whisper returned empty transcript")
        return text

    def _groq(self, file_path: Path, api_key: str) -> str:
        from groq import Groq

        client = Groq(api_key=api_key)
        with open(file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(file_path.name, audio_file),
                model="whisper-large-v3",
                response_format="text",
                language="es",
                temperature=0.0,
            )
        text = str(transcription).strip()
        if not text:
            raise ExtractionError("Groq returned empty transcript")
        return text

    async def transcribe_async(self, file_path: Path) -> tuple[str, str]:
        import asyncio

        return await asyncio.to_thread(self.transcribe, file_path)
