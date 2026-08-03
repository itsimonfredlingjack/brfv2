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
from scripts.invoice_acceptance import FAILURE_SCREENSHOT, INVOICE_SCREENSHOTS

# The XS-49 run that caused the damage, and the evidence files it overwrote,
# belong to the Fedora pilot and stay on that frozen release line — they are
# history, not product. So the "git already carries this target" half of the
# guard is anchored here on a file this branch genuinely tracks. What is being
# asserted is the rule, not the filename: any target already in the index stops
# the run, whichever file happens to occupy that path.
TRACKED_FILE = "README.md"


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


def test_a_label_of_its_own_is_free_to_write():
    assert Evidence(REPO / "docs/evidence", "unclaimed-run-label").tracked() == []


def test_committed_evidence_is_seen_as_committed():
    """A target the repository already carries is reported, not silently written.

    Aimed through ``receipt=`` because ``--output`` was the older way to point a
    run at a committed file, so it is the path that must be guarded too.
    """
    evidence = Evidence(REPO / "docs/evidence", "unclaimed-run-label", receipt=REPO / TRACKED_FILE)
    assert evidence.tracked() == [TRACKED_FILE]


def test_the_guard_does_not_depend_on_which_phases_run(tmp_path):
    """A guard that only covered the selected phases would pass on a partial run
    and then destroy the evidence on the next full one."""
    names = {target.name for target in Evidence(tmp_path, "pilot").targets()}
    assert {f"pilot-desktop-{view}.png" for view in UI_SCREENSHOTS} <= names
    assert "pilot-desktop-startup-failure.png" in names


# ---------------------------------------------------------------------------
# Two journeys, one evidence directory
# ---------------------------------------------------------------------------
#
# The invoice acceptance writes into the same directory under the same label.
# If the two shared a filename, running both — which is exactly what
# `make desktop-acceptance-full` does — would leave one record describing the
# other's run. The kind is what keeps them apart, so it is asserted rather than
# assumed.


def test_the_two_journeys_cannot_write_the_same_file(tmp_path):
    desktop = Evidence(tmp_path, "pilot")
    invoice = Evidence(
        tmp_path, "pilot", kind="invoice", views=(*INVOICE_SCREENSHOTS, FAILURE_SCREENSHOT)
    )
    assert not {t.name for t in desktop.targets()} & {t.name for t in invoice.targets()}


def test_the_invoice_run_names_its_evidence_after_the_run_and_the_journey(tmp_path):
    invoice = Evidence(
        tmp_path, "rc2", kind="invoice", views=(*INVOICE_SCREENSHOTS, FAILURE_SCREENSHOT)
    )
    assert invoice.path("credit").name == "rc2-invoice-credit.png"
    assert invoice.receipt.name == "rc2-invoice-acceptance.json"


def test_every_invoice_screenshot_including_the_failure_one_is_guarded(tmp_path):
    invoice = Evidence(
        tmp_path, "pilot", kind="invoice", views=(*INVOICE_SCREENSHOTS, FAILURE_SCREENSHOT)
    )
    names = {target.name for target in invoice.targets()}
    assert {f"pilot-invoice-{view}.png" for view in INVOICE_SCREENSHOTS} <= names
    assert "pilot-invoice-failure.png" in names
