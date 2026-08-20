"""
Abstract repository interface.
All concrete repositories must implement this contract so use-cases
never depend on a specific database technology.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class AbstractRepository(ABC, Generic[T]):
    """CRUD + list interface for a single aggregate root."""

    @abstractmethod
    async def save(self, entity: T) -> T:
        """Persist a new entity or overwrite an existing one."""

    @abstractmethod
    async def get_by_id(self, entity_id: uuid.UUID) -> T | None:
        """Return the entity or None if not found."""

    @abstractmethod
    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[T]:
        """Return paginated records for a tenant."""

    @abstractmethod
    async def delete(self, entity_id: uuid.UUID) -> None:
        """Hard-delete a record (use only for GDPR erasure)."""
