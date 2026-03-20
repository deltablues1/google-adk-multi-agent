"""
Abstract Repository Interfaces
================================
Business services depend only on these abstractions.
Firestore (or Postgres) implementations live in repositories/firestore/.
Swap DB backends by changing the import — zero business logic changes needed.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar, Optional, List

from ..request_context import ERPRequestContext

T = TypeVar("T")


@dataclass
class InvoiceReference:
    """
    Uniform identifier for any invoice type.
    Intentionally does NOT contain collection/table names — the repository
    implementation handles type → storage location mapping.
    """
    invoice_id: str       # UUID (internal Firestore doc ID)
    invoice_type: str     # b2c | b2b | b2g | eu | int | vendor
    display_id: str       # e.g. "RAC-2026-00123" — for UI and audit logs

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "invoice_type": self.invoice_type,
            "display_id": self.display_id,
        }


class Repository(ABC, Generic[T]):
    """
    Generic async repository interface.
    All methods receive ERPRequestContext for tenant isolation and permission context.
    """

    @abstractmethod
    async def get(self, id: str, ctx: ERPRequestContext) -> Optional[T]:
        """Fetch a single entity by ID, scoped to ctx.company_id."""
        ...

    @abstractmethod
    async def list(
        self,
        ctx: ERPRequestContext,
        filters: Optional[dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[T]:
        """List entities with optional filters, scoped to ctx.company_id."""
        ...

    @abstractmethod
    async def create(self, entity: T, ctx: ERPRequestContext) -> T:
        """Persist a new entity."""
        ...

    @abstractmethod
    async def update(self, id: str, ctx: ERPRequestContext, data: dict) -> T:
        """Partial update — only provided fields are changed."""
        ...

    @abstractmethod
    async def soft_delete(self, id: str, ctx: ERPRequestContext) -> None:
        """Mark entity as deleted. Never physically removes data."""
        ...
