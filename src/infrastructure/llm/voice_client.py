"""
Groq Whisper adapter for voice-note transcription → OpenAI structuring.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings
from src.domain.exceptions import ExtractionError
from src.domain.models.enums import DocumentSource
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.infrastructure.llm.openai_client import OpenAIClient

_SUPPORTED_AUDIO = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}
_WHISPER_MODEL = "whisper-large-v3"


class VoiceClient:
    """Transcribe with Groq Whisper, structure with OpenAI."""

    def __init__(
        self,
        groq_client: Groq | None = None,
        openai_client: OpenAIClient | None = None,
    ) -> None:
        if groq_client is not None:
            self._groq = groq_client
        else:
            settings = get_settings()
            self._groq = Groq(api_key=settings.groq_api_key.get_secret_value())
        self._openai = openai_client or OpenAIClient()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8), reraise=True)
    def _transcribe(self, file_path: Path) -> str:
        with open(file_path, "rb") as audio_file:
            transcription = self._groq.audio.transcriptions.create(
                file=(file_path.name, audio_file),
                model=_WHISPER_MODEL,
                response_format="text",
                language="es",
                temperature=0.0,
            )
        return str(transcription)

    async def extract_from_audio(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
    ) -> FinancialTransaction:
        ext = file_path.suffix.lower()
        if ext not in _SUPPORTED_AUDIO:
            raise ExtractionError(
                f"Unsupported audio format '{ext}'. Supported: {_SUPPORTED_AUDIO}"
            )
        if not file_path.exists():
            raise ExtractionError(f"Audio file not found: {file_path}")

        try:
            transcript = self._transcribe(file_path)
        except Exception as exc:
            raise ExtractionError(f"Groq transcription failed: {exc}") from exc

        metadata = ExtractionMetadata(
            source=DocumentSource.AUDIO,
            raw_file_path=str(file_path),
            extraction_model=_WHISPER_MODEL,
            extraction_timestamp=datetime.utcnow(),
            confidence_score=0.80,
            raw_text=transcript,
        )
        return await self._openai.structure_text(transcript, tenant_id, metadata)
