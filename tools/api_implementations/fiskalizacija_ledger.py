"""
Fiscalization Ledger and Retry Queue

Provides:
- Invoice ledger for idempotency (prevent duplicate fiscalization)
- Retry queue for failed fiscalizations (48h deadline per Croatian law)
- Audit trail for all fiscalization attempts

Storage:
- Google Cloud Firestore (production)
- In-memory storage (development/testing)

This is a DETERMINISTIC tool - no LLM involvement.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass, asdict
import logging
import json
import hashlib

# Firestore
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

# Croatian law requires fiscalization within 48 hours
FISCALIZATION_DEADLINE_HOURS = 48

# Collections
LEDGER_COLLECTION = "fiscalization_ledger"
RETRY_QUEUE_COLLECTION = "fiscalization_retry_queue"
AUDIT_LOG_COLLECTION = "fiscalization_audit"
COUNTER_COLLECTION = "fiscalization_counters"


# ============================================================================
# DATA MODELS
# ============================================================================

class FiscalizationStatus(Enum):
    """Status of fiscalization attempt."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    EXPIRED = "expired"  # Past 48h deadline


@dataclass
class LedgerEntry:
    """Invoice ledger entry for idempotency."""
    invoice_number: str
    supplier_oib: str
    jir: Optional[str]
    zki: str
    status: str
    created_at: str
    updated_at: str
    signed_xml: Optional[str] = None
    fina_response: Optional[str] = None
    total_amount: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LedgerEntry':
        return cls(**data)


@dataclass
class RetryQueueEntry:
    """Entry in retry queue for failed fiscalizations."""
    invoice_number: str
    supplier_oib: str
    signed_xml: str
    zki: str
    first_attempt: str
    last_attempt: str
    attempt_count: int
    next_retry: str
    deadline: str  # 48h from first attempt
    error_message: str
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetryQueueEntry':
        return cls(**data)


# ============================================================================
# IN-MEMORY STORAGE (Development/Testing)
# ============================================================================

class InMemoryLedger:
    """In-memory implementation for development and testing."""

    def __init__(self):
        self._ledger: Dict[str, LedgerEntry] = {}
        self._retry_queue: Dict[str, RetryQueueEntry] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._counters: Dict[str, int] = {}

    def _make_key(self, invoice_number: str, supplier_oib: str) -> str:
        """Generate unique key for invoice."""
        return hashlib.md5(f"{supplier_oib}:{invoice_number}".encode()).hexdigest()

    def check_exists(self, invoice_number: str, supplier_oib: str) -> Optional[LedgerEntry]:
        """Check if invoice already exists in ledger."""
        key = self._make_key(invoice_number, supplier_oib)
        entry = self._ledger.get(key)
        return entry

    def save_entry(self, entry: LedgerEntry) -> str:
        """Save ledger entry."""
        key = self._make_key(entry.invoice_number, entry.supplier_oib)
        self._ledger[key] = entry
        return key

    def update_entry(self, invoice_number: str, supplier_oib: str, updates: Dict[str, Any]) -> bool:
        """Update existing ledger entry."""
        key = self._make_key(invoice_number, supplier_oib)
        if key in self._ledger:
            entry = self._ledger[key]
            for k, v in updates.items():
                if hasattr(entry, k):
                    setattr(entry, k, v)
            entry.updated_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def add_to_retry_queue(self, entry: RetryQueueEntry) -> str:
        """Add failed invoice to retry queue."""
        key = self._make_key(entry.invoice_number, entry.supplier_oib)
        self._retry_queue[key] = entry
        return key

    def get_retry_entry(self, invoice_number: str, supplier_oib: str) -> Optional[RetryQueueEntry]:
        """Get entry from retry queue."""
        key = self._make_key(invoice_number, supplier_oib)
        return self._retry_queue.get(key)

    def remove_from_retry_queue(self, invoice_number: str, supplier_oib: str) -> bool:
        """Remove entry from retry queue (after success or expiry)."""
        key = self._make_key(invoice_number, supplier_oib)
        if key in self._retry_queue:
            del self._retry_queue[key]
            return True
        return False

    def get_pending_retries(self) -> List[RetryQueueEntry]:
        """Get all entries due for retry."""
        now = datetime.now(timezone.utc)
        pending = []

        for entry in self._retry_queue.values():
            next_retry = datetime.fromisoformat(entry.next_retry.replace('Z', '+00:00'))
            deadline = datetime.fromisoformat(entry.deadline.replace('Z', '+00:00'))

            if now >= deadline:
                entry.status = FiscalizationStatus.EXPIRED.value
            elif now >= next_retry and entry.status != FiscalizationStatus.EXPIRED.value:
                pending.append(entry)

        return pending

    def add_audit_log(self, action: str, details: Dict[str, Any]) -> None:
        """Add entry to audit log."""
        self._audit_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details
        })

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get retry queue statistics."""
        now = datetime.now(timezone.utc)
        pending = 0
        expired = 0

        for entry in self._retry_queue.values():
            deadline = datetime.fromisoformat(entry.deadline.replace('Z', '+00:00'))
            if now >= deadline:
                expired += 1
            else:
                pending += 1

        return {
            "total": len(self._retry_queue),
            "pending": pending,
            "expired": expired
        }

    def get_next_invoice_number(self, supplier_oib: str, business_unit: str, device_number: str, year: int = None) -> int:
        """Get next sequential invoice number (in-memory counter)."""
        if year is None:
            year = datetime.now(timezone.utc).year
        key = f"{supplier_oib}_{business_unit}_{device_number}_{year}"
        current = self._counters.get(key, 0)
        new_number = current + 1
        self._counters[key] = new_number
        return new_number


# ============================================================================
# FIRESTORE STORAGE (Production)
# ============================================================================

class FirestoreLedger:
    """Firestore implementation for production."""

    def __init__(self, project_id: str = None):
        if not FIRESTORE_AVAILABLE:
            raise ImportError("google-cloud-firestore required for Firestore ledger")

        self.db = firestore.Client(project=project_id) if project_id else firestore.Client()
        logger.info("Firestore ledger initialized")

    def _make_doc_id(self, invoice_number: str, supplier_oib: str) -> str:
        """Generate document ID."""
        return hashlib.md5(f"{supplier_oib}:{invoice_number}".encode()).hexdigest()

    def check_exists(self, invoice_number: str, supplier_oib: str) -> Optional[LedgerEntry]:
        """Check if invoice exists in Firestore."""
        doc_id = self._make_doc_id(invoice_number, supplier_oib)
        doc_ref = self.db.collection(LEDGER_COLLECTION).document(doc_id)
        doc = doc_ref.get()

        if doc.exists:
            return LedgerEntry.from_dict(doc.to_dict())
        return None

    def save_entry(self, entry: LedgerEntry) -> str:
        """Save ledger entry to Firestore."""
        doc_id = self._make_doc_id(entry.invoice_number, entry.supplier_oib)
        doc_ref = self.db.collection(LEDGER_COLLECTION).document(doc_id)
        doc_ref.set(entry.to_dict())
        return doc_id

    def update_entry(self, invoice_number: str, supplier_oib: str, updates: Dict[str, Any]) -> bool:
        """Update existing ledger entry."""
        doc_id = self._make_doc_id(invoice_number, supplier_oib)
        doc_ref = self.db.collection(LEDGER_COLLECTION).document(doc_id)

        if doc_ref.get().exists:
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            doc_ref.update(updates)
            return True
        return False

    def add_to_retry_queue(self, entry: RetryQueueEntry) -> str:
        """Add to Firestore retry queue."""
        doc_id = self._make_doc_id(entry.invoice_number, entry.supplier_oib)
        doc_ref = self.db.collection(RETRY_QUEUE_COLLECTION).document(doc_id)
        doc_ref.set(entry.to_dict())
        return doc_id

    def get_retry_entry(self, invoice_number: str, supplier_oib: str) -> Optional[RetryQueueEntry]:
        """Get retry queue entry from Firestore."""
        doc_id = self._make_doc_id(invoice_number, supplier_oib)
        doc_ref = self.db.collection(RETRY_QUEUE_COLLECTION).document(doc_id)
        doc = doc_ref.get()

        if doc.exists:
            return RetryQueueEntry.from_dict(doc.to_dict())
        return None

    def remove_from_retry_queue(self, invoice_number: str, supplier_oib: str) -> bool:
        """Remove from Firestore retry queue."""
        doc_id = self._make_doc_id(invoice_number, supplier_oib)
        doc_ref = self.db.collection(RETRY_QUEUE_COLLECTION).document(doc_id)

        if doc_ref.get().exists:
            doc_ref.delete()
            return True
        return False

    def get_pending_retries(self) -> List[RetryQueueEntry]:
        """Get pending retries from Firestore."""
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()

        # Query entries where next_retry <= now and status != expired
        query = (
            self.db.collection(RETRY_QUEUE_COLLECTION)
            .where("next_retry", "<=", now_str)
            .where("status", "!=", FiscalizationStatus.EXPIRED.value)
        )

        pending = []
        for doc in query.stream():
            entry = RetryQueueEntry.from_dict(doc.to_dict())
            deadline = datetime.fromisoformat(entry.deadline.replace('Z', '+00:00'))

            if now >= deadline:
                # Mark as expired
                doc.reference.update({"status": FiscalizationStatus.EXPIRED.value})
            else:
                pending.append(entry)

        return pending

    def add_audit_log(self, action: str, details: Dict[str, Any]) -> None:
        """Add audit log entry to Firestore."""
        self.db.collection(AUDIT_LOG_COLLECTION).add({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details
        })

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get retry queue statistics."""
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()

        total = 0
        pending = 0
        expired = 0

        for doc in self.db.collection(RETRY_QUEUE_COLLECTION).stream():
            total += 1
            data = doc.to_dict()
            deadline = datetime.fromisoformat(data["deadline"].replace('Z', '+00:00'))

            if now >= deadline:
                expired += 1
            else:
                pending += 1

        return {
            "total": total,
            "pending": pending,
            "expired": expired
        }

    def get_next_invoice_number(self, supplier_oib: str, business_unit: str, device_number: str, year: int = None) -> int:
        """
        Get next sequential invoice number using Firestore atomic transaction.

        Uses a counter document per supplier/business_unit/device/year combination
        to ensure unique, sequential invoice numbers even with concurrent access.

        Args:
            supplier_oib: Supplier's OIB
            business_unit: Business premise code
            device_number: Cash register code
            year: Year (defaults to current year)

        Returns:
            Next sequential invoice number (1, 2, 3, ...)
        """
        if year is None:
            year = datetime.now(timezone.utc).year

        counter_doc_id = f"{supplier_oib}_{business_unit}_{device_number}_{year}"
        counter_ref = self.db.collection(COUNTER_COLLECTION).document(counter_doc_id)

        @firestore.transactional
        def increment_counter(transaction, counter_ref):
            snapshot = counter_ref.get(transaction=transaction)
            if snapshot.exists:
                current = snapshot.to_dict().get('last_number', 0)
            else:
                current = 0
            new_number = current + 1
            transaction.set(counter_ref, {
                'last_number': new_number,
                'supplier_oib': supplier_oib,
                'business_unit': business_unit,
                'device_number': device_number,
                'year': year,
                'updated_at': datetime.now(timezone.utc).isoformat()
            })
            return new_number

        transaction = self.db.transaction()
        return increment_counter(transaction, counter_ref)


# ============================================================================
# LEDGER SERVICE (Facade)
# ============================================================================

class FiscalizationLedgerService:
    """
    Service for managing fiscalization ledger and retry queue.

    Uses Firestore in production, in-memory storage for development.
    """

    def __init__(self, use_firestore: bool = False, project_id: str = None):
        """
        Initialize ledger service.

        Args:
            use_firestore: Use Firestore (True) or in-memory (False)
            project_id: GCP project ID for Firestore
        """
        if use_firestore:
            self.storage = FirestoreLedger(project_id)
        else:
            self.storage = InMemoryLedger()

        self.use_firestore = use_firestore
        logger.info(f"Ledger service initialized (firestore={use_firestore})")

    def check_invoice_exists(
        self,
        invoice_number: str,
        supplier_oib: str
    ) -> Dict[str, Any]:
        """
        Check if invoice already exists (idempotency check).

        Args:
            invoice_number: Invoice number
            supplier_oib: Supplier's OIB

        Returns:
            Dictionary with:
                - exists: bool
                - jir: Optional existing JIR
                - status: Current status
                - timestamp: When fiscalized
        """
        entry = self.storage.check_exists(invoice_number, supplier_oib)

        if entry:
            logger.info(f"Invoice {invoice_number} found in ledger, status={entry.status}")
            return {
                "exists": True,
                "jir": entry.jir,
                "zki": entry.zki,
                "status": entry.status,
                "timestamp": entry.created_at
            }

        return {
            "exists": False,
            "jir": None,
            "zki": None,
            "status": None,
            "timestamp": None
        }

    def save_successful_fiscalization(
        self,
        invoice_number: str,
        supplier_oib: str,
        jir: str,
        zki: str,
        signed_xml: str,
        fina_response: str,
        total_amount: str = None
    ) -> Dict[str, Any]:
        """
        Save successful fiscalization to ledger.

        Args:
            invoice_number: Invoice number
            supplier_oib: Supplier's OIB
            jir: JIR from FINA
            zki: ZKI code
            signed_xml: Signed XML document
            fina_response: Raw FINA response
            total_amount: Invoice total

        Returns:
            Dictionary with success status and document ID
        """
        now = datetime.now(timezone.utc).isoformat()

        entry = LedgerEntry(
            invoice_number=invoice_number,
            supplier_oib=supplier_oib,
            jir=jir,
            zki=zki,
            status=FiscalizationStatus.SUCCESS.value,
            created_at=now,
            updated_at=now,
            signed_xml=signed_xml,
            fina_response=fina_response,
            total_amount=total_amount
        )

        doc_id = self.storage.save_entry(entry)

        # Remove from retry queue if present
        self.storage.remove_from_retry_queue(invoice_number, supplier_oib)

        # Audit log
        self.storage.add_audit_log("FISCALIZATION_SUCCESS", {
            "invoice_number": invoice_number,
            "supplier_oib": supplier_oib[-4:],  # Last 4 digits for privacy
            "jir": jir
        })

        logger.info(f"Saved successful fiscalization: {invoice_number}, JIR={jir}")

        return {
            "success": True,
            "document_id": doc_id,
            "error": None
        }

    def add_to_retry_queue(
        self,
        invoice_number: str,
        supplier_oib: str,
        signed_xml: str,
        zki: str,
        error_message: str
    ) -> Dict[str, Any]:
        """
        Add failed fiscalization to retry queue.

        Implements exponential backoff: 1m, 2m, 4m, 8m, 16m, 32m, 64m...

        Args:
            invoice_number: Invoice number
            supplier_oib: Supplier's OIB
            signed_xml: Signed XML document
            zki: ZKI code
            error_message: Error that caused failure

        Returns:
            Dictionary with:
                - success: bool
                - queue_position: Position in queue
                - next_retry: Next retry datetime
                - deadline: 48h deadline
                - attempt_count: Number of attempts so far
        """
        now = datetime.now(timezone.utc)

        # Check if already in queue
        existing = self.storage.get_retry_entry(invoice_number, supplier_oib)

        if existing:
            # Update existing entry
            attempt_count = existing.attempt_count + 1

            # Exponential backoff: 2^attempt minutes
            backoff_minutes = min(2 ** attempt_count, 60)  # Cap at 60 minutes
            next_retry = now + timedelta(minutes=backoff_minutes)

            # Keep original deadline
            deadline = datetime.fromisoformat(existing.deadline.replace('Z', '+00:00'))

            if now >= deadline:
                return {
                    "success": False,
                    "queue_position": None,
                    "next_retry": None,
                    "deadline": existing.deadline,
                    "attempt_count": attempt_count,
                    "error": "48h deadline exceeded"
                }

            entry = RetryQueueEntry(
                invoice_number=invoice_number,
                supplier_oib=supplier_oib,
                signed_xml=signed_xml,
                zki=zki,
                first_attempt=existing.first_attempt,
                last_attempt=now.isoformat(),
                attempt_count=attempt_count,
                next_retry=next_retry.isoformat(),
                deadline=existing.deadline,
                error_message=error_message,
                status=FiscalizationStatus.RETRYING.value
            )
        else:
            # New entry
            deadline = now + timedelta(hours=FISCALIZATION_DEADLINE_HOURS)
            next_retry = now + timedelta(minutes=1)  # First retry after 1 minute

            entry = RetryQueueEntry(
                invoice_number=invoice_number,
                supplier_oib=supplier_oib,
                signed_xml=signed_xml,
                zki=zki,
                first_attempt=now.isoformat(),
                last_attempt=now.isoformat(),
                attempt_count=1,
                next_retry=next_retry.isoformat(),
                deadline=deadline.isoformat(),
                error_message=error_message,
                status=FiscalizationStatus.RETRYING.value
            )

        self.storage.add_to_retry_queue(entry)

        # Update ledger entry if exists
        self.storage.update_entry(invoice_number, supplier_oib, {
            "status": FiscalizationStatus.RETRYING.value,
            "error_message": error_message
        })

        # Audit log
        self.storage.add_audit_log("ADDED_TO_RETRY_QUEUE", {
            "invoice_number": invoice_number,
            "attempt_count": entry.attempt_count,
            "next_retry": entry.next_retry
        })

        stats = self.storage.get_queue_stats()

        logger.info(
            f"Added to retry queue: {invoice_number}, "
            f"attempt={entry.attempt_count}, next_retry={entry.next_retry}"
        )

        return {
            "success": True,
            "queue_position": stats["pending"],
            "next_retry": entry.next_retry,
            "deadline": entry.deadline,
            "attempt_count": entry.attempt_count,
            "error": None
        }

    def get_pending_retries(self) -> List[Dict[str, Any]]:
        """Get all invoices due for retry."""
        entries = self.storage.get_pending_retries()
        return [e.to_dict() for e in entries]

    def get_queue_statistics(self) -> Dict[str, Any]:
        """Get retry queue statistics."""
        return self.storage.get_queue_stats()

    def get_next_invoice_number(
        self,
        supplier_oib: str,
        business_unit: str = "1",
        device_number: str = "1",
        year: int = None
    ) -> int:
        """
        Get next sequential invoice number (atomic counter).

        Uses Firestore transactions in production for concurrent safety,
        in-memory counter for development.

        Args:
            supplier_oib: Supplier's OIB
            business_unit: Business premise code (default "1")
            device_number: Cash register code (default "1")
            year: Year (defaults to current year)

        Returns:
            Next sequential number (1, 2, 3, ...)
        """
        return self.storage.get_next_invoice_number(
            supplier_oib=supplier_oib,
            business_unit=business_unit,
            device_number=device_number,
            year=year
        )


# ============================================================================
# GLOBAL SERVICE INSTANCE
# ============================================================================

_ledger_service: Optional[FiscalizationLedgerService] = None


def get_ledger_service(
    use_firestore: bool = False,
    project_id: str = None
) -> FiscalizationLedgerService:
    """Get or create ledger service instance."""
    global _ledger_service

    if _ledger_service is None:
        _ledger_service = FiscalizationLedgerService(
            use_firestore=use_firestore,
            project_id=project_id
        )

    return _ledger_service


# ============================================================================
# CONVENIENCE FUNCTIONS FOR ADK TOOLS
# ============================================================================

def check_invoice_ledger(
    invoice_number: str,
    supplier_oib: str,
    use_firestore: bool = False
) -> Dict[str, Any]:
    """
    Check if invoice already fiscalized (idempotency).

    Convenience function for ADK tools.
    """
    service = get_ledger_service(use_firestore=use_firestore)
    return service.check_invoice_exists(invoice_number, supplier_oib)


def save_to_ledger(
    invoice_number: str,
    supplier_oib: str,
    jir: str,
    zki: str,
    signed_xml: str,
    fina_response: str,
    total_amount: str = None,
    use_firestore: bool = False
) -> Dict[str, Any]:
    """
    Save successful fiscalization to ledger.

    Convenience function for ADK tools.
    """
    service = get_ledger_service(use_firestore=use_firestore)
    return service.save_successful_fiscalization(
        invoice_number=invoice_number,
        supplier_oib=supplier_oib,
        jir=jir,
        zki=zki,
        signed_xml=signed_xml,
        fina_response=fina_response,
        total_amount=total_amount
    )


def add_to_retry(
    invoice_number: str,
    supplier_oib: str,
    signed_xml: str,
    zki: str,
    error_message: str,
    use_firestore: bool = False
) -> Dict[str, Any]:
    """
    Add failed fiscalization to retry queue.

    Convenience function for ADK tools.
    """
    service = get_ledger_service(use_firestore=use_firestore)
    return service.add_to_retry_queue(
        invoice_number=invoice_number,
        supplier_oib=supplier_oib,
        signed_xml=signed_xml,
        zki=zki,
        error_message=error_message
    )
