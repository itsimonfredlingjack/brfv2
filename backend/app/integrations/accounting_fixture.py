"""A read-only accounting adapter backed by synthetic fixture files.

The payload it reads is shaped like a Swedish accounting system's supplier
invoice export — ``PascalCase`` keys, ``InvoiceRows``, a ``Total`` that includes
VAT — because the point of a fixture adapter is to prove that the *mapping*
works, and a mapping onto a shape nobody else uses proves nothing. A future
adapter for a real system replaces this file and the translation table in
:meth:`FixtureAccountingAdapter._to_snapshot`; it does not touch
:class:`~app.integrations.models.InvoiceSnapshot`, the review engine, the store
or the routes.

Nothing in this module names a vendor, needs a credential, opens a socket or
has a method that writes. The fixtures live under ``backend/fixtures/accounting``
and are read from disk with :meth:`Path.read_bytes`; there is no configuration
that can point it at a network location, because there is no network code to
point.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import InvoiceLine, InvoiceSnapshot, utc_now_iso

DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "accounting"

# The shape this adapter knows how to read. Version it, so a fixture written
# for a later mapping fails loudly instead of silently producing empty fields.
FIXTURE_SCHEMA = "brfv2-accounting-fixture/v1"


class FixtureError(ValueError):
    """A fixture file is missing, unreadable or not the shape this adapter reads."""


def _decimal(value: object) -> Decimal | None:
    """Parse an amount without going through float.

    Accepts the two forms an export realistically uses — a JSON number and a
    string — and the Swedish decimal comma, because a fixture that is supposed
    to look real will eventually contain one.
    """
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


class FixtureAccountingAdapter:
    """Satisfies :class:`~app.integrations.protocols.AccountingReadAdapter`.

    ``list_invoices`` and ``get_invoice`` take a ``tenant_id`` and it is used:
    each fixture declares which association it belongs to, and a reference from
    another tenant's dataset is a ``LookupError``, not someone else's invoice.
    The dataset is synthetic, so this is not the isolation that protects real
    data — that is the per-tenant store — but an adapter whose read is not
    tenant-scoped is a shape that becomes a leak the moment it is pointed at
    something real.
    """

    name = "fixture-accounting"

    def __init__(self, fixture_dir: str | Path | None = None) -> None:
        self.fixture_dir = Path(fixture_dir) if fixture_dir else DEFAULT_FIXTURE_DIR

    # ---------- reading ----------

    def _load_all(self) -> list[tuple[dict, str, str]]:
        """Every fixture as ``(payload, dataset name, payload sha256)``."""
        if not self.fixture_dir.is_dir():
            return []
        rows: list[tuple[dict, str, str]] = []
        for path in sorted(self.fixture_dir.glob("*.json")):
            raw = path.read_bytes()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise FixtureError(f"{path.name} är inte giltig JSON: {exc}") from exc
            if not isinstance(payload, dict) or payload.get("Schema") != FIXTURE_SCHEMA:
                raise FixtureError(
                    f"{path.name} saknar Schema == {FIXTURE_SCHEMA!r} och läses inte."
                )
            for invoice in payload.get("SupplierInvoices") or []:
                rows.append((invoice, path.name, hashlib.sha256(raw).hexdigest()))
        return rows

    def _for_tenant(self, tenant_id: str) -> list[tuple[dict, str, str]]:
        return [row for row in self._load_all() if row[0].get("AssociationRef") == tenant_id]

    def list_invoices(self, tenant_id: str) -> list[dict]:
        """Enough to choose one from a list, and nothing more."""
        return [
            {
                "external_ref": str(invoice.get("DocumentNumber") or ""),
                "supplier_name": str(invoice.get("SupplierName") or ""),
                "invoice_number": str(invoice.get("InvoiceNumber") or "") or None,
                "invoice_date": str(invoice.get("InvoiceDate") or "") or None,
                "due_date": str(invoice.get("DueDate") or "") or None,
                "total_amount": str(_decimal(invoice.get("Total")) or ""),
                "currency": str(invoice.get("Currency") or "SEK"),
                "adapter": self.name,
                "dataset": dataset,
            }
            for invoice, dataset, _ in self._for_tenant(tenant_id)
        ]

    def get_invoice(self, tenant_id: str, external_ref: str) -> InvoiceSnapshot:
        for invoice, dataset, digest in self._for_tenant(tenant_id):
            if str(invoice.get("DocumentNumber") or "") == external_ref:
                return self._to_snapshot(invoice, tenant_id, dataset, digest)
        raise LookupError(
            f"Fakturan {external_ref!r} finns inte i fixturunderlaget för {tenant_id!r}."
        )

    # ---------- mapping ----------

    def _to_snapshot(
        self, invoice: dict, tenant_id: str, dataset: str, digest: str
    ) -> InvoiceSnapshot:
        """The whole vendor-specific part of this adapter, in one method.

        Everything above and below this line is domain. A real adapter rewrites
        exactly this and inherits the rest.
        """
        period = invoice.get("Period") or {}
        lines = [
            InvoiceLine(
                description=str(row.get("Description") or ""),
                quantity=_decimal(row.get("DeliveredQuantity")),
                unit_price=_decimal(row.get("Price")),
                amount=_decimal(row.get("Total")),
                vat_amount=_decimal(row.get("VAT")),
            )
            for row in (invoice.get("InvoiceRows") or [])
        ]
        return InvoiceSnapshot(
            id=uuid.uuid4().hex[:12],
            tenant_id=tenant_id,
            adapter=self.name,
            external_ref=str(invoice.get("DocumentNumber") or ""),
            supplier_name=str(invoice.get("SupplierName") or ""),
            supplier_ref=str(invoice.get("SupplierOrgNo") or "") or None,
            invoice_number=str(invoice.get("InvoiceNumber") or "") or None,
            invoice_date=str(invoice.get("InvoiceDate") or "") or None,
            due_date=str(invoice.get("DueDate") or "") or None,
            period_start=str(period.get("From") or "") or None,
            period_end=str(period.get("To") or "") or None,
            total_amount=_decimal(invoice.get("Total")),
            currency=str(invoice.get("Currency") or "SEK"),
            vat_amount=_decimal(invoice.get("VAT")),
            lines=lines,
            retrieved_at=utc_now_iso(),
            source_dataset=dataset,
            content_sha256=digest,
        )
