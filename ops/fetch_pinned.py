#!/usr/bin/env python3
"""Materialize a pinned build input from ops/pins.json, verifying the bytes.

The cache is an efficiency device, never an authority: a cached file is used
only after its SHA-256 matches the pin, and a file that fails verification is
discarded and re-fetched rather than repaired. Nothing here trusts a filename,
a modification time, or the fact that something was already on disk.

    ops/fetch_pinned.py python                 -> prints the archive path
    ops/fetch_pinned.py uv                     -> prints the uv binary path
    ops/fetch_pinned.py embedder <target-dir>  -> fills target-dir, prints it
    ops/fetch_pinned.py manifest               -> prints the verified manifest

Stdlib only, and deliberately runnable by the system interpreter: it has to
work before any project interpreter exists.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS = json.loads((ROOT / "ops" / "pins.json").read_text(encoding="utf-8"))

# Overridable so a build can be pointed at a pre-populated cache (an air-gapped
# builder, CI); the verification below is identical either way.
CACHE = Path(
    os.environ.get("BRFV2_BUILD_CACHE") or Path.home() / ".cache" / "brfv2-desktop-build"
)

CHUNK = 1024 * 1024


def log(message: str) -> None:
    print(f"  {message}", file=sys.stderr)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_verified(url: str, sha256: str, destination: Path, *, label: str) -> Path:
    """Return ``destination`` holding exactly the bytes ``sha256`` names."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        found = sha256_of(destination)
        if found == sha256:
            log(f"{label}: cache verifierad ({sha256[:16]}…)")
            return destination
        log(f"{label}: cachen matchar inte pinnen ({found[:16]}… ≠ {sha256[:16]}…) — hämtar om")
        destination.unlink()

    log(f"{label}: hämtar {url}")
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as tmp:
        temp_path = Path(tmp.name)
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                shutil.copyfileobj(response, tmp, CHUNK)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    found = sha256_of(temp_path)
    if found != sha256:
        temp_path.unlink(missing_ok=True)
        raise SystemExit(
            f"FEL: {label} har fel SHA-256.\n"
            f"  förväntat: {sha256}\n"
            f"  hämtat:    {found}\n"
            f"  källa:     {url}"
        )
    os.replace(temp_path, destination)
    log(f"{label}: hämtad och verifierad ({sha256[:16]}…)")
    return destination


def python_archive() -> Path:
    pin = PINS["python"]
    return fetch_verified(
        pin["url"],
        pin["sha256"],
        CACHE / "python" / pin["archive"],
        label=f"CPython {pin['version']}+{pin['build']}",
    )


def uv_binary() -> Path:
    """The pinned uv, extracted once into the cache and re-verified each run."""

    pin = PINS["uv"]
    archive = fetch_verified(
        pin["url"],
        pin["sha256"],
        CACHE / "uv" / pin["archive"],
        label=f"uv {pin['version']}",
    )
    target = CACHE / "uv" / pin["version"] / "uv"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            member = next(m for m in tar.getmembers() if Path(m.name).name == "uv" and m.isfile())
            with tar.extractfile(member) as source, tempfile.NamedTemporaryFile(
                dir=target.parent, delete=False
            ) as tmp:
                shutil.copyfileobj(source, tmp, CHUNK)
            os.replace(tmp.name, target)
        target.chmod(0o755)

    reported = subprocess.run(
        [str(target), "--version"], capture_output=True, text=True, check=True
    ).stdout.split()
    if pin["version"] not in reported:
        raise SystemExit(
            f"FEL: den uppackade uv-binären rapporterar {' '.join(reported)}, "
            f"inte den pinnade {pin['version']}."
        )
    return target


def embedder(target_dir: Path) -> Path:
    """Fill ``target_dir`` with exactly the pinned files, all verified.

    Real files, not links into a shared cache: the bundle is copied to another
    machine, and a symlink into somebody's home directory does not survive that.
    """

    pin = PINS["embedder"]
    cache_dir = CACHE / "models" / pin["repoId"].replace("/", "--") / pin["revision"]
    target_dir.mkdir(parents=True, exist_ok=True)
    for name, expected in sorted(pin["files"].items()):
        url = pin["urlTemplate"].format(
            repoId=pin["repoId"], revision=pin["revision"], file=name
        )
        cached = fetch_verified(
            url,
            expected["sha256"],
            cache_dir / name,
            label=f"{pin['repoId']}@{pin['revision'][:8]}/{name}",
        )
        size = cached.stat().st_size
        if size != expected["bytes"]:
            raise SystemExit(
                f"FEL: {name} är {size} byte, pinnen säger {expected['bytes']}."
            )
        shutil.copyfile(cached, target_dir / name)
    return target_dir


def manifest() -> dict:
    """What was verified, in the form the evidence and BUNDLE.json record."""

    pin = PINS["embedder"]
    return {
        "schema": PINS["schema"],
        "python": {
            "implementation": PINS["python"]["implementation"],
            "version": PINS["python"]["version"],
            "build": PINS["python"]["build"],
            "distribution": PINS["python"]["distribution"],
            "archive": PINS["python"]["archive"],
            "url": PINS["python"]["url"],
            "sha256": PINS["python"]["sha256"],
            "verifiedBy": "ops/fetch_pinned.py python (SHA-256 före uppackning)",
        },
        "uv": {
            "version": PINS["uv"]["version"],
            "url": PINS["uv"]["url"],
            "sha256": PINS["uv"]["sha256"],
            "verifiedBy": "ops/fetch_pinned.py uv (SHA-256 + uv --version)",
        },
        "embedder": {
            "repoId": pin["repoId"],
            "revision": pin["revision"],
            "urlTemplate": pin["urlTemplate"],
            "files": {name: dict(meta) for name, meta in sorted(pin["files"].items())},
            "verifiedBy": "ops/fetch_pinned.py embedder (SHA-256 + storlek per fil)",
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    what = argv[1]
    if what == "python":
        print(python_archive())
    elif what == "uv":
        print(uv_binary())
    elif what == "embedder":
        if len(argv) < 3:
            print("ops/fetch_pinned.py embedder <target-dir>", file=sys.stderr)
            return 2
        print(embedder(Path(argv[2])))
    elif what == "manifest":
        print(json.dumps(manifest(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"okänt argument: {what}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
