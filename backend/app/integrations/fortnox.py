"""Read-only Fortnox: supplier invoices out of a live company, and nothing back.

The mapping is the whole adapter. Everything above it —
:class:`~app.integrations.models.InvoiceSnapshot`, the review engine, the
store, the routes — is the same code the fixture adapter feeds, which is what
the fixture adapter was for.

**Read-only, and honest about how.** Fortnox scopes are not read/write
separated: ``supplierinvoice`` grants both, and there is no narrower scope to
ask for. So the read-only guarantee here is *client-side*, and it is made of
three things that can each be checked:

1. this module contains no write verb — the adapter has ``list_invoices``,
   ``get_invoice`` and ``mapping_preview``, and :mod:`.protocols` refuses a
   protocol that grows one that writes;
2. :class:`~app.integrations.egress.ReadOnlyEgress` has no method that can
   issue a PUT, PATCH, DELETE or an API POST at all — the single POST it owns
   is bound to the authority host and the token path;
3. the test suite asserts both, and asserts that no request this module makes
   is anything but a GET.

What that does **not** give is a promise the token could not be misused by
other software with access to it. That is why the connection is made by a named
administrator, why the credential lives in the tenant's ``0600`` secret file
and out of every backup, and why the honest recommendation — recorded in
``docs/INTEGRATION-FORTNOX.md`` — is to connect a Fortnox user whose own
permissions are limited to reading supplier invoices. A scope cannot be the
last line of defence when the provider does not offer a read-only one.

**Never a bookkeeping state.** ``Booked``, ``Cancelled``, ``Balance`` and the
voucher fields are read and shown, and none of them is ever sent anywhere. The
product has no code path that books, attests, pays or changes a status, which
is enforced by there being no such method rather than by anyone remembering.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from .egress import EgressPolicy, ReadOnlyEgress, read_json
from .models import InvoiceLine, InvoiceSnapshot, utc_now_iso

logger = logging.getLogger("brf.integrations.fortnox")

PROVIDER = "fortnox"

API_HOST = "api.fortnox.se"
AUTHORITY_HOST = "apps.fortnox.se"
API_BASE = f"https://{API_HOST}/3"
AUTHORIZE_PATH = "/oauth-v1/auth"
TOKEN_PATH = "/oauth-v1/token"

# The scopes this product asks Fortnox for.
#
#   supplierinvoice   the supplier invoices being reviewed
#   companyinformation  the company name, so the connection can say which
#                     Fortnox company it is reading — a board that cannot see
#                     that cannot tell a misconnected integration from a
#                     correct one
#
# `supplier` is NOT in the base set. It buys a stronger anchor (the supplier's
# organisation number, which is unambiguous where a name is not) at the cost of
# read access to the whole supplier register, so it is opt-in per installation
# and named as a trade-off in the UI rather than switched on quietly.
BASE_SCOPES: tuple[str, ...] = ("supplierinvoice", "companyinformation")
SUPPLIER_SCOPE = "supplier"

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

_GIVEN_NUMBER_RE = re.compile(r"^[0-9]{1,12}$")


def policy() -> EgressPolicy:
    return EgressPolicy(
        provider=PROVIDER,
        api_hosts=frozenset({API_HOST}),
        authority_host=AUTHORITY_HOST,
        token_paths=(TOKEN_PATH,),
    )


class FortnoxConfigError(ValueError):
    """The Fortnox configuration is not usable, and the message says why."""


@dataclass(frozen=True)
class FortnoxConfig:
    """What an installation needs to reach one Fortnox company.

    ``client_id`` and the secret come from a Fortnox *developer* application —
    the integration's identity, not the association's. ``redirect_uri`` must be
    the one registered on that application, because Fortnox compares it exactly
    and the operator pastes the code back from wherever it lands.
    """

    client_id: str
    redirect_uri: str
    read_supplier_register: bool = False

    def validated(self) -> "FortnoxConfig":
        client_id = self.client_id.strip()
        if not client_id:
            raise FortnoxConfigError("Klient-id från Fortnox-appen saknas.")
        if len(client_id) > 200 or not re.fullmatch(r"[A-Za-z0-9._~-]+", client_id):
            raise FortnoxConfigError("Klient-id ser inte ut som ett Fortnox-klient-id.")
        redirect = self.redirect_uri.strip()
        if not redirect.startswith("https://") and not redirect.startswith("http://localhost"):
            raise FortnoxConfigError(
                "Redirect-URI måste vara https (eller http://localhost vid utveckling) "
                "och exakt den som är registrerad på Fortnox-appen."
            )
        return FortnoxConfig(
            client_id=client_id,
            redirect_uri=redirect,
            read_supplier_register=bool(self.read_supplier_register),
        )

    def scopes(self) -> tuple[str, ...]:
        return BASE_SCOPES + ((SUPPLIER_SCOPE,) if self.read_supplier_register else ())

    def public(self) -> dict:
        return {
            "clientId": self.client_id,
            "redirectUri": self.redirect_uri,
            "readSupplierRegister": self.read_supplier_register,
            "scopes": list(self.scopes()),
        }


def _decimal(value: object) -> Decimal | None:
    """Parse an amount without going through float. Same rule as the fixture adapter."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _text(value: object) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class FieldMapping:
    """One line of the translation table, and of the preview built from it.

    ``sources`` is tried in order; the first that yields a value wins. Keeping
    the order here rather than in a chain of ``or`` expressions is what lets
    :meth:`FortnoxAccountingAdapter.mapping_preview` tell an operator *which*
    Fortnox field a number actually came from — the question that decides
    whether a first live connection is trustworthy or merely plausible.
    """

    target: str
    label: str
    sources: tuple[str, ...]
    convert: Callable[[object], Any]
    note: str = ""


INVOICE_FIELDS: tuple[FieldMapping, ...] = (
    FieldMapping("external_ref", "Referens i Fortnox", ("GivenNumber",), _text),
    FieldMapping("supplier_name", "Leverantör", ("SupplierName",), _text),
    FieldMapping("supplier_ref", "Leverantörsnummer", ("SupplierNumber",), _text),
    FieldMapping("invoice_number", "Fakturanummer", ("InvoiceNumber", "ExternalInvoiceNumber"), _text),
    FieldMapping("invoice_date", "Fakturadatum", ("InvoiceDate",), _text),
    FieldMapping("due_date", "Förfallodatum", ("DueDate", "FinalPayDate"), _text),
    FieldMapping("total_amount", "Totalbelopp inkl. moms", ("Total",), _decimal),
    FieldMapping("vat_amount", "Varav moms", ("VAT",), _decimal),
    FieldMapping("currency", "Valuta", ("Currency",), _text),
)

ROW_FIELDS: tuple[FieldMapping, ...] = (
    FieldMapping("description", "Radtext", ("Description", "ArticleNumber", "Account"), _text),
    FieldMapping("quantity", "Antal", ("Quantity",), _decimal),
    FieldMapping("unit_price", "À-pris", ("Price",), _decimal),
    FieldMapping(
        "amount",
        "Radbelopp",
        ("Total", "Debit"),
        _decimal,
        note="Fortnox konterar leverantörsfakturarader; Debit är kostnadssidan.",
    ),
)

# Read and shown, never sent. Listed explicitly so the preview can say out loud
# that the product saw a bookkeeping state and did nothing with it.
OBSERVED_ONLY = ("Booked", "Cancelled", "Balance", "VoucherNumber", "VoucherSeries", "VoucherYear")

# What Fortnox's supplier invoice simply does not carry.
ABSENT_FIELDS = {
    "period_start": "Fortnox leverantörsfaktura har inget periodfält — periodgranskning görs inte för den här källan.",
    "period_end": "Fortnox leverantörsfaktura har inget periodfält — periodgranskning görs inte för den här källan.",
}


def _apply(mapping: FieldMapping, payload: dict) -> tuple[Any, str]:
    for source in mapping.sources:
        if source in payload and payload.get(source) not in (None, ""):
            value = mapping.convert(payload.get(source))
            if value not in (None, ""):
                return value, source
    return None, ""


class FortnoxAccountingAdapter:
    """Satisfies :class:`~app.integrations.protocols.AccountingReadAdapter`.

    Constructed per request with a live access token, exactly like the Graph
    adapter and for the same reason: an object that could refresh its own
    credential is an object that can keep reading after consent is withdrawn.
    """

    name = PROVIDER

    def __init__(
        self,
        config: FortnoxConfig,
        *,
        access_token: str,
        egress: ReadOnlyEgress | None = None,
    ) -> None:
        self.config = config.validated()
        self._token = access_token
        self.egress = egress or ReadOnlyEgress(policy=policy())

    # ---------- reads ----------

    def _get(self, path: str) -> Any:
        reply = self.egress.get(f"{API_BASE}{path}", access_token=self._token)
        return read_json(reply, provider=PROVIDER)

    def account_label(self) -> str:
        """Which Fortnox company this connection reads."""
        try:
            payload = self._get("/companyinformation")
        except Exception as exc:  # a label is nice to have, never load-bearing
            logger.info("Kunde inte läsa företagsnamn från Fortnox: %s", exc)
            return ""
        info = (payload or {}).get("CompanyInformation") or {}
        name = _text(info.get("CompanyName"))
        org = _text(info.get("OrganizationNumber"))
        return f"{name} ({org})" if name and org else name or org

    def list_invoices(self, tenant_id: str, *, limit: int = DEFAULT_PAGE_SIZE) -> list[dict]:
        """Enough to choose one from a list, and nothing more.

        ``tenant_id`` is not sent to Fortnox and could not be: the company is
        whichever one authorised this connection. It is in the signature
        because the protocol has it, and because an adapter whose read is not
        tenant-scoped in *shape* becomes a leak the day it is pointed at
        something multi-company.
        """
        size = max(1, min(int(limit), MAX_PAGE_SIZE))
        payload = self._get(f"/supplierinvoices?limit={size}&sortby=givennumber&sortorder=descending")
        rows: list[dict] = []
        for entry in (payload or {}).get("SupplierInvoices") or []:
            if not isinstance(entry, dict):
                continue
            rows.append(
                {
                    "external_ref": _text(entry.get("GivenNumber")),
                    "supplier_name": _text(entry.get("SupplierName")),
                    "invoice_number": _text(entry.get("InvoiceNumber")) or None,
                    "invoice_date": _text(entry.get("InvoiceDate")) or None,
                    "due_date": _text(entry.get("DueDate")) or None,
                    "total_amount": str(_decimal(entry.get("Total")) or ""),
                    "currency": _text(entry.get("Currency")) or "SEK",
                    "adapter": self.name,
                    "dataset": "fortnox:supplierinvoices",
                    # Read and shown so a reviewer knows the state in the
                    # accounting system. This product never changes it.
                    "booked": bool(entry.get("Booked")),
                    "cancelled": bool(entry.get("Cancelled")),
                }
            )
        return rows

    def _fetch_invoice(self, external_ref: str) -> dict:
        ref = external_ref.strip()
        if not _GIVEN_NUMBER_RE.fullmatch(ref):
            raise LookupError(f"{external_ref!r} är inte ett Fortnox-dokumentnummer.")
        payload = self._get(f"/supplierinvoices/{ref}")
        invoice = (payload or {}).get("SupplierInvoice")
        if not isinstance(invoice, dict):
            raise LookupError(f"Fakturan {ref} finns inte i Fortnox.")
        return invoice

    def get_invoice(self, tenant_id: str, external_ref: str) -> InvoiceSnapshot:
        invoice = self._fetch_invoice(external_ref)
        return self._to_snapshot(invoice, tenant_id)

    def mapping_preview(self, tenant_id: str, external_ref: str) -> dict:
        """Which Fortnox field became which of ours, with both values.

        This exists because the first live connection is the one moment the
        mapping can actually be checked, and "the amounts looked right" is not
        checking. A person compares this table against the invoice in Fortnox
        once, and after that the mapping is a verified fact rather than a
        confident assumption in a source file.
        """
        invoice = self._fetch_invoice(external_ref)
        fields = []
        for mapping in INVOICE_FIELDS:
            value, source = _apply(mapping, invoice)
            fields.append(
                {
                    "target": mapping.target,
                    "label": mapping.label,
                    "sourceField": source or " / ".join(mapping.sources),
                    "matched": bool(source),
                    "value": str(value) if value is not None else None,
                    "note": mapping.note,
                }
            )
        for target, why in ABSENT_FIELDS.items():
            fields.append(
                {
                    "target": target,
                    "label": target,
                    "sourceField": "",
                    "matched": False,
                    "value": None,
                    "note": why,
                }
            )
        observed = {key: invoice.get(key) for key in OBSERVED_ONLY if key in invoice}
        return {
            "adapter": self.name,
            "externalRef": _text(invoice.get("GivenNumber")),
            "fields": fields,
            "rows": [
                [
                    {
                        "target": m.target,
                        "label": m.label,
                        "sourceField": _apply(m, row)[1] or " / ".join(m.sources),
                        "value": (lambda v: str(v) if v is not None else None)(_apply(m, row)[0]),
                    }
                    for m in ROW_FIELDS
                ]
                for row in (invoice.get("SupplierInvoiceRows") or [])
                if isinstance(row, dict)
            ],
            "observedNotChanged": observed,
            "note": (
                "Fälten läses ur Fortnox och skrivs aldrig tillbaka. Bokförings- och "
                "annulleringsstatus visas men ändras inte av den här produkten."
            ),
        }

    # ---------- mapping ----------

    def _supplier_org_number(self, supplier_number: str) -> str:
        """The supplier's organisation number, when the register may be read.

        Worth having because it anchors a review on something unambiguous: two
        companies can share a trading name, and none share an organisation
        number. Silent about failure on purpose — a missing org number weakens
        an anchor, and must never fail an invoice read.
        """
        if not (self.config.read_supplier_register and supplier_number):
            return ""
        try:
            payload = self._get(f"/suppliers/{supplier_number}")
        except Exception as exc:
            logger.info("Kunde inte läsa leverantör %s: %s", supplier_number, exc)
            return ""
        supplier = (payload or {}).get("Supplier") or {}
        return _text(supplier.get("OrganisationNumber"))

    def _to_snapshot(self, invoice: dict, tenant_id: str) -> InvoiceSnapshot:
        """The whole vendor-specific part, driven by the same table as the preview."""
        import hashlib
        import json as _json

        values: dict[str, Any] = {}
        for mapping in INVOICE_FIELDS:
            value, _ = _apply(mapping, invoice)
            values[mapping.target] = value

        lines: list[InvoiceLine] = []
        for row in invoice.get("SupplierInvoiceRows") or []:
            if not isinstance(row, dict):
                continue
            row_values = {m.target: _apply(m, row)[0] for m in ROW_FIELDS}
            if not any(v not in (None, "") for v in row_values.values()):
                continue
            lines.append(
                InvoiceLine(
                    description=str(row_values.get("description") or ""),
                    quantity=row_values.get("quantity"),
                    unit_price=row_values.get("unit_price"),
                    amount=row_values.get("amount"),
                )
            )

        supplier_ref = str(values.get("supplier_ref") or "")
        org_number = self._supplier_org_number(supplier_ref)
        if org_number:
            # Both, not one: the Fortnox supplier number is what a person finds
            # the record by over there, and the organisation number is what
            # anchors the review here.
            supplier_ref = f"{supplier_ref} · {org_number}" if supplier_ref else org_number

        digest = hashlib.sha256(
            _json.dumps(invoice, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()

        return InvoiceSnapshot(
            id=uuid.uuid4().hex[:12],
            tenant_id=tenant_id,
            adapter=self.name,
            external_ref=str(values.get("external_ref") or ""),
            supplier_name=str(values.get("supplier_name") or ""),
            supplier_ref=supplier_ref or None,
            invoice_number=str(values.get("invoice_number") or "") or None,
            invoice_date=str(values.get("invoice_date") or "") or None,
            due_date=str(values.get("due_date") or "") or None,
            period_start=None,
            period_end=None,
            total_amount=values.get("total_amount"),
            currency=str(values.get("currency") or "SEK"),
            vat_amount=values.get("vat_amount"),
            lines=lines,
            retrieved_at=utc_now_iso(),
            source_dataset="fortnox:supplierinvoices",
            content_sha256=digest,
        )


__all__ = [
    "ABSENT_FIELDS",
    "API_BASE",
    "API_HOST",
    "AUTHORITY_HOST",
    "AUTHORIZE_PATH",
    "BASE_SCOPES",
    "FortnoxAccountingAdapter",
    "FortnoxConfig",
    "FortnoxConfigError",
    "INVOICE_FIELDS",
    "OBSERVED_ONLY",
    "PROVIDER",
    "ROW_FIELDS",
    "SUPPLIER_SCOPE",
    "TOKEN_PATH",
    "policy",
]
