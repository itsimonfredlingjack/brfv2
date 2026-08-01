"""Vendor-neutral integration domain: incoming source events, read-only
invoice snapshots and reviewable findings.

Three rules hold this package together, and every module in it is written to
make them structural rather than aspirational:

1. **No vendor name reaches the core.** ``SourceEvent``, ``InvoiceSnapshot``
   and ``ReviewFinding`` know nothing about Outlook, Microsoft Graph or
   Fortnox. Adapters translate a specific system's payload into these types;
   the types never grow a field named after the system that filled it.

2. **Adapters read. They do not write.** :mod:`.protocols` refuses, at import
   time, to define an adapter protocol carrying a method whose name would let
   this product send, archive, book, attest or pay anything in a system it
   does not own. That check is a module-level assertion, not a review note.

3. **A finding is not a decision.** Every ``ReviewFinding`` separates what was
   verified verbatim in a document from what the system proposes, carries its
   uncertainty explicitly, and stays ``open`` until a human approves,
   dismisses or corrects it.

Tenant isolation is inherited, not re-implemented: integration records live in
the tenant's own :class:`app.store.Store` directory, so there is no shared
collection to filter and ``registry.delete()`` sweeps them with everything
else.
"""

from .models import (
    Attachment,
    FindingStatus,
    FindingType,
    ImportStatus,
    InvoiceLine,
    InvoiceSnapshot,
    ReviewFinding,
    ReviewStatus,
    SourceEvent,
    SourceType,
    VerifiedFact,
    Verdict,
)
from .protocols import (
    FORBIDDEN_METHOD_STEMS,
    AccountingReadAdapter,
    MailImportAdapter,
    ReadOnlyAdapterError,
    assert_read_only,
)
from .store import IntegrationStore, SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "AccountingReadAdapter",
    "Attachment",
    "FORBIDDEN_METHOD_STEMS",
    "FindingStatus",
    "FindingType",
    "ImportStatus",
    "IntegrationStore",
    "InvoiceLine",
    "InvoiceSnapshot",
    "MailImportAdapter",
    "ReadOnlyAdapterError",
    "ReviewFinding",
    "ReviewStatus",
    "SourceEvent",
    "SourceType",
    "Verdict",
    "VerifiedFact",
    "assert_read_only",
]
