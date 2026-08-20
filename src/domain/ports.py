"""Domain ports (Protocols) — keep use-cases free of concrete infrastructure."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from src.domain.models.bank_movement import BankMovement
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction


class DocumentExtractor(Protocol):
    async def extract_from_image(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        *,
        source=...,
    ) -> FinancialTransaction: ...

    async def structure_text(
        self,
        text: str,
        tenant_id: uuid.UUID,
        metadata: ExtractionMetadata,
    ) -> FinancialTransaction: ...


class TransactionStore(Protocol):
    async def save(self, entity: FinancialTransaction) -> FinancialTransaction: ...

    async def get_by_id(self, entity_id: uuid.UUID) -> FinancialTransaction | None: ...

    async def list_by_tenant(
        self, tenant_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> list[FinancialTransaction]: ...

    async def list_pending(self, tenant_id: uuid.UUID) -> list[FinancialTransaction]: ...


class MovementStore(Protocol):
    async def save(self, entity: BankMovement) -> BankMovement: ...

    async def list_by_period(
        self, tenant_id: uuid.UUID, statement_month: str
    ) -> list[BankMovement]: ...
