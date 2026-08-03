"""What may appear inside a website field, checked rather than trusted.

Two things reach this module: HTML that the rich-text editor produced, and HTML
that a model produced. They are checked identically and by the same function,
because the moment those two paths differ, the weaker one is the one that gets
used.

**Fail closed, not "strip and hope".** A sanitiser that silently removes what it
does not recognise turns a bad input into a *quietly different* output — the
page ends up saying something nobody wrote and nobody reviewed. Everything here
refuses instead, with a Swedish sentence naming the offending tag or address.
That is affordable precisely because the whitelist below is not a guess: it is
the exact node and mark set the editor is configured with
(``@puckeditor/core``'s Tiptap extensions, mirrored in ``websiteConfig.jsx``).
Anything outside it did not come from the editor, and something that did not
come from the editor is exactly what should not be written without a look.

No third-party sanitiser is pulled in for this. The backend is offline by
design and the grammar being checked is a dozen tags wide.
"""

from __future__ import annotations

from html.parser import HTMLParser

# Structure and marks the editor can emit. h1 is absent on purpose: a page's
# first-level heading belongs to the page and its blocks' own heading fields, so
# allowing another one inside body text is how a published site ends up with
# four <h1>s and an unreadable outline for a screen reader.
ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "p", "br", "hr",
        "h2", "h3", "h4",
        "strong", "b", "em", "i", "u", "s",
        "code", "pre", "blockquote",
        "ul", "ol", "li",
        "a",
    }
)

VOID_TAGS: frozenset[str] = frozenset({"br", "hr"})

# Per-tag attribute whitelist. `style` is allowed only on block-level nodes and
# only for the one declaration the text-align extension writes — see
# _check_style.
ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "target", "rel", "title"}),
    "p": frozenset({"style"}),
    "h2": frozenset({"style"}),
    "h3": frozenset({"style"}),
    "h4": frozenset({"style"}),
}

ALLOWED_TEXT_ALIGN: frozenset[str] = frozenset({"left", "center", "right", "justify"})

# Address schemes a föreningssida legitimately needs. `http` is absent: a public
# page that links out over plaintext is a downgrade nobody chose, and every real
# destination a board links to answers on https.
ALLOWED_SCHEMES: frozenset[str] = frozenset({"https", "mailto", "tel"})

MAX_RICHTEXT_LENGTH = 20_000


class UnsafeContent(ValueError):
    """Content that will not be stored, with the reason in Swedish."""


def check_href(raw: str, *, what: str = "Länken") -> str:
    """Validate one destination. Returns it stripped; raises on anything else.

    Internal links are relative and start with ``/`` — they are resolved against
    the site's own pages by the renderer, so a link can never point at another
    association's site by accident.
    """
    href = (raw or "").strip()
    if not href:
        return ""
    if len(href) > 2048:
        raise UnsafeContent(f"{what} är orimligt lång.")
    if href.startswith("#"):
        return href
    if href.startswith("/"):
        if href.startswith("//"):
            # Protocol-relative: looks internal, is not.
            raise UnsafeContent(
                f"{what} börjar med '//', vilket pekar ut på nätet och inte på den egna sidan. "
                "Skriv hela adressen med https:// om det är meningen."
            )
        return href
    scheme, _, rest = href.partition(":")
    scheme = scheme.lower()
    if not rest:
        raise UnsafeContent(
            f"{what} saknar adress. Skriv en intern länk som börjar med '/' eller en "
            "fullständig adress som börjar med https://."
        )
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeContent(
            f"{what} använder {scheme!r}, som inte är tillåtet. Tillåtna: "
            f"{', '.join(sorted(ALLOWED_SCHEMES))}, eller en intern länk som börjar med '/'."
        )
    return href


def _check_style(tag: str, value: str) -> None:
    """Allow exactly ``text-align: <one of four>`` and nothing else."""
    for declaration in value.split(";"):
        declaration = declaration.strip()
        if not declaration:
            continue
        prop, _, val = declaration.partition(":")
        prop = prop.strip().lower()
        val = val.strip().lower()
        if prop != "text-align" or val not in ALLOWED_TEXT_ALIGN:
            raise UnsafeContent(
                f"<{tag}> har formatering som inte är tillåten ({declaration!r}). "
                "Endast textjustering får sättas som stil."
            )


class _Checker(HTMLParser):
    """Walks the document and raises on the first thing outside the whitelist."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.open_tags: list[str] = []
        self.text_length = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            raise UnsafeContent(
                f"<{tag}> får inte förekomma i text på webbplatsen. Tillåtna element: "
                f"{', '.join(sorted(ALLOWED_TAGS))}."
            )
        allowed = ALLOWED_ATTRS.get(tag, frozenset())
        for name, value in attrs:
            name = (name or "").lower()
            if name.startswith("on"):
                # The one case worth naming separately: an event handler is not
                # a formatting mistake, it is a script.
                raise UnsafeContent(
                    f"<{tag}> har en händelsehanterare ({name}). Skript lagras aldrig i "
                    "webbplatsens innehåll."
                )
            if name not in allowed:
                raise UnsafeContent(
                    f"<{tag}> har attributet {name!r}, som inte är tillåtet här."
                    + (f" Tillåtna: {', '.join(sorted(allowed))}." if allowed else "")
                )
            if name == "style":
                _check_style(tag, value or "")
            if name == "href":
                check_href(value or "", what=f"Länken i <{tag}>")
            if name == "target" and (value or "") not in ("_blank", "_self"):
                raise UnsafeContent(f"<{tag} target={value!r}> är inte tillåtet.")
        if tag not in VOID_TAGS:
            self.open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in VOID_TAGS:
            return
        if tag in self.open_tags:
            # Pop back to it: browsers and Tiptap both close implicitly nested
            # inline marks, and refusing that would fail on legitimate output.
            while self.open_tags and self.open_tags.pop() != tag:
                continue

    def handle_data(self, data: str) -> None:
        self.text_length += len(data)

    def handle_comment(self, data: str) -> None:
        raise UnsafeContent("HTML-kommentarer lagras inte i webbplatsens innehåll.")

    def handle_decl(self, decl: str) -> None:
        raise UnsafeContent("Dokumentdeklarationer hör inte hemma i ett textfält.")

    def handle_pi(self, data: str) -> None:
        raise UnsafeContent("Processinstruktioner hör inte hemma i ett textfält.")

    def unknown_decl(self, data: str) -> None:
        raise UnsafeContent("Otillåten HTML-konstruktion i ett textfält.")


def check_richtext(html: str, *, what: str = "Texten") -> str:
    """Validate rich text. Returns it unchanged, or raises :class:`UnsafeContent`.

    Returning the input verbatim rather than a cleaned copy is the contract: the
    bytes stored are the bytes the editor produced, so what is published is what
    was reviewed.
    """
    value = html or ""
    if len(value) > MAX_RICHTEXT_LENGTH:
        raise UnsafeContent(
            f"{what} är för lång ({len(value)} tecken, högst {MAX_RICHTEXT_LENGTH}). "
            "Dela upp den i flera block."
        )
    checker = _Checker()
    try:
        checker.feed(value)
        checker.close()
    except UnsafeContent:
        raise
    except Exception as exc:  # malformed beyond the parser's tolerance
        raise UnsafeContent(f"{what} går inte att tolka som text ({exc}).") from exc
    return value


def plain_text(html: str) -> str:
    """The readable text inside rich text, for grounding checks and summaries.

    Block-level tags become spaces so ``<p>12</p><p>000</p>`` cannot be read as
    the number 12000 — the grounding gate must see the two claims the reader
    sees, not an artefact of the markup.
    """
    parts: list[str] = []

    class _Text(HTMLParser):
        def handle_data(self, data: str) -> None:
            parts.append(data)

        def handle_starttag(self, tag: str, attrs) -> None:
            parts.append(" ")

        def handle_endtag(self, tag: str) -> None:
            parts.append(" ")

    parser = _Text(convert_charrefs=True)
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # a string that will be refused elsewhere anyway
        return html or ""
    return " ".join("".join(parts).split())


__all__ = [
    "ALLOWED_SCHEMES",
    "ALLOWED_TAGS",
    "MAX_RICHTEXT_LENGTH",
    "UnsafeContent",
    "check_href",
    "check_richtext",
    "plain_text",
]
