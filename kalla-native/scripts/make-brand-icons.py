#!/usr/bin/env python3
"""Generate the Träff launcher, adaptive, splash and favicon assets.

Every number here comes from the identity document ("Träff · visuell
identitet v2", §02 Geometrin and §08 Ikon och bruk) and matches
`src/theme/brand.ts`, so the icon and the in-app mark are the same mark:

    ring weight   8 % of the outer diameter
    core          46 % of the inner dimension, concentric
    mark diameter 52 % of the *visible* icon field

The icon always carries the BRAND mark — complete ◉, monochrome. §08 is
explicit that it never takes a state colour, "inte ens vid nya träffar":
the count goes in the badge, which Android draws itself.

Adaptive icons are the one place the two field definitions differ. The
foreground canvas is 108 dp but launchers only ever show the middle ~72 dp,
and §08 guarantees the safe zone at 66 dp of 108. So 52 % is taken of the
*visible* 72 dp, which lands the mark at 37.4 dp — comfortably inside the
66 dp guarantee no matter which mask the launcher applies.

Run:  python3 scripts/make-brand-icons.py
Needs ImageMagick 7 (`magick`).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

RING_WEIGHT = 0.08
CORE_OF_INNER = 0.46
ICON_FIELD = 0.52
ADAPTIVE_VISIBLE = 72 / 108
ADAPTIVE_SAFE = 66 / 108

SHELL = "#07080B"   # Skal — the base. Near-black, never pure black.
INK = "#ECEDEF"     # The mark on dark.
PAPER = "#E8E5DE"   # Papper — warm, for the light/print variant.
PAPER_INK = "#16181C"

# Supersample, then average down: a 4x render gives a genuinely round edge
# rather than ImageMagick's single-pass antialiasing on a hard stroke.
SS = 4

ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets" / "images"


def draw(out: pathlib.Path, canvas: int, diameter: float, ink: str, bg: str | None) -> None:
    """Render ◉ centred on `canvas`, with `diameter` as the mark's outer size."""
    weight = diameter * RING_WEIGHT
    inner = diameter - 2 * weight
    core_r = (CORE_OF_INNER * inner) / 2
    # A stroke straddles its path, so the path radius is half the diameter
    # less half the weight — that puts the stroke's OUTER edge on `diameter`.
    ring_r = (diameter - weight) / 2

    c = canvas * SS / 2
    background = f"xc:{bg}" if bg else "xc:none"

    subprocess.run(
        [
            "magick",
            "-size", f"{canvas * SS}x{canvas * SS}",
            background,
            "-fill", "none", "-stroke", ink, "-strokewidth", f"{weight * SS}",
            "-draw", f"circle {c},{c} {c},{c - ring_r * SS}",
            "-stroke", "none", "-fill", ink,
            "-draw", f"circle {c},{c} {c},{c - core_r * SS}",
            "-resize", f"{canvas}x{canvas}",
            "-depth", "8",
            "-strip",
            str(out),
        ],
        check=True,
    )
    print(f"  {out.name:34s} {canvas}px  mark {diameter:.1f}  ring {weight:.2f}  core {core_r * 2:.1f}")


def main() -> int:
    if not ASSETS.is_dir():
        print(f"missing {ASSETS}", file=sys.stderr)
        return 1

    print("Träff · brand assets")

    # Legacy square launcher icon: the whole square is the visible field.
    draw(ASSETS / "icon.png", 1024, 1024 * ICON_FIELD, INK, SHELL)

    # Adaptive foreground: 52 % of the visible 72 dp, on the 108 dp canvas.
    adaptive = 1024 * ICON_FIELD * ADAPTIVE_VISIBLE
    draw(ASSETS / "android-icon-foreground.png", 1024, adaptive, INK, None)

    # Themed ("monochrome") icons are tinted by the system, so this ships
    # pure white — §08 "Notisikon: enfärgad, vit".
    draw(ASSETS / "android-icon-monochrome.png", 1024, adaptive, "#FFFFFF", None)

    safe = 1024 * ADAPTIVE_SAFE
    assert adaptive < safe, "mark must sit inside the 66dp safe zone"
    print(f"  safe zone {safe:.0f}px, mark {adaptive:.0f}px — inside by {(safe - adaptive) / 2:.0f}px a side")

    subprocess.run(
        ["magick", "-size", "1024x1024", f"xc:{SHELL}", "-strip", str(ASSETS / "android-icon-background.png")],
        check=True,
    )
    print(f"  {'android-icon-background.png':34s} 1024px  solid {SHELL}")

    # Splash: the mark alone, rendered by expo-splash-screen at 76 dp wide.
    draw(ASSETS / "splash-icon.png", 512, 512 * 0.82, INK, None)

    draw(ASSETS / "favicon.png", 96, 96 * ICON_FIELD, INK, SHELL)

    # The inverted lockup mark for print/light surfaces (§05, §08).
    draw(ASSETS / "brand-mark-light.png", 512, 512 * ICON_FIELD, PAPER_INK, PAPER)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
