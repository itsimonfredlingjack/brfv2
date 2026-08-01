#!/usr/bin/env python3
"""Remove from the staged runtime everything ops/forbidden_providers.json forbids.

Called by ops/build-runtime.sh after the locked wheels are installed and the
product code is copied in. It removes; it never certifies. Whether the removal
worked is answered afterwards by ops/inspect_payload.py, which looks at the
tree rather than at this script's intentions — so a pattern that silently
matched nothing here shows up there as a finding, not as a success.

Three kinds of thing have to go, and each needs its own mechanism:

  packages + metadata   a distribution is its package directory AND its
                        .dist-info; deleting only the importable half leaves
                        the payload claiming to contain software it does not.
  module subtrees       huggingface_hub ships a hosted inference client and a
                        registry of ~20 third-party inference-provider
                        adapters inside a package the approved embedder needs.
                        The subtree goes, the package stays.
  registrations         an entry point is loadable without anyone importing
                        it by name, so a stale one pointing into a removed
                        subtree is a live registration for code that is gone.
                        Removing it means rewriting the distribution's RECORD,
                        or the metadata still describes a file that changed.

Idempotent; safe to re-run.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = json.loads((ROOT / "ops" / "forbidden_providers.json").read_text(encoding="utf-8"))


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def record_hash(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}", len(data)


def rewrite_record(dist_info: Path, site: Path, changed: set[str]) -> bool:
    """Keep RECORD honest after files under the distribution changed or went away.

    A RECORD that still lists a deleted file, or the old hash of a rewritten
    one, is exactly the kind of metadata/reality mismatch this repair exists to
    remove — so it is corrected here rather than left as a smaller version of
    the same defect.

    Deletions need no argument: a line whose file is not on disk is dropped,
    which is the same answer however the file came to be missing.
    """
    record = dist_info / "RECORD"
    if not record.is_file():
        return False
    out: list[str] = []
    touched = False
    for line in record.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name = line.split(",", 1)[0]
        if not (site / name).exists():
            touched = True
            continue
        if name in changed:
            digest, size = record_hash(site / name)
            out.append(f"{name},{digest},{size}")
            touched = True
            continue
        out.append(line)
    if touched:
        record.write_text("\n".join(out) + "\n", encoding="utf-8")
    return touched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path)
    args = parser.parse_args()
    runtime: Path = args.runtime.resolve()

    site_candidates = sorted((runtime / "python" / "lib").glob("python3.*/site-packages"))
    if not site_candidates:
        print("FEL: hittade inga site-packages i körmiljön", file=sys.stderr)
        return 1
    site = site_candidates[0]
    backend = runtime / "backend"

    removed_report: list[str] = []

    def drop(path: Path, note: str) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
        else:
            return
        removed_report.append(f"{note}: {path.relative_to(runtime).as_posix()}")

    # --- distributions: package directory + every metadata directory --------
    forbidden_dists = {normalize(item["name"]) for item in RULES["distributions"]}
    for meta in sorted(site.glob("*.dist-info")) + sorted(site.glob("*.egg-info")):
        # `{name}-{version}.dist-info` — strip the suffix BEFORE splitting off
        # the version, or the hyphen in "dist-info" is the one that splits.
        stem = re.sub(r"\.(dist|egg)-info$", "", meta.name)
        stem = stem.rsplit("-", 1)[0] if "-" in stem else stem
        if normalize(stem) in forbidden_dists:
            drop(meta, "distributionsmetadata")
    for name in sorted(forbidden_dists):
        for candidate in (name, name.replace("-", "_")):
            drop(site / candidate, "paket")
            drop(site / f"{candidate}.py", "modul")
    # pkg_resources ships with setuptools and is the same runtime-install
    # machinery under another name.
    drop(site / "pkg_resources", "paket")

    # --- module subtrees inside packages that stay -------------------------
    # Only the hosted inference surface: huggingface_hub itself is required by
    # the approved embedder and is left intact.
    drop(site / "huggingface_hub" / "inference", "hostad inferens-subtree")
    drop(site / "huggingface_hub" / "inference_api.py", "hostad inferensmodul")

    # --- the repository's own hosted plug-in -------------------------------
    # backend/app is copied wholesale; the hosted providers are removed here so
    # the packaged app.llm finds no plug-in to register.
    drop(backend / "app" / "llm_hosted.py", "hostad leverantörsplugin")

    # --- bytecode for everything removed above -----------------------------
    for cache in sorted(runtime.rglob("__pycache__")):
        if cache.is_dir():
            shutil.rmtree(cache)

    # --- registrations -----------------------------------------------------
    entry_pattern = re.compile(RULES["entryPointPatterns"][0]["pattern"])
    for entry_points in sorted(site.glob("*.dist-info/entry_points.txt")):
        text = entry_points.read_text(encoding="utf-8")
        group = ""
        kept: list[str] = []
        dropped: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                group = stripped[1:-1]
                kept.append(line)
                continue
            if stripped and not stripped.startswith("#") and entry_pattern.search(f"[{group}] {stripped}"):
                dropped.append(f"[{group}] {stripped}")
                continue
            kept.append(line)
        if not dropped:
            continue
        new_text = "\n".join(kept).rstrip("\n") + "\n"
        entry_points.write_text(new_text, encoding="utf-8")
        rel = entry_points.relative_to(site).as_posix()
        rewrite_record(entry_points.parent, site, changed={rel})
        for item in dropped:
            removed_report.append(f"registrering: {entry_points.parent.name} {item}")

    # --- RECORD entries for files that are gone ----------------------------
    # Every distribution, not only the ones touched above: removing
    # huggingface_hub/inference/ left its own distribution's RECORD listing
    # files that no longer exist.
    for record in sorted(site.glob("*.dist-info/RECORD")):
        rewrite_record(record.parent, site, changed=set())

    for line in removed_report:
        print(f"  borttaget  {line}")
    print(f"  {len(removed_report)} objekt borttagna ur den stegade körmiljön")
    return 0


if __name__ == "__main__":
    sys.exit(main())
