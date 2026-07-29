"""The acceptance run must not be able to destroy evidence somebody committed.

The screenshot names used to be hardcoded ``xs49-*`` in ``docs/evidence``, so
running `make desktop-acceptance` overwrote the evidence XS-49 had been accepted
on — with images of a different run, without saying so. These tests hold the two
halves of the repair: the names follow the run label, and any target git already
tracks stops the run before it starts.
"""

from __future__ import annotations

import pytest

from scripts.desktop_acceptance import REPO, UI_SCREENSHOTS, AcceptanceError, Evidence

# Committed under docs/evidence since XS-49; the collision this guard exists for.
XS49_SCREENSHOT = "docs/evidence/xs49-desktop-setup.png"
XS49_RECEIPT = "docs/evidence/xs49-desktop-acceptance.json"


def test_screenshot_names_follow_the_run_label(tmp_path):
    evidence = Evidence(tmp_path, "pilot")
    assert evidence.path("setup").name == "pilot-desktop-setup.png"
    assert evidence.receipt.name == "pilot-desktop-acceptance.json"


def test_no_target_carries_a_foreign_issue_name(tmp_path):
    evidence = Evidence(tmp_path, "pilot")
    assert not [target for target in evidence.targets() if "xs49" in target.name]


def test_an_unusable_label_is_refused(tmp_path):
    for label in ("", "XS49", "../escape", "with space"):
        with pytest.raises(AcceptanceError):
            Evidence(tmp_path, label)


def test_committed_evidence_is_seen_as_committed():
    """The exact run that caused the damage is now the one that is refused."""
    tracked = Evidence(REPO / "docs/evidence", "xs49").tracked()
    assert XS49_SCREENSHOT in tracked
    assert XS49_RECEIPT in tracked


def test_a_label_of_its_own_is_free_to_write():
    assert Evidence(REPO / "docs/evidence", "unclaimed-run-label").tracked() == []


def test_an_explicitly_placed_receipt_is_guarded_too():
    """--output was the older way to aim a run at a committed file."""
    evidence = Evidence(REPO / "docs/evidence", "unclaimed-run-label", receipt=REPO / XS49_RECEIPT)
    assert evidence.tracked() == [XS49_RECEIPT]


def test_the_guard_does_not_depend_on_which_phases_run(tmp_path):
    """A guard that only covered the selected phases would pass on a partial run
    and then destroy the evidence on the next full one."""
    names = {target.name for target in Evidence(tmp_path, "pilot").targets()}
    assert {f"pilot-desktop-{view}.png" for view in UI_SCREENSHOTS} <= names
    assert "pilot-desktop-startup-failure.png" in names
