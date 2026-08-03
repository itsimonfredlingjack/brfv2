"""Which rules produced a finding — and a check that the number says so.

:data:`app.invoices.models.ANALYSIS_ENGINE_VERSION` is stamped on every
recorded analysis run, and it is the one thing on a case that says *a finding
from before this date was written by different rules*. It was bumped by hand,
which means it could be forgotten by hand — and a forgotten bump does not
degrade gracefully: it silently asserts that two conclusions written under
different rules were written under the same ones. The analysis history stops
being a record and becomes a plausible-looking guess.

So the rules are fingerprinted, and the fingerprint is locked to the version
that was current when it was taken (:data:`LOCK_PATH`). Change a rule without
bumping the version and ``tests/test_invoice_rules_version.py`` fails, naming
the module whose rules moved.

**What counts as a rule.** The modules that decide what a finding *says*:

* :mod:`app.integrations.review` — invoice against a cited contract passage,
* :mod:`app.invoices.compare` — invoice against the association's own history,
* :mod:`app.integrations.supplier` — which document may be used as evidence
  about which supplier, and how firmly, which is what a finding's caveat is
  made of,
* :mod:`app.terms` — the contract clauses that are read but not compared,
* and the label tables in :mod:`app.integrations.models` that put the verdicts
  into words, because a reworded verdict is a changed conclusion to the person
  reading it.

**What deliberately does not count**, and why the version is still honest
without it:

* Retrieval, extraction and :func:`app.citations.resolve_citation`. A change
  there can certainly change what a finding says — and when it does, the audit
  trail already records a new version, because :func:`app.invoices.audit.build_run`
  triggers on the *result* differing as well as on the rules differing. The
  engine version answers the narrower question those two triggers cannot:
  which rules wrote this, for a finding whose text happens not to have changed.
* :func:`app.invoices.cases.signals_for` and the signal labels. Signals are
  recomputed on every read and never stamped, so an old signal is never shown
  beside a new one.

**Why the fingerprint is structural rather than a file hash.** It is taken over
the parsed syntax with docstrings removed, so reformatting a rule module or
rewriting its documentation — both of which happen often and change nothing
about what the engine says — does not demand a version bump that would then
mean nothing. String literals *are* in it: the verdict wording is what a board
member reads.

Regenerate the lock after a deliberate rule change::

    backend/.venv/bin/python -m app.invoices.rules --write     # or: make invoice-rules-lock

:func:`record` refuses to rewrite an existing version's entry with a different
fingerprint. That refusal is the automation: the only way to a green suite
after changing a rule is to bump :data:`ANALYSIS_ENGINE_VERSION` first.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

# `app.integrations` first, deliberately. The two packages reference each
# other's models, and the cycle only resolves when the integrations side is
# entered first — which every other caller does implicitly and `python -m
# app.invoices.rules` would not. Naming the order here keeps the operator entry
# point working without rearranging either package for a tool's convenience.
from ..integrations import models as _integration_models  # noqa: F401
from .models import ANALYSIS_ENGINE_VERSION

# `app/invoices/rules.py` → backend/. Every path below is relative to it, so
# the lock reads the same on any checkout and a fingerprint taken over a
# throwaway copy of the tree (which is how the tripwire proves itself) is
# comparable with one taken over the real one.
BACKEND = Path(__file__).resolve().parents[2]

LOCK_PATH = BACKEND / "app" / "invoices" / "RULES.lock.json"

# Whole modules whose purpose is to decide what a finding says.
RULE_MODULES: tuple[str, ...] = (
    "app/integrations/review.py",
    "app/integrations/supplier.py",
    "app/invoices/compare.py",
    "app/terms.py",
)

# Named constants inside modules that are not rules end to end. Only these
# names are read; the rest of the module is not part of the fingerprint.
RULE_CONSTANTS: dict[str, tuple[str, ...]] = {
    "app/integrations/models.py": (
        "ANCHOR_LABELS",
        "FINDING_TYPE_LABELS",
        "FindingType",
        "VERDICT_LABELS",
        "Verdict",
    ),
}


class RulesLockError(RuntimeError):
    """The lock cannot be written as asked, and the message says what to do."""


# ---------------------------------------------------------------------------
# The fingerprint
# ---------------------------------------------------------------------------


def _without_docstrings(node: ast.AST) -> ast.AST:
    """The same tree with every docstring dropped.

    Documentation is not a rule. Keeping docstrings in would make every
    clarifying edit demand a version bump, and a version that gets bumped for
    prose is a version nobody trusts to mean anything.
    """
    for child in ast.walk(node):
        if not isinstance(
            child, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(child, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            child.body = body[1:] or [ast.Pass()]
    return node


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _module_fingerprint(path: Path) -> str:
    tree = _without_docstrings(ast.parse(path.read_text("utf-8"), filename=str(path)))
    return _digest(ast.dump(tree, annotate_fields=True, include_attributes=False))


def _constants_fingerprint(path: Path, names: tuple[str, ...]) -> str:
    """Only the named module-level assignments, in the order they are named.

    A name that is not in the module at all is recorded as absent rather than
    skipped: a rule table that gets renamed must not quietly leave the
    fingerprint by leaving the file.
    """
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    found: dict[str, str] = {}
    for statement in tree.body:
        targets: list[str] = []
        if isinstance(statement, ast.Assign):
            targets = [t.id for t in statement.targets if isinstance(t, ast.Name)]
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            targets = [statement.target.id]
        for name in targets:
            if name in names:
                found[name] = ast.dump(
                    statement, annotate_fields=True, include_attributes=False
                )
    return _digest(
        "\x00".join(f"{name}={found.get(name, '<saknas>')}" for name in sorted(names))
    )


def parts(root: Path | None = None) -> dict[str, str]:
    """Every fingerprinted source, digested separately.

    Per source rather than one number for the lot, so a failure can name the
    module whose rules moved instead of telling a reader that *something*
    somewhere did.
    """
    base = Path(root) if root else BACKEND
    out: dict[str, str] = {}
    for relative in RULE_MODULES:
        out[relative] = _module_fingerprint(base / relative)
    for relative, names in RULE_CONSTANTS.items():
        out[f"{relative}::{','.join(sorted(names))}"] = _constants_fingerprint(
            base / relative, names
        )
    return dict(sorted(out.items()))


def fingerprint(root: Path | None = None) -> str:
    """One number for the rules as they stand in this checkout."""
    return _digest("\x00".join(f"{key}={value}" for key, value in parts(root).items()))


# ---------------------------------------------------------------------------
# The lock
# ---------------------------------------------------------------------------


def read_lock(path: Path | None = None) -> dict:
    target = Path(path) if path else LOCK_PATH
    if not target.exists():
        return {"versions": {}}
    return json.loads(target.read_text("utf-8"))


def recorded_for(version: str, *, path: Path | None = None) -> dict | None:
    return read_lock(path).get("versions", {}).get(version)


def drifted(root: Path | None = None, *, path: Path | None = None) -> list[str]:
    """Which fingerprinted sources differ from what the current version recorded.

    Empty when the rules match the version stamped on findings — including the
    case where the version is not in the lock at all, which is a different
    fault and is reported as one by the caller.
    """
    recorded = recorded_for(ANALYSIS_ENGINE_VERSION, path=path)
    if recorded is None:
        return []
    before = recorded.get("parts", {})
    now = parts(root)
    return sorted(
        key for key in set(before) | set(now) if before.get(key) != now.get(key)
    )


def record(
    version: str = ANALYSIS_ENGINE_VERSION,
    *,
    root: Path | None = None,
    path: Path | None = None,
) -> dict:
    """Write this checkout's rules down under ``version``. Never over another entry.

    The refusal is the whole automation. A rule change followed by a
    regeneration would otherwise be as silent as no check at all — so a version
    that is already recorded keeps the fingerprint it was recorded with, and
    the only way forward is to bump
    :data:`app.invoices.models.ANALYSIS_ENGINE_VERSION`.
    """
    target = Path(path) if path else LOCK_PATH
    lock = read_lock(target)
    current = fingerprint(root)
    existing = lock.get("versions", {}).get(version)
    if existing is not None and existing.get("fingerprint") != current:
        raise RulesLockError(
            f"Regelversion {version} är redan inspelad med ett annat fingeravtryck "
            f"({existing.get('fingerprint')} → {current}). Reglerna har ändrats sedan "
            "dess: höj ANALYSIS_ENGINE_VERSION i app/invoices/models.py och kör om. "
            "En inspelad version skrivs aldrig om — då skulle fynd som redan är "
            "stämplade med den påstå att de skrevs av de nya reglerna."
        )
    versions = dict(lock.get("versions", {}))
    versions[version] = {"fingerprint": current, "parts": parts(root)}
    written = {
        "note": lock.get(
            "note",
            "Fingeravtryck av granskningsreglerna per regelversion. Skrivs av "
            "`python -m app.invoices.rules --write`; redigeras inte för hand. En "
            "inspelad version skrivs aldrig om — nya regler kräver en ny version.",
        ),
        # Fingeravtrycket tas över Pythons parsade syntaxträd, så det hör ihop
        # med den tolk det togs under. Backenden kräver 3.12 ändå; att skriva
        # ner den gör ett annars förbryllande fel läsbart.
        "python": "3.12",
        "versions": dict(sorted(versions.items())),
    }
    target.write_text(json.dumps(written, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return written


def _main(argv: list[str]) -> int:
    write = "--write" in argv
    current = fingerprint()
    recorded = recorded_for(ANALYSIS_ENGINE_VERSION)
    print(f"ANALYSIS_ENGINE_VERSION = {ANALYSIS_ENGINE_VERSION}")
    print(f"regelfingeravtryck      = {current}")
    print(f"inspelat                = {recorded['fingerprint'] if recorded else '— saknas —'}")
    if write:
        try:
            record()
        except RulesLockError as exc:
            print(f"\nVÄGRAT: {exc}")
            return 1
        print(f"\nSkrev {LOCK_PATH.relative_to(BACKEND.parent)}")
        return 0
    if recorded is None:
        print("\nVersionen saknas i låsfilen. Kör med --write.")
        return 1
    if recorded["fingerprint"] != current:
        for key in drifted():
            print(f"  · ändrad regelkälla: {key}")
        print(
            "\nReglerna har ändrats utan att ANALYSIS_ENGINE_VERSION höjts. "
            "Höj den i app/invoices/models.py och kör om med --write."
        )
        return 1
    print("\nReglerna stämmer med den inspelade versionen.")
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    import sys

    raise SystemExit(_main(sys.argv[1:]))


__all__ = [
    "LOCK_PATH",
    "RULE_CONSTANTS",
    "RULE_MODULES",
    "RulesLockError",
    "drifted",
    "fingerprint",
    "parts",
    "read_lock",
    "record",
    "recorded_for",
]
