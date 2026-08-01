#!/usr/bin/env python3
"""Answer ops/forbidden_providers.json against a payload that actually exists.

This is the only thing in the delivery allowed to say whether a hosted
provider was excluded. It never reads a list of successes: every answer comes
from the artifact in front of it — the packaged tree is listed, the packaged
distribution metadata and entry points are parsed, and the packaged
interpreter is executed to see what it can import, expose and select. A rule
that finds nothing is a *checked absence*; a rule that finds something is a
finding and the caller fails.

Two scopes, same rules:

  --runtime DIR   the staged runtime tree alone (ops/build-runtime.sh, before
                  a package exists). The shell binary and the built UI are not
                  in scope yet and are reported as such rather than skipped
                  silently.
  --root DIR      an install-shaped root: usr/bin/brfv2-desktop and
                  usr/lib/BRF Dokument-AI/. That is the buildroot and an
                  extracted RPM, so the same rules answer for the package
                  contents.
  --installed [P] the installed product under prefix P (default /), mounted
                  component by component rather than by walking a live
                  filesystem — same rules, same install-relative paths, so
                  file absence and import/registration behaviour are
                  distinguished on the machine the package is actually on.

The output is deterministic: relative paths only, sorted, no clock, no
build-host detail. It is embedded verbatim in the bundle manifest, so two
builds of the same commit from different checkout paths must produce the same
bytes here too.

  ops/inspect_payload.py --runtime src-tauri/runtime --json out.json
  ops/inspect_payload.py --root src-tauri/target/rpm/buildroot
  ops/inspect_payload.py --installed --scope installed

Exit status: 0 when every rule is answered and none found anything, 1 when
there is at least one finding or a rule could not be answered.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "ops" / "forbidden_providers.json"

APP_DIR = "usr/lib/BRF Dokument-AI"
RUNTIME_REL = f"{APP_DIR}/runtime"
UI_REL = f"{APP_DIR}/ui"
SHELL_REL = "usr/bin/brfv2-desktop"

PRESENT = "present"
ABSENT = "absent"
PASS = "pass"
FAIL = "fail"
OUT_OF_SCOPE = "out-of-scope"

FAILING = (PRESENT, FAIL)

# Two files are deliberately outside the payload identity hash. BUNDLE.json
# carries the hash, so it cannot contain it; requirements.lock.txt is a
# build-only input that packaging drops from the buildroot. Excluding exactly
# these two is what lets the hash recorded at staging time be recomputed from
# the unpacked RPM and compared.
IDENTITY_EXCLUDE = (f"{RUNTIME_REL}/BUNDLE.json", f"{RUNTIME_REL}/requirements.lock.txt")


def normalize_distribution(name: str) -> str:
    """PEP 503/427 name normalization, so `hf-xet` and `hf_xet` are one name."""
    return re.sub(r"[-_.]+", "-", name).lower()


class Payload:
    """An install-shaped view of whatever was handed in.

    Both scopes are expressed as a mapping from an install-relative prefix to
    a real directory, so every rule can be written once against install paths
    and answered identically for a staged tree, a buildroot, an unpacked RPM
    or a live installation.
    """

    def __init__(self, mounts: dict[str, Path], scope: str) -> None:
        self.mounts = mounts
        self.scope = scope

    @classmethod
    def from_runtime(cls, runtime: Path) -> "Payload":
        return cls({RUNTIME_REL: runtime.resolve()}, "runtime")

    @classmethod
    def from_root(cls, root: Path, scope: str) -> "Payload":
        return cls({"": root.resolve()}, scope)

    @classmethod
    def from_installed(cls, prefix: Path, scope: str) -> "Payload":
        """The installed product, mounted component by component.

        Deliberately not `--root /`: the payload is three known paths, and
        walking a live filesystem to find them would read every process's
        /proc entry and every other package on the machine. Same rules, same
        install-relative paths, bounded to what the package owns.
        """
        prefix = prefix.resolve()
        mounts = {}
        for rel in (SHELL_REL, UI_REL, RUNTIME_REL):
            candidate = prefix / rel
            if candidate.exists():
                mounts[rel] = candidate
        if not mounts:
            raise SystemExit(f"FEL: inget installerat paket under {prefix}")
        return cls(mounts, scope)

    def resolve(self, rel: str) -> Path | None:
        """The real path of an install-relative path, or None if out of scope."""
        rel = rel.strip("/")
        best: Path | None = None
        best_len = -1
        for prefix, real in self.mounts.items():
            prefix = prefix.strip("/")
            if prefix and not (rel == prefix or rel.startswith(prefix + "/")):
                continue
            if len(prefix) <= best_len:
                continue
            tail = rel[len(prefix):].strip("/") if prefix else rel
            best = real / tail if tail else real
            best_len = len(prefix)
        return best

    def in_scope(self, rel: str) -> bool:
        return self.resolve(rel) is not None

    def exists(self, rel: str) -> bool:
        path = self.resolve(rel)
        return path is not None and (path.exists() or path.is_symlink())

    def walk(self):
        """Every file and symlink in the payload, as (install-relative, real)."""
        for prefix, real in sorted(self.mounts.items()):
            prefix = prefix.strip("/")
            if real.is_file():
                yield prefix, real
                continue
            for path in sorted(real.rglob("*")):
                if path.is_dir() and not path.is_symlink():
                    continue
                rel = path.relative_to(real).as_posix()
                yield (f"{prefix}/{rel}" if prefix else rel), path

    def site_packages(self) -> tuple[str, Path] | tuple[None, None]:
        runtime = self.resolve(RUNTIME_REL)
        if runtime is None or not runtime.is_dir():
            return None, None
        candidates = sorted((runtime / "python" / "lib").glob("python3.*/site-packages"))
        if not candidates:
            return None, None
        site = candidates[0]
        rel = f"{RUNTIME_REL}/python/lib/{site.parent.name}/site-packages"
        return rel, site

    def identity(self) -> dict:
        """A content hash over the payload, plus what it covers.

        This is what ties an inspection result to the bytes it was taken from.
        The bundle manifest carries the hash of the runtime tree it describes;
        packaging recomputes the same hash from the *unpacked RPM* and refuses
        to ship if the two differ, which is what makes the manifest a
        statement about the package rather than about the build's intentions.
        """
        digest = hashlib.sha256()
        files = 0
        total = 0
        for rel, path in self.walk():
            if rel in IDENTITY_EXCLUDE:
                continue
            if path.is_symlink():
                entry = f"{rel}\0symlink\0{os.readlink(path)}\n"
            else:
                data = path.read_bytes()
                total += len(data)
                entry = f"{rel}\0{path.stat().st_mode & 0o777:o}\0{hashlib.sha256(data).hexdigest()}\n"
            digest.update(entry.encode("utf-8"))
            files += 1
        return {
            "scope": self.scope,
            "covers": sorted(self.mounts.keys()) or [""],
            "files": files,
            "bytes": total,
            "payloadSha256": digest.hexdigest(),
            "excludedFromHash": list(IDENTITY_EXCLUDE),
        }


# --------------------------------------------------------------------------
# The probe that runs inside the packaged interpreter.
#
# File absence is not the whole claim: a module can be importable from
# somewhere else, an attribute can be produced by a lazy __getattr__, and a
# provider can be selectable by a key even when nothing obvious names it. So
# the questions that are about *behaviour* are asked of the packaged
# interpreter, running the packaged code, with the packaged site-packages.
# --------------------------------------------------------------------------
PROBE_SOURCE = r'''
import importlib, json, os, stat, sys, tempfile
sys.path.insert(0, os.getcwd())

spec = json.loads(open(sys.argv[1], encoding="utf-8").read())
out = {"imports": [], "attributes": [], "required": [], "guarded": [], "inert": [],
       "selection": [], "functional": [], "errors": []}


def record(exc):
    return {"error": type(exc).__name__, "message": str(exc)}


for name in spec["forbiddenModules"]:
    try:
        importlib.import_module(name)
        out["imports"].append({"module": name, "importable": True})
    except ModuleNotFoundError as exc:
        out["imports"].append({"module": name, "importable": False, **record(exc)})
    except Exception as exc:
        out["imports"].append({"module": name, "importable": False, "unexpected": True, **record(exc)})

for item in spec["forbiddenAttributes"]:
    entry = {"module": item["module"], "attribute": item["attribute"]}
    try:
        module = importlib.import_module(item["module"])
    except Exception as exc:
        entry.update({"reachable": False, **record(exc)})
    else:
        try:
            getattr(module, item["attribute"])
            entry["reachable"] = True
        except Exception as exc:
            entry.update({"reachable": False, **record(exc)})
    out["attributes"].append(entry)

for name in spec["requiredModules"]:
    try:
        module = importlib.import_module(name)
        out["required"].append({"module": name, "importable": True,
                                "version": str(getattr(module, "__version__", "") or "")})
    except Exception as exc:
        out["required"].append({"module": name, "importable": False, **record(exc)})

for item in spec["guardedOptionalImports"]:
    entry = {"module": item["module"], "absentDependency": item["absentDependency"]}
    try:
        importlib.import_module(item["module"])
        entry["hostImportable"] = True
        probe_mod, _, probe_attr = item["availabilityProbe"].rpartition(".")
        entry["available"] = bool(getattr(importlib.import_module(probe_mod), probe_attr)())
    except Exception as exc:
        entry.update({"hostImportable": False, **record(exc)})
    out["guarded"].append(entry)

# Inertness probes for modules retained because the approved runtime imports
# them transitively. Keyed by module so the rules file cannot smuggle code in.
def _probe_inference_endpoints():
    """Prove the retained module cannot produce a hosted client.

    Constructing the dataclass would fail for unrelated reasons (unset
    fields), which proves nothing. So the probe reads the source of the only
    two members that can hand out a client, extracts the imports they perform,
    and shows that each of those imports is unsatisfiable in this payload.
    """
    import inspect as _inspect, re as _re
    from huggingface_hub import _inference_endpoints as mod

    results = {}
    for prop in ("client", "async_client"):
        member = getattr(mod.InferenceEndpoint, prop, None)
        target = getattr(member, "fget", member)
        try:
            source = _inspect.getsource(target)
        except Exception as exc:
            results[prop] = {"raised": False, "sourceUnavailable": True, **record(exc)}
            continue
        imports = _re.findall(r"^\s*from\s+([.\w]+)\s+import\s", source, _re.M)
        resolved = []
        for name in imports:
            absolute = "huggingface_hub" + name if name.startswith(".") else name
            try:
                importlib.import_module(absolute)
                resolved.append({"module": absolute, "importable": True})
            except Exception as exc:
                resolved.append({"module": absolute, "importable": False, **record(exc)})
        reachable = [i for i in resolved if i["importable"]]
        results[prop] = {
            "raised": bool(resolved) and not reachable,
            "imports": resolved,
        }
    return results

INERTNESS = {"huggingface_hub._inference_endpoints": _probe_inference_endpoints}

for name in spec["retainedModules"]:
    entry = {"module": name, "hasProbe": name in INERTNESS}
    if entry["hasProbe"]:
        try:
            entry["probe"] = INERTNESS[name]()
        except Exception as exc:
            entry["probe"] = {"probeFailed": True, **record(exc)}
    out["inert"].append(entry)

# ---- provider selection ---------------------------------------------------
# Guarded like every other section: a payload whose app.llm predates the
# plug-in split must still produce the file-level and import-level findings
# instead of aborting the probe and losing them.
try:
    import app.llm as llm
    out["hostedPlugins"] = [p.key for p in llm.hosted_providers()]
except Exception as exc:
    llm = None
    out["errors"].append({"section": "hostedPlugins", **record(exc)})

FAKE_BIN = tempfile.mkdtemp(prefix="probe-path-")
fake_claude = os.path.join(FAKE_BIN, "claude")
with open(fake_claude, "w", encoding="utf-8") as handle:
    handle.write("#!/bin/sh\nexit 0\n")
os.chmod(fake_claude, os.stat(fake_claude).st_mode | stat.S_IEXEC)

MANAGED = ("BRF_LLM", "BRF_LLM_BASE_URL", "BRF_LLM_MODEL", "BRF_LLM_API_KEY",
           "ANTHROPIC_API_KEY", "PATH")
BASE_PATH = os.environ.get("PATH", "")

def select(env, fake_claude_on_path):
    saved = {k: os.environ.get(k) for k in MANAGED}
    for key in MANAGED:
        os.environ.pop(key, None)
    os.environ["PATH"] = (FAKE_BIN + os.pathsep + BASE_PATH) if fake_claude_on_path else BASE_PATH
    os.environ.update(env)
    llm.reset_provider_cache()
    try:
        provider = llm.pick_provider()
        return {"provider": provider.name, "model": str(getattr(provider, "model", "") or "")}
    except Exception as exc:
        return {"provider": None, **record(exc)}
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        llm.reset_provider_cache()

for case in spec["selectionCases"]:
    entry = {
        "label": case["label"],
        "env": case["env"],
        "fakeClaudeOnPath": bool(case.get("fakeClaudeOnPath")),
        "expected": case["expected"],
    }
    if llm is None:
        entry.update({"provider": None, "error": "ProbeUnavailable",
                      "message": "app.llm could not be imported"})
    else:
        entry.update(select(case["env"], case.get("fakeClaudeOnPath")))
    out["selection"].append(entry)

# ---- the approved runtime still works ------------------------------------
try:
    from app.model_endpoint import classify_endpoint
    verdicts = {url: bool(classify_endpoint(url).allowed) for url in spec["endpointPolicy"]}
    out["functional"].append({"check": "endpointPolicy", "verdicts": verdicts})
except Exception as exc:
    out["functional"].append({"check": "endpointPolicy", **record(exc)})

if spec.get("model2vecPath"):
    try:
        os.environ["BRF_MODEL2VEC_PATH"] = spec["model2vecPath"]
        os.environ["HF_HUB_OFFLINE"] = "1"
        from app.embeddings import Model2VecEmbedder
        embedder = Model2VecEmbedder()
        vector = embedder.embed(["Styrelsen har sitt säte i Göteborgs kommun."])[0]
        out["functional"].append({"check": "model2vec", "ok": True, "name": embedder.name,
                                  "dim": len(vector), "finite": all(v == v for v in vector)})
    except Exception as exc:
        out["functional"].append({"check": "model2vec", "ok": False, **record(exc)})

with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(out, handle, ensure_ascii=False, sort_keys=True)
'''


class Inspection:
    def __init__(self, payload: Payload, rules: dict) -> None:
        self.payload = payload
        self.rules = rules
        self.checks: list[dict] = []

    def add(self, rule: str, target: str, method: str, result: str, why: str = "", **detail) -> None:
        entry = {"rule": rule, "target": target, "method": method, "result": result}
        if why:
            entry["why"] = why
        entry.update(detail)
        self.checks.append(entry)

    # -- structural rules ---------------------------------------------------

    def check_distributions(self) -> None:
        rel, site = self.payload.site_packages()
        installed: dict[str, str] = {}
        if site is not None:
            for meta in sorted(site.glob("*.dist-info")) + sorted(site.glob("*.egg-info")):
                # Fallback only — METADATA's own Name: wins below. Strip the
                # suffix before splitting off the version, or the hyphen in
                # "dist-info" is the one that splits.
                name = re.sub(r"\.(dist|egg)-info$", "", meta.name)
                name = name.rsplit("-", 1)[0] if "-" in name else name
                metadata = meta / "METADATA"
                if metadata.is_file():
                    for line in metadata.read_text(encoding="utf-8", errors="replace").splitlines():
                        if line.lower().startswith("name:"):
                            name = line.split(":", 1)[1].strip()
                            break
                        if not line.strip():
                            break
                installed[normalize_distribution(name)] = meta.name
        self.add(
            "distribution-inventory", rel or RUNTIME_REL,
            "parsed Name: from every *.dist-info/*.egg-info METADATA in the payload",
            PASS if site is not None else FAIL,
            distributions=sorted(installed),
            count=len(installed),
        )
        for item in self.rules["distributions"]:
            key = normalize_distribution(item["name"])
            found = installed.get(key)
            self.add(
                "distribution", item["name"],
                "distribution name present among the payload's parsed metadata",
                PRESENT if found else ABSENT, item["why"],
                **({"foundAs": found} if found else {}),
            )

    def check_path_patterns(self) -> None:
        paths = [rel for rel, _ in self.payload.walk()]
        for item in self.rules["pathPatterns"]:
            hits = sorted(p for p in paths if fnmatch.fnmatch(p, item["glob"]))
            self.add(
                "path-pattern", item["glob"],
                "glob over every file in the payload",
                PRESENT if hits else ABSENT, item["why"],
                matches=hits[:20], matchCount=len(hits),
            )

    def check_filenames(self) -> None:
        rule = self.rules["filenameScan"]
        pattern = re.compile(rule["pattern"])
        hits = sorted(rel for rel, _ in self.payload.walk() if pattern.search(rel))
        self.add(
            "filename-scan", rule["pattern"],
            "regex over every path in the payload",
            PRESENT if hits else ABSENT, rule["why"],
            matches=hits[:20], matchCount=len(hits),
        )

    def check_entry_points(self) -> None:
        rel, site = self.payload.site_packages()
        entries: list[str] = []
        sources = 0
        if site is not None:
            for path in sorted(site.glob("*.dist-info/entry_points.txt")):
                sources += 1
                group = ""
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("[") and line.endswith("]"):
                        group = line[1:-1]
                        continue
                    entries.append(f"{path.parent.name}:[{group}] {line}")
        self.add(
            "entry-point-inventory", rel or RUNTIME_REL,
            "parsed every *.dist-info/entry_points.txt in the payload",
            PASS if site is not None else FAIL,
            files=sources, entryPoints=sorted(entries),
        )
        for item in self.rules["entryPointPatterns"]:
            pattern = re.compile(item["pattern"])
            hits = sorted(e for e in entries if pattern.search(e))
            self.add(
                "entry-point", item["pattern"],
                "regex over every declared entry point in the payload",
                PRESENT if hits else ABSENT, item["why"],
                matches=hits[:20], matchCount=len(hits),
            )

    def check_text(self) -> None:
        scan = self.rules["textScan"]
        pattern = re.compile(scan["pattern"])
        declared = self.rules["declaredReferences"]
        for target in scan["scan"]:
            root_rel = target["root"]
            root = self.payload.resolve(root_rel)
            if root is None or not root.exists():
                self.add("text-scan", root_rel, "regex over file contents",
                         OUT_OF_SCOPE if root is None else ABSENT, target["why"])
                continue
            files = 0
            hits: list[dict] = []
            walk = [(root_rel, root)] if root.is_file() else [
                (f"{root_rel}/{p.relative_to(root).as_posix()}", p)
                for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()
            ]
            for rel, path in walk:
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                files += 1
                for match in pattern.finditer(text):
                    hits.append({"path": rel, "match": match.group(0)})
            undeclared = [h for h in hits if not self._is_declared(h, declared)]
            self.add(
                "text-scan", root_rel,
                f"regex over the contents of {files} readable file(s)",
                PRESENT if undeclared else ABSENT, target["why"],
                files=files, matches=len(hits), undeclared=undeclared[:20],
            )

    @staticmethod
    def _is_declared(hit: dict, declared: list[dict]) -> bool:
        """Is this file covered by a declared reference?

        The text scan only defers; it does not excuse. check_declared_reference
        then counts *every* forbidden name in that file and requires the total
        to equal the declared occurrences, so a second, undeclared name in a
        declared file still fails.
        """
        return any(hit["path"] == item["path"] for item in declared)

    def check_declared_references(self) -> None:
        pattern = re.compile(self.rules["textScan"]["pattern"])
        for item in self.rules["declaredReferences"]:
            path = self.payload.resolve(item["path"])
            if path is None:
                self.add("declared-reference", item["path"], "occurrence count in the artifact",
                         OUT_OF_SCOPE, item["why"])
                continue
            if not path.is_file():
                self.add("declared-reference", item["path"], "occurrence count in the artifact",
                         FAIL, item["why"], detail="declared file is not in the payload")
                continue
            blob = path.read_bytes()
            declared_hits = len(re.findall(item["pattern"].encode(), blob, re.IGNORECASE))
            all_hits = len(pattern.findall(blob.decode("utf-8", "replace")))
            ok = declared_hits == item["expectedOccurrences"] and all_hits == declared_hits
            self.add(
                "declared-reference", f"{item['path']} :: {item['pattern']}",
                "counted occurrences of the declared literal and of every forbidden name in the same file",
                PASS if ok else FAIL, item["why"],
                classification=item["classification"],
                expected=item["expectedOccurrences"],
                declaredOccurrences=declared_hits,
                totalForbiddenNameOccurrences=all_hits,
            )

    # -- behavioural rules --------------------------------------------------

    def run_probe(self) -> None:
        runtime = self.payload.resolve(RUNTIME_REL)
        if runtime is None or not runtime.is_dir():
            self.add("interpreter-probe", RUNTIME_REL, "run the packaged interpreter", FAIL,
                     detail="no packaged runtime in this payload")
            return
        python = runtime / "python" / "bin" / "python3"
        backend = runtime / "backend"
        if not (python.is_file() and backend.is_dir()):
            self.add("interpreter-probe", RUNTIME_REL, "run the packaged interpreter", FAIL,
                     detail="packaged interpreter or backend missing")
            return

        models = sorted((runtime / "models").glob("*")) if (runtime / "models").is_dir() else []
        spec = {
            "forbiddenModules": [m["name"] for m in self.rules["modules"]],
            "forbiddenAttributes": [
                {"module": a["module"], "attribute": a["attribute"]} for a in self.rules["attributes"]
            ],
            "requiredModules": [m["module"] for m in self.rules["requiredPresent"]],
            "guardedOptionalImports": [
                {"module": g["module"], "absentDependency": g["absentDependency"],
                 "availabilityProbe": g["availabilityProbe"]}
                for g in self.rules["guardedOptionalImports"]
            ],
            "retainedModules": [r["module"] for r in self.rules["retainedModules"]],
            "selectionCases": self._selection_cases(),
            "endpointPolicy": [
                "https://api.openai.com/v1",
                "https://api.anthropic.com/v1",
                "http://127.0.0.1:8000/v1",
            ],
            "model2vecPath": str(models[0]) if models else "",
        }

        with tempfile.TemporaryDirectory(prefix="brfv2-inspect-") as tmp:
            tmpdir = Path(tmp)
            (tmpdir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (tmpdir / "probe.py").write_text(PROBE_SOURCE, encoding="utf-8")
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": os.environ.get("HOME", str(tmpdir)),
                "LANG": "C.UTF-8",
                "HF_HUB_OFFLINE": "1",
                "TMPDIR": str(tmpdir),
            }
            proc = subprocess.run(
                [str(python), "-E", "-s", "-B", str(tmpdir / "probe.py"),
                 str(tmpdir / "spec.json"), str(tmpdir / "out.json")],
                cwd=str(backend), env=env, capture_output=True, text=True,
            )
            if proc.returncode != 0 or not (tmpdir / "out.json").is_file():
                self.add("interpreter-probe", RUNTIME_REL, "run the packaged interpreter", FAIL,
                         detail=(proc.stderr or proc.stdout)[-2000:])
                return
            probe = json.loads((tmpdir / "out.json").read_text(encoding="utf-8"))

        self._record_probe(probe)

    def _selection_cases(self) -> list[dict]:
        cases = []
        for item in self.rules["selectionEnvironments"]:
            cases.append({
                "label": item["label"], "env": item["env"],
                "fakeClaudeOnPath": bool(item.get("fakeClaudeOnPath")),
                "expected": "none",
            })
        for item in self.rules["selectionKeys"]:
            cases.append({
                "label": f"BRF_LLM={item['key']} (declared selection key)",
                "env": {"BRF_LLM": item["key"]}, "fakeClaudeOnPath": True, "expected": "none",
            })
        cases.append({
            "label": "the approved self-hosted provider is still selectable",
            "env": {"BRF_LLM": "selfhosted", "BRF_LLM_BASE_URL": "http://127.0.0.1:8000/v1",
                    "BRF_LLM_MODEL": "gemma4:e12b"},
            "fakeClaudeOnPath": False, "expected": "selfhosted",
        })
        return cases

    def _record_probe(self, probe: dict) -> None:
        # A section of the probe that blew up is a finding, not a gap: a
        # payload whose app.llm cannot even be asked what it registers has not
        # demonstrated that it registers nothing.
        for error in probe.get("errors", []):
            self.add("interpreter-probe", error.get("section", "okänd sektion"),
                     "section of the packaged-interpreter probe", FAIL, "",
                     error=error.get("error", ""), message=error.get("message", ""))
        for section, label in (("imports", "forbidden-module imports"),
                               ("selection", "provider selection"),
                               ("required", "required-module imports")):
            if not probe.get(section):
                self.add("interpreter-probe", label,
                         "section of the packaged-interpreter probe", FAIL, "",
                         detail="the probe produced no results for this section")
        why = {item["name"]: item["why"] for item in self.rules["modules"]}
        for entry in probe["imports"]:
            self.add(
                "module-import", entry["module"],
                "import attempted in the packaged interpreter",
                PRESENT if entry["importable"] else ABSENT, why.get(entry["module"], ""),
                error=entry.get("error", ""), message=entry.get("message", ""),
            )
        attr_why = {(a["module"], a["attribute"]): a["why"] for a in self.rules["attributes"]}
        for entry in probe["attributes"]:
            key = (entry["module"], entry["attribute"])
            self.add(
                "module-attribute", f"{entry['module']}.{entry['attribute']}",
                "attribute access attempted in the packaged interpreter",
                PRESENT if entry["reachable"] else ABSENT, attr_why.get(key, ""),
                error=entry.get("error", ""),
            )
        req_why = {item["module"]: item["why"] for item in self.rules["requiredPresent"]}
        for entry in probe["required"]:
            self.add(
                "required-module", entry["module"],
                "import attempted in the packaged interpreter",
                PASS if entry["importable"] else FAIL, req_why.get(entry["module"], ""),
                version=entry.get("version", ""), error=entry.get("error", ""),
            )
        guard_why = {g["module"]: g["why"] for g in self.rules["guardedOptionalImports"]}
        for entry in probe["guarded"]:
            ok = entry.get("hostImportable") and entry.get("available") is False
            self.add(
                "guarded-optional-import", f"{entry['module']} -> {entry['absentDependency']}",
                "imported the host module and called its availability probe",
                PASS if ok else FAIL, guard_why.get(entry["module"], ""),
                hostImportable=entry.get("hostImportable"), available=entry.get("available"),
                error=entry.get("error", ""),
            )
        retained_why = {r["module"]: r["why"] for r in self.rules["retainedModules"]}
        for entry in probe["inert"]:
            results = entry.get("probe") or {}
            ok = entry.get("hasProbe") and all(
                isinstance(v, dict) and v.get("raised") for v in results.values()
            ) and bool(results)
            self.add(
                "retained-module-inert", entry["module"],
                "read the source of every member that can hand out a hosted client and "
                "attempted each import it performs, in the packaged interpreter",
                PASS if ok else FAIL, retained_why.get(entry["module"], ""),
                probe=results,
            )
        self.add(
            "hosted-plugin-registry", "app.llm.hosted_providers()",
            "called the registry the packaged code uses to discover hosted providers",
            PASS if probe.get("hostedPlugins") == [] else PRESENT,
            "A hosted plug-in registered in the packaged runtime would be an implementation the "
            "application could select at any time.",
            registered=probe.get("hostedPlugins"),
        )
        forbidden_ids = {item["id"] for item in self.rules["providerIdentifiers"]}
        for entry in probe["selection"]:
            got = entry.get("provider")
            ok = got == entry["expected"] and got not in forbidden_ids
            self.add(
                "provider-selection", entry["label"],
                "called app.llm.pick_provider() in the packaged interpreter under that environment",
                PASS if ok else FAIL, "",
                env=entry["env"], fakeClaudeOnPath=entry["fakeClaudeOnPath"],
                expected=entry["expected"], selected=got, model=entry.get("model", ""),
                error=entry.get("error", ""),
            )
        for entry in probe["functional"]:
            if entry["check"] == "endpointPolicy":
                verdicts = entry.get("verdicts") or {}
                ok = (
                    verdicts.get("https://api.openai.com/v1") is False
                    and verdicts.get("https://api.anthropic.com/v1") is False
                    and verdicts.get("http://127.0.0.1:8000/v1") is True
                )
                self.add("endpoint-policy", "app.model_endpoint.classify_endpoint",
                         "classified third-party and loopback endpoints in the packaged interpreter",
                         PASS if ok else FAIL,
                         "The packaged code must carry the same endpoint policy the tests proved.",
                         verdicts=verdicts, error=entry.get("error", ""))
            elif entry["check"] == "model2vec":
                ok = bool(entry.get("ok")) and entry.get("dim") == 256 and entry.get("finite")
                self.add("model2vec", "app.embeddings.Model2VecEmbedder",
                         "loaded the bundled weights and embedded a Swedish sentence, offline",
                         PASS if ok else FAIL,
                         "The exclusions must not have damaged the approved self-hosted embedder.",
                         name=entry.get("name", ""), dim=entry.get("dim"),
                         error=entry.get("error", ""))

    # -- scope bookkeeping --------------------------------------------------

    def check_scope(self) -> None:
        for rel, label in ((SHELL_REL, "compiled shell"), (UI_REL, "built desktop UI"),
                           (RUNTIME_REL, "packaged Python runtime")):
            present = self.payload.exists(rel)
            in_scope = self.payload.in_scope(rel)
            self.add(
                "scope", rel, "presence of a payload component",
                PASS if present else (OUT_OF_SCOPE if not in_scope else FAIL),
                f"The {label}.",
            )

    def run(self) -> dict:
        self.check_scope()
        self.check_distributions()
        self.check_path_patterns()
        self.check_filenames()
        self.check_entry_points()
        self.check_text()
        self.check_declared_references()
        self.run_probe()
        findings = [c for c in self.checks if c["result"] in FAILING]
        return {
            "schema": "brfv2-desktop-provider-exclusion/v1",
            "rules": {
                "source": "ops/forbidden_providers.json",
                "sha256": hashlib.sha256(RULES_PATH.read_bytes()).hexdigest(),
            },
            "derivedFrom": "inspection of the payload named in `inspected`; no rule is answered from a stored result",
            "inspected": self.payload.identity(),
            "checks": self.checks,
            "findings": findings,
            "counts": {
                "checks": len(self.checks),
                "absent": sum(1 for c in self.checks if c["result"] == ABSENT),
                "pass": sum(1 for c in self.checks if c["result"] == PASS),
                "outOfScope": sum(1 for c in self.checks if c["result"] == OUT_OF_SCOPE),
                "findings": len(findings),
            },
            "ok": not findings,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--runtime", type=Path, help="the staged runtime tree")
    group.add_argument("--root", type=Path, help="an install-shaped root")
    group.add_argument("--installed", nargs="?", const=Path("/"), type=Path,
                       metavar="PREFIX",
                       help="the installed product under PREFIX (default /), mounted component "
                            "by component instead of walking a live filesystem")
    parser.add_argument("--scope", default="", help="label for the inspected artifact")
    parser.add_argument("--artifact", default="", help="artifact filename this payload came from")
    parser.add_argument("--artifact-sha256", default="", help="SHA-256 of that artifact")
    parser.add_argument("--json", type=Path, help="write the full result here")
    parser.add_argument("--identity-only", action="store_true",
                        help="print only the payload identity hash (for comparing a staged tree "
                             "against the same tree unpacked from the package)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    if args.runtime:
        payload = Payload.from_runtime(args.runtime)
    elif args.installed is not None:
        payload = Payload.from_installed(args.installed, args.scope or "installed")
    else:
        payload = Payload.from_root(args.root, args.scope or "artifact")
    if args.scope:
        payload.scope = args.scope

    if args.identity_only:
        print(payload.identity()["payloadSha256"])
        return 0

    result = Inspection(payload, rules).run()
    if args.artifact:
        result["inspected"]["artifact"] = args.artifact
    if args.artifact_sha256:
        result["inspected"]["artifactSha256"] = args.artifact_sha256

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")

    if not args.quiet:
        counts = result["counts"]
        print(f"payload:  {result['inspected']['scope']} "
              f"({result['inspected']['files']} filer, sha256={result['inspected']['payloadSha256'][:16]}…)")
        print(f"regler:   ops/forbidden_providers.json@{result['rules']['sha256'][:16]}…")
        print(f"kontroller: {counts['checks']}  frånvarande: {counts['absent']}  "
              f"godkända: {counts['pass']}  utanför omfång: {counts['outOfScope']}  "
              f"fynd: {counts['findings']}")
        for finding in result["findings"]:
            print(f"  FYND [{finding['rule']}] {finding['target']} -> {finding['result']}")
            for key in ("matches", "undeclared", "message", "error", "detail", "selected", "probe",
                        "registered", "verdicts", "foundAs"):
                if finding.get(key):
                    print(f"        {key}: {json.dumps(finding[key], ensure_ascii=False)[:400]}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
