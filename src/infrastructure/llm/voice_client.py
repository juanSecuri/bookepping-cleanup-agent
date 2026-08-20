"""
Groq Whisper adapter for transcribing voice notes.

Audio note workflow:
  1. Accountant records a voice memo describing an expense/income.
  2. VoiceClient transcribes it with whisper-large-v3.
  3. The raw transcript is forwarded to ClaudeVisionClient (text mode)
     or directly to the ingest_document use-case for structuring.
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
from src.infrastructure.llm.text_structurer import TextStructurer

_SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}
_WHISPER_MODEL = "whisper-large-v3"


class VoiceClient:
    """
    Transcribes audio voice notes via Groq Cloud (whisper-large-v3)
    and returns a structured FinancialTransaction.

    Example:
        client = VoiceClient()
        tx = await client.extract_from_audio(
            file_path=Path("notes/2023-04-voice.m4a"),
            tenant_id=uuid.UUID("..."),
        )
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._groq = Groq(api_key=settings.groq_api_key.get_secret_value())
        self._structurer = TextStructurer()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    def _transcribe(self, file_path: Path) -> str:
        with open(file_path, "rb") as audio_file:
            transcription = self._groq.audio.transcriptions.create(
                file=(file_path.name, audio_file),
                model=_WHISPER_MODEL,
                response_format="text",
                language="es",   # Spanish default — override if needed
                temperature=0.0,
            )
        return str(transcription)

    async def extract_from_audio(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
    ) -> FinancialTransaction:
        """
        Transcribe the voice note, then use the TextStructurer to
        parse the transcript into a FinancialTransaction domain entity.
        """
        ext = file_path.suffix.lower()
        if ext not in _SUPPORTED_AUDIO_EXTENSIONS:
            raise ExtractionError(
                f"Unsupported audio format '{ext}'. "
                f"Supported: {_SUPPORTED_AUDIO_EXTENSIONS}"
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
            confidence_score=0.80,   # Whisper does not expose per-segment confidence
            raw_text=transcript,
        )

        return await self._structurer.structure_transcript(
            transcript=transcript,
            tenant_id=tenant_id,
            metadata=metadata,
        )
