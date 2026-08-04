"""Artifact-level proof that no hosted provider ships in the Fedora desktop RPM.

Every other test in this suite reads the source tree. This one refuses to:
it unpacks the built package, and — where the package is also installed —
looks at /usr as well. A source tree can be correct while the artifact is not,
which is precisely the defect this file exists to catch.

What it checks, and why each is a different claim:

  file absence        the package does not carry the implementation,
                      its distribution metadata, or its entry points
  import behaviour    the packaged interpreter cannot import it from anywhere
                      else either — a lazy __getattr__ or a stale .pyc would
                      make absence-on-disk meaningless
  selection behaviour no BRF_LLM value and no ambient credential or CLI makes
                      the packaged app.llm hand back a hosted provider

The verdicts come from ops/inspect_payload.py, which answers
ops/forbidden_providers.json against the artifact. This file does not maintain
a list of expected successes: it asserts that the named rules were *answered*,
and that every answer came back clean. A rule that silently stopped running
fails here, because "was this checked?" is asserted separately from "what did
it find?".

Two independent derivations are used on purpose. The structural assertions go
through the inspector; the coarse one below goes straight to `rpm -qlp`, so a
bug in the inspector cannot make the package look clean on its own.

Skipped when no artifact is available. Set BRFV2_REQUIRE_ARTIFACT=1 to turn
that skip into a failure — the delivery run does, so a green suite can never
mean "the artifact test did not run".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INSPECTOR = REPO / "ops" / "inspect_payload.py"
RULES = json.loads((REPO / "ops" / "forbidden_providers.json").read_text(encoding="utf-8"))
INSTALLED_ROOT = Path("/usr/lib/Träff")

pytestmark = pytest.mark.artifact


def _require_or_skip(reason: str):
    if os.environ.get("BRFV2_REQUIRE_ARTIFACT") == "1":
        pytest.fail(f"BRFV2_REQUIRE_ARTIFACT=1 men {reason}")
    pytest.skip(reason)


def _locate_rpm() -> Path:
    explicit = os.environ.get("BRFV2_RPM", "").strip()
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            _require_or_skip(f"BRFV2_RPM pekar på något som inte finns: {path}")
        return path
    candidates = sorted((REPO / "dist").glob("brf-dokument-ai-*.rpm"))
    if not candidates:
        _require_or_skip(
            "ingen byggd RPM hittades (kör 'make desktop-package', eller ange BRFV2_RPM=...)"
        )
    return candidates[-1]


def _run_inspector(args: list[str], out: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(INSPECTOR), *args, "--json", str(out), "--quiet"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert out.is_file(), (
        "granskaren producerade inget resultat:\n"
        f"exit={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    result = json.loads(out.read_text(encoding="utf-8"))
    # The inspector's own exit status and its recorded verdict must agree; if
    # they ever disagree the evidence is not trustworthy in either direction.
    assert (proc.returncode == 0) == result["ok"], (
        f"granskarens slutstatus ({proc.returncode}) motsäger dess resultat (ok={result['ok']})"
    )
    return result


@pytest.fixture(scope="module")
def unpacked_rpm() -> tuple[Path, Path]:
    """The built package, unpacked. Returns (rpm path, unpacked root).

    Deliberately not pytest's tmp_path: the payload is ~780 MB unpacked and
    /tmp is a tmpfs on the machines this runs on. It lands next to the build
    output instead, on the disk that already holds the artifact, and is
    removed afterwards. BRFV2_ARTIFACT_WORKDIR overrides the location.
    """
    rpm = _locate_rpm()
    for tool in ("rpm2cpio", "cpio"):
        if shutil.which(tool) is None:
            _require_or_skip(f"{tool} saknas — kan inte packa upp artefakten")
    workdir = Path(os.environ.get("BRFV2_ARTIFACT_WORKDIR") or (REPO / "src-tauri/target/rpm"))
    workdir.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="test-unpacked-", dir=str(workdir)))
    with open(rpm, "rb") as handle:
        cpio_stream = subprocess.Popen(["rpm2cpio", "-"], stdin=handle, stdout=subprocess.PIPE)
        subprocess.run(["cpio", "-idm", "--quiet"], stdin=cpio_stream.stdout, cwd=str(root), check=True)
        cpio_stream.stdout.close()
        assert cpio_stream.wait() == 0, "rpm2cpio misslyckades"
    assert (root / "usr/bin/brfv2-desktop").is_file(), "det uppackade paketet saknar skalet"
    try:
        yield rpm, root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def artifact_inspection(unpacked_rpm, tmp_path_factory) -> dict:
    rpm, root = unpacked_rpm
    out = tmp_path_factory.mktemp("inspection") / "artifact.json"
    sha = subprocess.run(["sha256sum", str(rpm)], capture_output=True, text=True, check=True)
    return _run_inspector(
        ["--root", str(root), "--scope", "unpacked-rpm",
         "--artifact", rpm.name, "--artifact-sha256", sha.stdout.split()[0]],
        out,
    )


def _by_rule(inspection: dict, rule: str) -> dict[str, dict]:
    return {check["target"]: check for check in inspection["checks"] if check["rule"] == rule}


def _assert_answered(checks: dict[str, dict], target: str, rule: str) -> dict:
    assert target in checks, (
        f"regeln {rule} besvarades aldrig för {target!r} — granskningen är ofullständig, "
        f"besvarade mål: {sorted(checks)}"
    )
    return checks[target]


# ---------------------------------------------------------------------------
# The artifact as a whole
# ---------------------------------------------------------------------------

def test_inspection_covers_the_whole_installed_layout(artifact_inspection):
    scope = _by_rule(artifact_inspection, "scope")
    for component in ("usr/bin/brfv2-desktop", "usr/lib/Träff/ui",
                      "usr/lib/Träff/runtime"):
        check = _assert_answered(scope, component, "scope")
        assert check["result"] == "pass", f"{component} saknas i artefakten: {check}"


def test_the_artifact_has_no_forbidden_provider_content(artifact_inspection):
    findings = artifact_inspection["findings"]
    assert findings == [], (
        "den byggda RPM:en innehåller förbjudet leverantörsmaterial:\n"
        + json.dumps(findings, ensure_ascii=False, indent=2)
    )
    assert artifact_inspection["ok"] is True


def test_the_inspection_actually_ran_every_class_of_rule(artifact_inspection):
    """A clean result is only worth something if the rules were answered.

    Without this, deleting a rule class from the inspector would turn the test
    above green — the exact failure mode a manually maintained success list
    has.
    """
    ran = {check["rule"] for check in artifact_inspection["checks"]}
    for rule in ("distribution", "path-pattern", "filename-scan", "entry-point",
                 "text-scan", "declared-reference", "module-import", "module-attribute",
                 "required-module", "provider-selection", "hosted-plugin-registry",
                 "retained-module-inert", "guarded-optional-import", "model2vec",
                 "endpoint-policy"):
        assert rule in ran, f"regelklassen {rule} kördes aldrig mot artefakten"
    assert artifact_inspection["counts"]["checks"] >= 40
    assert artifact_inspection["rules"]["sha256"], "granskningen anger inte vilka regler den svarade på"


def test_the_inspection_names_the_artifact_it_read(artifact_inspection, unpacked_rpm):
    rpm, _ = unpacked_rpm
    inspected = artifact_inspection["inspected"]
    assert inspected["artifact"] == rpm.name
    assert len(inspected["artifactSha256"]) == 64
    assert len(inspected["payloadSha256"]) == 64
    assert inspected["files"] > 1000, "granskningen läste misstänkt få filer"


# ---------------------------------------------------------------------------
# Explicit negative assertions, per forbidden thing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("distribution", ["anthropic", "hf_xet"])
def test_no_forbidden_distribution_metadata(artifact_inspection, distribution):
    check = _assert_answered(_by_rule(artifact_inspection, "distribution"), distribution, "distribution")
    assert check["result"] == "absent", (
        f"{distribution} har distributionsmetadata i paketet: {check.get('foundAs')}"
    )
    inventory = _by_rule(artifact_inspection, "distribution-inventory")
    (parsed,) = inventory.values()
    assert distribution.replace("_", "-") not in parsed["distributions"]
    assert parsed["count"] > 20, "distributionsinventeringen hittade nästan inget — läste den rätt träd?"


@pytest.mark.parametrize("module", [
    "anthropic",
    "hf_xet",
    "huggingface_hub.inference",
    "huggingface_hub.inference._providers",
    "huggingface_hub.inference_api",
    "app.llm_hosted",
])
def test_forbidden_modules_cannot_be_imported_by_the_packaged_interpreter(artifact_inspection, module):
    check = _assert_answered(_by_rule(artifact_inspection, "module-import"), module, "module-import")
    assert check["result"] == "absent", f"{module} går att importera ur paketet: {check}"
    assert check["error"] == "ModuleNotFoundError", (
        f"{module} misslyckades av fel skäl ({check.get('error')}: {check.get('message')}) — "
        "det bevisar inte att implementationen saknas"
    )


@pytest.mark.parametrize("attribute", ["huggingface_hub.InferenceClient",
                                       "huggingface_hub.AsyncInferenceClient"])
def test_hosted_inference_clients_are_not_reachable_as_attributes(artifact_inspection, attribute):
    check = _assert_answered(_by_rule(artifact_inspection, "module-attribute"), attribute, "module-attribute")
    assert check["result"] == "absent", (
        f"{attribute} går fortfarande att nå — filfrånvaro räcker inte när paketet "
        f"exponerar attributet lat: {check}"
    )


def test_no_hosted_inference_provider_adapters_remain(artifact_inspection):
    """The ~20 third-party adapters in huggingface_hub.inference._providers."""
    paths = _by_rule(artifact_inspection, "path-pattern")
    for glob in ("**/huggingface_hub/inference/**", "**/huggingface_hub/inference_api.py*"):
        check = _assert_answered(paths, glob, "path-pattern")
        assert check["result"] == "absent", f"hostade inferensadaptrar finns kvar: {check['matches']}"
    filenames = _by_rule(artifact_inspection, "filename-scan")
    (scan,) = filenames.values()
    assert scan["result"] == "absent", f"förbjudna filnamn i paketet: {scan['matches']}"


def test_no_entry_point_registers_a_forbidden_implementation(artifact_inspection):
    inventory = _by_rule(artifact_inspection, "entry-point-inventory")
    (parsed,) = inventory.values()
    assert parsed["entryPoints"], "inga entry points lästes alls — inventeringen är tom"
    for check in _by_rule(artifact_inspection, "entry-point").values():
        assert check["result"] == "absent", f"förbjuden registrering kvar: {check['matches']}"
    # Independent of the regex: nothing may point into the removed tree.
    assert not [e for e in parsed["entryPoints"] if "inference" in e]


def test_no_hosted_provider_plugin_is_registered_in_the_package(artifact_inspection):
    (check,) = _by_rule(artifact_inspection, "hosted-plugin-registry").values()
    assert check["result"] == "pass", check
    assert check["registered"] == [], (
        f"paketet registrerar hostade leverantörer: {check['registered']}"
    )


@pytest.mark.parametrize("label,expected_key", [
    ("auto with a hosted API key exported", "ANTHROPIC_API_KEY"),
    ("auto with a `claude` executable on PATH", None),
    ("forced hosted API key", "ANTHROPIC_API_KEY"),
    ("forced hosted CLI", None),
    ("BRF_LLM=api (declared selection key)", None),
    ("BRF_LLM=cli (declared selection key)", None),
])
def test_no_environment_selects_a_hosted_provider(artifact_inspection, label, expected_key):
    check = _assert_answered(_by_rule(artifact_inspection, "provider-selection"), label, "provider-selection")
    forbidden = {item["id"] for item in RULES["providerIdentifiers"]}
    assert check["selected"] == "none", f"{label} valde {check['selected']!r}"
    assert check["selected"] not in forbidden
    if expected_key:
        assert expected_key in check["env"], "fallet testade inte den avsedda miljövariabeln"


def test_the_declared_shell_reference_is_only_the_environment_scrub(artifact_inspection):
    """The one forbidden literal that is allowed, held to an exact count.

    It is the name of a variable the shell DELETES from the backend's
    environment. A second occurrence — or any other forbidden name in the same
    file — fails, so this is a bounded declaration and not an exemption.
    """
    checks = _by_rule(artifact_inspection, "declared-reference")
    target = next(t for t in checks if t.startswith("usr/bin/brfv2-desktop"))
    check = checks[target]
    assert check["result"] == "pass", check
    assert check["declaredOccurrences"] == check["expected"] == 1
    assert check["totalForbiddenNameOccurrences"] == 1, (
        "skalet innehåller fler förbjudna namn än den deklarerade miljöskrubben"
    )


def test_the_packaged_product_code_names_no_hosted_provider(artifact_inspection):
    checks = _by_rule(artifact_inspection, "text-scan")
    for target in ("usr/lib/Träff/runtime/backend", "usr/lib/Träff/ui"):
        check = _assert_answered(checks, target, "text-scan")
        assert check["result"] == "absent", (
            f"odeklarerade förbjudna namn i {target}: {check['undeclared']}"
        )
        assert check["files"] > 0, f"textsökningen läste inga filer under {target}"


# ---------------------------------------------------------------------------
# The approved runtime survived the removals
# ---------------------------------------------------------------------------

def test_model2vec_still_loads_the_bundled_weights_and_embeds(artifact_inspection):
    (check,) = _by_rule(artifact_inspection, "model2vec").values()
    assert check["result"] == "pass", check
    assert check["name"] == "model2vec:potion-multilingual-128M"
    assert check["dim"] == 256


def test_the_selfhosted_provider_is_still_selectable_from_the_package(artifact_inspection):
    check = _assert_answered(
        _by_rule(artifact_inspection, "provider-selection"),
        "the approved self-hosted provider is still selectable", "provider-selection",
    )
    assert check["selected"] == "selfhosted", check
    assert check["model"] == "gemma4:e12b"


def test_the_endpoint_policy_shipped_with_the_package(artifact_inspection):
    (check,) = _by_rule(artifact_inspection, "endpoint-policy").values()
    assert check["result"] == "pass", check
    assert check["verdicts"]["https://api.openai.com/v1"] is False
    assert check["verdicts"]["https://api.anthropic.com/v1"] is False
    assert check["verdicts"]["http://127.0.0.1:8000/v1"] is True


@pytest.mark.parametrize("module", ["model2vec", "huggingface_hub", "huggingface_hub.hf_api",
                                    "app.llm", "app.desktop"])
def test_the_approved_runtime_still_imports(artifact_inspection, module):
    check = _assert_answered(_by_rule(artifact_inspection, "required-module"), module, "required-module")
    assert check["result"] == "pass", f"{module} går inte att importera ur paketet: {check}"


def test_the_retained_inference_endpoint_module_cannot_produce_a_client(artifact_inspection):
    (check,) = _by_rule(artifact_inspection, "retained-module-inert").values()
    assert check["result"] == "pass", check
    for prop, probe in check["probe"].items():
        assert probe["raised"], f"{prop} kan fortfarande nå en hostad klient: {probe}"
        assert probe["imports"], f"{prop} utför inga importer — bevisningen är tom"
        assert all(not i["importable"] for i in probe["imports"])


def test_the_absent_xet_backend_is_a_guarded_optional_import(artifact_inspection):
    (check,) = _by_rule(artifact_inspection, "guarded-optional-import").values()
    assert check["result"] == "pass", check
    assert check["hostImportable"] is True, "huggingface_hub gick inte att importera utan hf_xet"
    assert check["available"] is False, "paketet tror fortfarande att hf_xet finns"


# ---------------------------------------------------------------------------
# A second, independent derivation from the same artifact
# ---------------------------------------------------------------------------

def test_rpm_file_list_names_nothing_forbidden(unpacked_rpm):
    """Straight from `rpm -qlp`, with no help from the inspector."""
    rpm, _ = unpacked_rpm
    if shutil.which("rpm") is None:
        pytest.skip("rpm saknas")
    listing = subprocess.run(["rpm", "-qlp", str(rpm)], capture_output=True, text=True, check=True).stdout
    paths = listing.splitlines()
    assert len(paths) > 1000, "paketlistan är misstänkt kort"
    offending = [
        p for p in paths
        if any(token in p.lower() for token in ("anthropic", "hf_xet", "llm_hosted"))
        or "huggingface_hub/inference" in p
    ]
    assert offending == [], f"RPM:ens filista innehåller förbjudna sökvägar: {offending[:20]}"


def test_the_package_declares_no_forbidden_dependency(unpacked_rpm):
    rpm, _ = unpacked_rpm
    if shutil.which("rpm") is None:
        pytest.skip("rpm saknas")
    requires = subprocess.run(["rpm", "-qRp", str(rpm)], capture_output=True, text=True, check=True).stdout
    assert "anthropic" not in requires.lower()
    assert "hf_xet" not in requires.lower()


# ---------------------------------------------------------------------------
# The installed runtime, when there is one
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def installed_inspection(tmp_path_factory) -> dict:
    if not (INSTALLED_ROOT / "runtime").is_dir():
        pytest.skip("paketet är inte installerat på den här maskinen")
    out = tmp_path_factory.mktemp("installed") / "installed.json"
    return _run_inspector(["--installed", "--scope", "installed"], out)


def test_the_installed_runtime_has_no_forbidden_provider_content(installed_inspection):
    assert installed_inspection["findings"] == [], json.dumps(
        installed_inspection["findings"], ensure_ascii=False, indent=2
    )


def test_the_installed_runtime_cannot_import_or_select_a_hosted_provider(installed_inspection):
    imports = _by_rule(installed_inspection, "module-import")
    for module in ("anthropic", "app.llm_hosted", "huggingface_hub.inference"):
        assert _assert_answered(imports, module, "module-import")["result"] == "absent"
    for check in _by_rule(installed_inspection, "provider-selection").values():
        assert check["selected"] == check["expected"], check


def test_the_installed_runtime_still_embeds_with_model2vec(installed_inspection):
    (check,) = _by_rule(installed_inspection, "model2vec").values()
    assert check["result"] == "pass", check
    assert check["dim"] == 256
