"""The engine version cannot fall behind the rules it names.

``ANALYSIS_ENGINE_VERSION`` is stamped on every recorded analysis run and is
the only thing on a case that says *these findings were written by different
rules than those*. It was maintained by hand. A bump that gets forgotten does
not fail loudly — it asserts, quietly and wrongly, that a conclusion from
before a rule change and one from after were reached the same way, which is
exactly the misreading the audit trail exists to prevent.

So this file makes the bump non-optional:

* :class:`TestTheRulesMatchTheVersionTheyAreStampedWith` is the tripwire. It
  fingerprints the rule sources as they stand in this checkout and compares
  that against what the lock recorded for the current version.
* :class:`TestTheFingerprintNoticesTheRightThings` is its RED proof, on a
  throwaway copy of the tree: a changed rule moves the fingerprint, and a
  rewritten docstring does not. A tripwire that has never been shown to fire is
  a comment.
* :class:`TestTheLockCannotBeRewrittenInsteadOfBumped` is what makes it
  automation rather than a reminder. Regenerating the lock without bumping is
  refused, so the only route to a green suite after changing a rule is the
  bump itself.
* :class:`TestEveryRuleSourceIsCovered` closes the hole the other three leave:
  rules that move into a module nobody added to the fingerprint. Any module in
  the backend that constructs a ``ReviewFinding`` must be fingerprinted.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

from app.invoices import rules
from app.invoices.models import ANALYSIS_ENGINE_VERSION

BACKEND = Path(__file__).resolve().parents[1]


def _rule_sources() -> list[str]:
    return [*rules.RULE_MODULES, *rules.RULE_CONSTANTS]


def _copy_tree(tmp_path: Path) -> Path:
    """Just the fingerprinted sources, at the paths the fingerprint reads them from."""
    root = tmp_path / "backend"
    for relative in _rule_sources():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BACKEND / relative, target)
    return root


class TestTheRulesMatchTheVersionTheyAreStampedWith:
    def test_the_lock_knows_the_version_the_engine_stamps(self):
        recorded = rules.recorded_for(ANALYSIS_ENGINE_VERSION)
        assert recorded is not None, (
            f"ANALYSIS_ENGINE_VERSION {ANALYSIS_ENGINE_VERSION} finns inte i "
            f"{rules.LOCK_PATH.name}. Kör: backend/.venv/bin/python -m app.invoices.rules --write"
        )

    def test_the_rules_are_the_ones_that_version_was_recorded_with(self):
        recorded = rules.recorded_for(ANALYSIS_ENGINE_VERSION)
        assert recorded is not None
        drift = rules.drifted()
        assert recorded["fingerprint"] == rules.fingerprint(), (
            "Granskningsreglerna har ändrats utan att ANALYSIS_ENGINE_VERSION höjts.\n"
            f"  ändrade regelkällor: {', '.join(drift) or '(hela avtrycket)'}\n"
            "  Fynd som redan är stämplade med "
            f"{ANALYSIS_ENGINE_VERSION} skulle då påstå att de skrevs av de nya reglerna.\n"
            "  Höj ANALYSIS_ENGINE_VERSION i app/invoices/models.py och kör sedan:\n"
            "    backend/.venv/bin/python -m app.invoices.rules --write"
        )
        assert drift == []

    def test_every_fingerprinted_source_still_exists(self):
        for relative in _rule_sources():
            assert (BACKEND / relative).exists(), (
                f"{relative} är fingeravtryckt men finns inte. En regelkälla som byter "
                "namn måste bytas namn i app/invoices/rules.py också, annars slutar "
                "kontrollen tyst att titta på den."
            )

    def test_a_renamed_rule_table_is_a_failure_not_a_silent_pass(self, tmp_path):
        """A constant that leaves the module must not leave the fingerprint quietly."""
        root = _copy_tree(tmp_path)
        relative, names = next(iter(rules.RULE_CONSTANTS.items()))
        source = (root / relative).read_text("utf-8")
        renamed = source.replace(f"{names[0]}:", f"{names[0]}_NYTT_NAMN:", 1).replace(
            f"{names[0]} =", f"{names[0]}_NYTT_NAMN =", 1
        )
        assert renamed != source
        (root / relative).write_text(renamed, "utf-8")
        assert rules.fingerprint(root) != rules.fingerprint()


class TestTheFingerprintNoticesTheRightThings:
    def test_a_copy_of_the_tree_fingerprints_identically(self, tmp_path):
        assert rules.fingerprint(_copy_tree(tmp_path)) == rules.fingerprint()

    def test_a_changed_threshold_changes_the_fingerprint(self, tmp_path):
        root = _copy_tree(tmp_path)
        target = root / "app/invoices/compare.py"
        source = target.read_text("utf-8")
        moved = source.replace("NEAR_DUPLICATE_DAYS = 21", "NEAR_DUPLICATE_DAYS = 30", 1)
        assert moved != source, "förutsättningen för testet finns inte längre i compare.py"
        target.write_text(moved, "utf-8")
        assert rules.fingerprint(root) != rules.fingerprint()
        assert rules.parts(root)["app/invoices/compare.py"] != rules.parts()["app/invoices/compare.py"]

    def test_a_reworded_verdict_changes_the_fingerprint(self, tmp_path):
        """The words are the conclusion, to the person reading them."""
        root = _copy_tree(tmp_path)
        target = root / "app/integrations/models.py"
        source = target.read_text("utf-8")
        reworded = source.replace('"möjlig avvikelse"', '"trolig avvikelse"', 1)
        assert reworded != source
        target.write_text(reworded, "utf-8")
        assert rules.fingerprint(root) != rules.fingerprint()

    def test_a_rewritten_docstring_does_not(self, tmp_path):
        """Otherwise the version gets bumped for prose and stops meaning anything."""
        root = _copy_tree(tmp_path)
        target = root / "app/invoices/compare.py"
        tree = ast.parse(target.read_text("utf-8"))
        assert ast.get_docstring(tree), "compare.py har ingen modul-docstring att skriva om"
        rewritten = target.read_text("utf-8").replace(
            ast.get_docstring(tree, clean=False),
            "En helt annan beskrivning av exakt samma regler.",
            1,
        )
        target.write_text(rewritten, "utf-8")
        assert rules.fingerprint(root) == rules.fingerprint()

    def test_a_new_comment_does_not(self, tmp_path):
        root = _copy_tree(tmp_path)
        target = root / "app/integrations/supplier.py"
        target.write_text(
            "# En kommentar som inte ändrar någon regel.\n" + target.read_text("utf-8"),
            "utf-8",
        )
        assert rules.fingerprint(root) == rules.fingerprint()


class TestTheLockCannotBeRewrittenInsteadOfBumped:
    def test_recording_the_same_rules_twice_is_allowed(self, tmp_path):
        lock = tmp_path / "RULES.lock.json"
        rules.record("2026.08.1", path=lock)
        rules.record("2026.08.1", path=lock)  # must not raise: nothing changed
        assert rules.read_lock(lock)["versions"]["2026.08.1"]["fingerprint"] == rules.fingerprint()

    def test_changed_rules_under_the_same_version_are_refused(self, tmp_path):
        lock = tmp_path / "RULES.lock.json"
        rules.record("2026.08.1", path=lock)

        root = _copy_tree(tmp_path)
        target = root / "app/invoices/compare.py"
        target.write_text(
            target.read_text("utf-8").replace(
                "NEAR_DUPLICATE_DAYS = 21", "NEAR_DUPLICATE_DAYS = 30", 1
            ),
            "utf-8",
        )
        with pytest.raises(rules.RulesLockError, match="ANALYSIS_ENGINE_VERSION"):
            rules.record("2026.08.1", root=root, path=lock)

    def test_the_bump_is_what_makes_it_recordable(self, tmp_path):
        lock = tmp_path / "RULES.lock.json"
        rules.record("2026.08.1", path=lock)

        root = _copy_tree(tmp_path)
        target = root / "app/invoices/compare.py"
        target.write_text(
            target.read_text("utf-8").replace(
                "NEAR_DUPLICATE_DAYS = 21", "NEAR_DUPLICATE_DAYS = 30", 1
            ),
            "utf-8",
        )
        written = rules.record("2026.08.2", root=root, path=lock)
        assert set(written["versions"]) == {"2026.08.1", "2026.08.2"}
        assert (
            written["versions"]["2026.08.1"]["fingerprint"]
            != written["versions"]["2026.08.2"]["fingerprint"]
        )

    def test_an_earlier_versions_fingerprint_is_never_touched(self, tmp_path):
        lock = tmp_path / "RULES.lock.json"
        rules.record("2026.08.1", path=lock)
        before = rules.read_lock(lock)["versions"]["2026.08.1"]

        root = _copy_tree(tmp_path)
        target = root / "app/integrations/supplier.py"
        target.write_text(
            target.read_text("utf-8").replace("def normalize(", "def normalize_v2(", 1), "utf-8"
        )
        rules.record("2026.09.1", root=root, path=lock)
        assert rules.read_lock(lock)["versions"]["2026.08.1"] == before


class TestEveryRuleSourceIsCovered:
    """A new rule module must not be able to slip past the fingerprint."""

    def _modules_constructing_findings(self) -> set[str]:
        found: set[str] = set()
        for path in sorted((BACKEND / "app").rglob("*.py")):
            tree = ast.parse(path.read_text("utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "ReviewFinding"
                ):
                    found.add(str(path.relative_to(BACKEND)))
        return found

    def test_the_check_finds_the_two_engines_it_should(self):
        found = self._modules_constructing_findings()
        assert {"app/integrations/review.py", "app/invoices/compare.py"} <= found, (
            f"sökningen hittade {sorted(found)} — den letar efter fel sak"
        )

    def test_nothing_writes_a_finding_from_outside_the_fingerprint(self):
        uncovered = self._modules_constructing_findings() - set(rules.RULE_MODULES)
        assert not uncovered, (
            f"{sorted(uncovered)} skriver fynd men ingår inte i regelavtrycket. "
            "Lägg till modulen i RULE_MODULES i app/invoices/rules.py — annars kan "
            "reglerna ändras utan att ANALYSIS_ENGINE_VERSION behöver höjas."
        )

    def test_the_engine_version_is_what_the_runs_are_stamped_with(self):
        """The version the lock guards is the one that lands on a record."""
        from app.invoices.models import AnalysisRun

        assert AnalysisRun.model_fields["engine_version"].default == ANALYSIS_ENGINE_VERSION
