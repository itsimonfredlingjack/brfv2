"""Generate the synthetic integration fixtures, deterministically.

Run when the fixture content changes::

    cd backend && uv run python -m scripts.make_integration_fixtures

The `.eml` files under ``backend/fixtures/mail`` are committed, not generated at
test time, because a fixture that is rebuilt by the thing it tests proves less
each time it changes. This script exists so that regenerating them is a
reviewable, repeatable act rather than a hand-edited base64 blob.

Everything here is invented. The association, the suppliers, the org numbers
(deliberately outside the real Bolagsverket ranges' plausible use — they are
the same fictional numbers the demo corpus already uses), the addresses
(``.example`` and ``.invalid``, both reserved by RFC 2606) and the amounts.
No real person, company or document is represented.
"""

from __future__ import annotations

import sys
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
MAIL_DIR = ROOT / "fixtures" / "mail"

# Fixed clock: the fixtures must be byte-stable across regenerations.
_EPOCH = datetime(2026, 2, 3, 8, 14, 0, tzinfo=timezone(timedelta(hours=1)))

_PDF_META = {
    "creationDate": "D:20260203000000",
    "modDate": "D:20260203000000",
    "producer": "brf-fixture",
    "creator": "brf-fixture",
    "title": "",
    "author": "",
    "subject": "",
    "keywords": "",
}


def _invoice_pdf(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595.0, height=842.0)
    y = 72.0
    for line in lines:
        heading = line.startswith("# ")
        text = line[2:] if heading else line
        page.insert_text(
            fitz.Point(72.0, y),
            text,
            fontsize=12.5 if heading else 10.0,
            fontname="hebo" if heading else "helv",
        )
        y += (12.5 if heading else 10.0) * 1.6
    doc.set_metadata(_PDF_META)
    data = doc.tobytes(deflate=True, no_new_id=True)
    doc.close()
    return data


def _message(
    *,
    sender: str,
    sender_name: str,
    subject: str,
    body: str,
    when: datetime,
    ident: str,
    attachment: tuple[str, bytes] | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["From"] = f"{sender_name} <{sender}>"
    msg["To"] = "Styrelsen <styrelsen@gjutformen12.example>"
    msg["Subject"] = subject
    msg["Date"] = format_datetime(when)
    # Deterministic, not make_msgid(): that draws randomness and a fixture that
    # changes every time it is regenerated cannot be reviewed as a diff.
    msg["Message-ID"] = f"<{ident}@fixture.invalid>"
    msg.set_content(body)
    if attachment is not None:
        filename, data = attachment
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
        # Same reason: the default MIME boundary is random.
        msg.set_boundary(f"----brfv2-fixture-{ident}")
    return msg.as_bytes()


def build() -> list[Path]:
    MAIL_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # 1. The ordinary case: a supplier invoice with a PDF, matching a rate that
    #    the seeded snow-clearing contract states verbatim.
    written.append(
        _write(
            "faktura-snosvangen-2026-02.eml",
            _message(
                sender="faktura@snosvangen.example",
                sender_name="Snösvängen Entreprenad AB",
                subject="Faktura 2026-114 — snöröjning januari 2026",
                body=(
                    "Hej,\n\n"
                    "Bifogat finner ni faktura 2026-114 avseende utförd snöröjning under "
                    "januari 2026. Fakturan avser maskinell snöröjning med traktor, "
                    "4 timmar, enligt gällande avtal.\n\n"
                    "Vänliga hälsningar\n"
                    "Snösvängen Entreprenad AB\n"
                    "Fakturafrågor: faktura@snosvangen.example\n"
                ),
                when=_EPOCH,
                ident="snosvangen114",
                attachment=(
                    "faktura-2026-114.pdf",
                    _invoice_pdf(
                        [
                            "# FAKTURA 2026-114",
                            "Snösvängen Entreprenad AB, org.nr 556812-3344",
                            "Kund: Bostadsrättsföreningen Gjutformen 12, org.nr 769621-4455",
                            "Fakturadatum: 2026-02-03    Förfallodatum: 2026-03-05",
                            "Period: 2026-01-01 – 2026-01-31",
                            "",
                            "Maskinell snöröjning med traktor, 4 timmar a 1 250 kronor    5 000 kronor",
                            "Moms 25 procent                                              1 250 kronor",
                            "Att betala                                                   6 250 kronor",
                        ]
                    ),
                ),
            ),
        )
    )

    # 2. Same supplier, a rate that does NOT match the contract — the case that
    #    must come out as "möjlig avvikelse" and not as an accusation.
    written.append(
        _write(
            "faktura-snosvangen-2026-03-hojd-taxa.eml",
            _message(
                sender="faktura@snosvangen.example",
                sender_name="Snösvängen Entreprenad AB",
                subject="Faktura 2026-131 — snöröjning februari 2026",
                body=(
                    "Hej,\n\n"
                    "Bifogat faktura 2026-131 för februari. Observera att timtaxan för "
                    "maskinell snöröjning justerats.\n\n"
                    "Snösvängen Entreprenad AB\n"
                ),
                when=_EPOCH + timedelta(days=28),
                ident="snosvangen131",
                attachment=(
                    "faktura-2026-131.pdf",
                    _invoice_pdf(
                        [
                            "# FAKTURA 2026-131",
                            "Snösvängen Entreprenad AB, org.nr 556812-3344",
                            "Kund: Bostadsrättsföreningen Gjutformen 12, org.nr 769621-4455",
                            "Fakturadatum: 2026-03-03    Förfallodatum: 2026-04-02",
                            "Period: 2026-02-01 – 2026-02-28",
                            "",
                            "Maskinell snöröjning med traktor, 6 timmar a 1 450 kronor    8 700 kronor",
                            "Moms 25 procent                                              2 175 kronor",
                            "Att betala                                                  10 875 kronor",
                        ]
                    ),
                ),
            ),
        )
    )

    # 3. A message with no attachment at all — the queue must handle it.
    written.append(
        _write(
            "fraga-fran-medlem.eml",
            _message(
                sender="medlem@gjutformen12.example",
                sender_name="Medlem i föreningen",
                subject="Fråga om jourtid för snöröjning",
                body=(
                    "Hej styrelsen,\n\n"
                    "När på året gäller jouren för snöröjning? Trappan var hal i morse.\n\n"
                    "Hälsningar\n"
                ),
                when=_EPOCH + timedelta(days=1, hours=3),
                ident="medlemfraga",
            ),
        )
    )

    # 4. A message whose attachment is a type this version refuses. It exists so
    #    the refusal is exercised against a real file, not a hand-built blob.
    unsupported = EmailMessage()
    unsupported["From"] = "Leverantör AB <post@leverantor.example>"
    unsupported["To"] = "Styrelsen <styrelsen@gjutformen12.example>"
    unsupported["Subject"] = "Underlag i kalkylblad"
    unsupported["Date"] = format_datetime(_EPOCH + timedelta(days=2))
    unsupported["Message-ID"] = "<kalkyl@fixture.invalid>"
    unsupported.set_content("Underlaget ligger i bifogat kalkylblad.\n")
    unsupported.add_attachment(
        b"kolumn;varde\nsumma;1000\n",
        maintype="text",
        subtype="csv",
        filename="underlag.csv",
    )
    unsupported.set_boundary("----brfv2-fixture-kalkyl")
    written.append(_write("underlag-i-kalkylblad.eml", unsupported.as_bytes()))

    return written


def _write(name: str, data: bytes) -> Path:
    path = MAIL_DIR / name
    path.write_bytes(data)
    return path


def main() -> int:
    for path in build():
        print(f"{path.relative_to(ROOT)}  {len(path.read_bytes())} byte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
