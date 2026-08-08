#!/usr/bin/env python3
"""Bygger mockup-sidor: ersätter {{i:Ikon}} med inline-SVG och {{sidebar:AKTIV}}
med den delade sidomenyn. Kör från designmappen: python3 build.py"""
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
ICONS = ROOT / "icons"
SRC = ROOT / "src"

MARK = (
    '<svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">'
    '<circle cx="11" cy="11" r="8.6" stroke="#37322F" stroke-width="2.1"/>'
    '<circle cx="11" cy="11" r="3.4" fill="#37322F"/></svg>'
)

NAV_GROUPS = [
    ("Fråga &amp; arkiv", [
        ("fraga", "MessageSquare", "Fråga dokumenten"),
        ("dokument", "Folders", "Dokument"),
    ]),
    ("Arbete", [
        ("granskning", "ClipboardCheck", "Granskning"),
        ("bevakningar", "CalendarClock", "Bevakningar"),
        ("uppgifter", "ClipboardList", "Uppgifter"),
    ]),
    ("Post &amp; ekonomi", [
        ("inkommande", "Inbox", "Inkommande"),
        ("fakturor", "Receipt", "Fakturor"),
    ]),
]


def icon(name: str) -> str:
    svg = (ICONS / f"{name}.svg").read_text().strip()
    return svg.replace("<svg ", '<svg class="ic" ', 1)


def sidebar(active: str) -> str:
    groups = []
    for group_label, items in NAV_GROUPS:
        rows = []
        for slug, ic, label in items:
            cls = "nav-item active" if slug == active else "nav-item"
            rows.append(f'<a class="{cls}" href="#">{icon(ic)}<span>{label}</span></a>')
        rows_html = "\n          ".join(rows)
        groups.append(
            f'<div class="nav-group">\n'
            f'        <div class="nav-label">{group_label}</div>\n'
            f'          {rows_html}\n'
            f'        </div>'
        )
    nav_html = "\n        ".join(groups)
    return f"""<aside class="sidebar">
      <div class="brand">{MARK}<span class="brand-name">Träff</span></div>
      <div class="scope">BRF Norra Stackholm</div>
      <nav class="nav">
        {nav_html}
      </nav>
      <div class="sidebar-foot">
        <div class="foot-name">Anders Andersson</div>
        <div class="foot-role">Styrelsemedlem</div>
        <div class="foot-logout">Logga ut</div>
      </div>
    </aside>"""


def build() -> None:
    for src in sorted(SRC.glob("*.html")):
        html = src.read_text()
        html = re.sub(r"\{\{i:([A-Za-z]+)\}\}", lambda m: icon(m.group(1)), html)
        html = re.sub(r"\{\{sidebar:([a-z]+)\}\}", lambda m: sidebar(m.group(1)), html)
        (ROOT / src.name).write_text(html)
        print(f"built {src.name}")


if __name__ == "__main__":
    build()
