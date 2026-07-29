# XS-51 — the self-hosted boundary made structural in the Fedora RPM

Implementation record for the XS-51 repair. This is the implementer's evidence,
not an independent verdict: BP2 review is the next step and has not happened.

---

## 1. What was wrong

The XS-49 artifact shipped hosted-provider material while its own manifest said
it did not. Confirmed against the package installed on this machine before the
repair, by the inspector this change introduces
(`ops/inspect_payload.py --installed`, 24 findings):

| residual | where |
|---|---|
| `anthropic-0.116.0.dist-info` | `runtime/python/lib/python3.12/site-packages/` |
| `hf_xet-1.5.1.dist-info` | same |
| `huggingface_hub/inference/` — `InferenceClient`, `AsyncInferenceClient`, `_mcp`, and `_providers/` with 20 third-party inference-provider adapters (`black_forest_labs`, `cerebras`, `clarifai`, `cohere`, `fal_ai`, `featherless_ai`, `fireworks_ai`, `groq`, `hf_inference`, `hyperbolic`, `nebius`, `novita`, `nscale`, `openai`, `publicai`, `replicate`, `sambanova`, `scaleway`, `together`, `zai_org`) | same |
| `huggingface_hub/inference_api.py` (legacy hosted `InferenceApi`) | same |
| entry point `tiny-agents = huggingface_hub.inference._mcp.cli:app` | `huggingface_hub-0.36.2.dist-info/entry_points.txt` |
| `AnthropicProvider`, `ClaudeCLIProvider` and the `BRF_LLM=api` / `BRF_LLM=cli` branches that select them | `runtime/backend/app/llm.py` |
| hosted provider labels `anthropic-api` → "Anthropic", `claude-cli` → "Claude CLI" | the built UI bundle |

`BUNDLE.json` asserted `"excludedPackages": ["anthropic", "hf_xet", "pip",
"setuptools"]` — a constant, written whether or not anything was removed. The
loop it described used quoted globs (`rm -rf "$SITE/$pattern"` over
`hf_xet-*`, `pip-*`, `setuptools-*`), so every wildcard pattern expanded to a
literal filename that did not exist and silently removed nothing. The two
`.dist-info` directories that shipped are exactly the two patterns with a
wildcard.

The runtime control was real and is unchanged: `app.desktop.apply_model_runtime`
pins `BRF_LLM=selfhosted`, so nothing was ever *selected*. The defect was that
the payload and its provenance declaration disagreed, and that the boundary
rested on a policy the running program applied to itself rather than on the
contents of the package.

---

## 2. What was changed

### 2.1 The hosted providers became a removable plug-in

`backend/app/llm_hosted.py` (new) holds `AnthropicProvider`,
`ClaudeCLIProvider`, their auto-detection rules, their `BRF_LLM` keys and their
operator hints. `backend/app/llm.py` keeps only providers that run on
infrastructure the deployment controls, and discovers hosted ones at selection
time through `hosted_providers()`.

`app.llm` now names no hosted provider at all — asserted by a unit test
(`test_app_llm_itself_names_no_hosted_provider`), because an identifier left
behind in the packaged module would ship even when the implementation does not.

The delivery does not copy `llm_hosted.py`. With the file absent the
registry iterates over nothing: the implementations, their registration and
their selection keys are gone together, and `BRF_LLM=api` / `BRF_LLM=cli` fall
through to `none` because there is no branch left that could match them.

Hosted support is unchanged for everything that is not the desktop payload —
`anthropic` stays in `backend/pyproject.toml`, the providers are still
registered, and `make eval` still uses them.

### 2.2 The delivery-tree identity now covers the new build inputs

`ops/lib/repro.sh:REPRO_DELIVERY_PATHS` — the tracked paths the artifact is a
function of — gained `ops/forbidden_providers.json`, `ops/prune_payload.py` and
`ops/inspect_payload.py`. Without that, this change would have introduced three
files that decide what ships and what the manifest says, while two commits with
different exclusion logic still reported the same delivery tree. Adding them
changed the delivery tree, and therefore the artifact, which is the correct
consequence.

### 2.3 Removal is separate from certification

`ops/forbidden_providers.json` (new) states the rules and only the rules.
`ops/prune_payload.py` (new) removes: forbidden distributions *with* their
metadata, `huggingface_hub/inference/` and `inference_api.py`,
`app/llm_hosted.py`, and entry points matching the forbidden pattern —
rewriting each affected `RECORD` so the metadata still matches the tree.

`ops/inspect_payload.py` (new) answers the rules against the payload. Nothing
else is allowed to. It runs in three scopes with one rule set: `--runtime` (the
staged tree), `--root` (an unpacked RPM or the buildroot), `--installed` (the
machine the package is on).

### 2.4 `BUNDLE.json` is now derived from the payload

`ops/build-runtime.sh` runs the inspector against the staged tree and copies the
result into `BUNDLE.json` under `providerExclusion`, verbatim — 45 checks, each
naming the rule, the target, the method used, and what was found. A finding
fails the build; there is no flag to continue past one. The old
`excludedPackages` constant is gone.

`ops/package-desktop.sh` then unpacks the built RPM and asserts two separate
things:

1. the same rules answered against the unpacked package find nothing;
2. the payload identity hash recomputed from the unpacked runtime equals the one
   recorded in `BUNDLE.json`.

(2) is what makes the manifest a statement about *this* RPM rather than about a
staged tree that may since have moved. The hash covers every file's path, mode
and content, excluding exactly `BUNDLE.json` (which carries the hash) and
`requirements.lock.txt` (which packaging deliberately drops).

### 2.5 Two Fedora BRP passes had to be turned off for (2) to be true

Both rewrite the buildroot *after* `BUNDLE.json` is written, so the package
could not describe itself while they ran:

* `add-determinism --handler=-pyc` — it rewrote all 1808 `.pyc` files "to a
  normalized version". The bundle's bytecode is already deterministic
  (`compileall --invalidation-mode unchecked-hash`, source path remapped to the
  install prefix), so this bought nothing.
* `%define __brp_strip_lto %{nil}` — `brp-strip-lto` runs `strip` over the three
  static archives numpy and pymupdf ship, and `strip` on an archive rewrites its
  member headers with the current clock. **Two consecutive builds produced two
  different `.a` files.** That non-determinism existed before this change and
  was invisible only because add-determinism's `ar` handler normalized it away
  afterwards. Not stripping them removes the cause; the `ar` handler stays on.

This is the one place where the repair reaches outside provider exclusion, and
it is load-bearing for the manifest-describes-the-artifact property.

### 2.6 Artifact-level enforcement

`backend/tests/test_desktop_artifact.py` (new, 40 tests, `artifact` marker)
unpacks the built RPM, runs the inspector against it, and — when the package is
installed — against `/usr` as well. It asserts three separate things:

* every rule class actually **ran** (`test_the_inspection_actually_ran_every_class_of_rule`), so deleting a rule cannot turn the suite green;
* every answer came back clean;
* two coarse checks derived *without* the inspector, straight from `rpm -qlp`
  and `rpm -qRp`, so a bug in the inspector cannot make the package look clean
  on its own.

Self-skips without an artifact; `BRFV2_REQUIRE_ARTIFACT=1` turns the skip into a
failure, and the delivery run sets it.

**The test was verified to fail on the defect**: run against the pre-repair
package installed on this machine it reported 24 findings and 3 hard failures.

---

## 3. Identity

| | |
|---|---|
| base commit | `ac3cd2b34fdd9e107556ccd27f4a334c50a82819` |
| final repair commit | the head of this branch — the commit that contains this file. A commit cannot record its own hash, so the two identities below are the ones that determine the artifact, and the SHA is reported with the push. |
| branch | `itsimonfredlingjack/xs-51-gor-provider-exkluderingen-sann-i-fedora-rpmn` |
| `dirty` | `false` (asserted by `ops/lib/repro.sh:repro_require_clean_tree`; recorded in the provenance receipt) |
| delivery tree | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` |
| artifact | `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm` |
| size | 574 604 029 bytes |
| **SHA-256** | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` |
| RPM NEVRA | `brf-dokument-ai-0.2.0-1.fc44.x86_64` |
| RPM BUILDTIME / BUILDHOST | `1785196800` / `reproducible.brfdokumentai.se` |
| payload compressor | `zstd` (`w3.zstdio`) |
| installed runtime payload hash | `9fe3f0e36989f19261d4b6e47a3aa6fb03832e3df7732de95e89699d5b5139a5` |
| whole-artifact payload hash | `b44a5bb286e4dba0bca2b5c65962486d6afb479f99c14cf268c11573e1b86964` (4679 files) |
| rule set | `ops/forbidden_providers.json` @ `500e8c852a3539b6cb1c4036f1ee10ce9af5c6d85894e7172b6fb286b3fb109f` |

**The delivery tree, not the commit, determines the artifact.**
`ops/lib/repro.sh:REPRO_DELIVERY_PATHS` excludes `docs/`, so adding this record
to the delivery commit cannot move a byte of the package — which is what lets
evidence and delivery share one commit. Demonstrated in passing: commit
`eef3b66d` and the final commit have the same delivery tree and produce the
same RPM SHA-256, and separately, three earlier commits with an identical
delivery tree each produced SHA-256 `6659ba4a…` — the artifact moved only when
the delivery sources did.

Consequence worth stating plainly: the acceptance JSON in
`xs51-desktop-acceptance-installed.json` embeds the provenance receipt of the
build it ran against, whose `commit` field reads `eef3b66d072fde00e0ef45f1c251013c70f14cf5`.
That commit differs from the final commit only by the addition and update of
these `docs/evidence/**` files. Both have delivery tree `a702a337…` and both
produce SHA-256 `6ba028fb…`. §6's two clean-checkout builds were likewise run
from `eef3b66d` — for the same reason: a build has to be run from a commit that
exists, and a record of that build cannot be inside the commit it names without
changing it.

---

## 4. Payload inspection of the exact artifact

45 checks, 0 findings. Full output: `providerExclusion` in
`dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm.provenance.json` (whole artifact)
and in `BUNDLE.json` inside the package (the runtime tree). Reproduce with:

```
rpm2cpio dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm | (mkdir -p /var/tmp/x && cd /var/tmp/x && cpio -idm)
ops/inspect_payload.py --root /var/tmp/x --scope unpacked-rpm
```

| rule | target | method | result |
|---|---|---|---|
| `scope` | `usr/bin/brfv2-desktop` | presence of a payload component | **pass** |
| `scope` | `usr/lib/BRF Dokument-AI/ui` | presence of a payload component | **pass** |
| `scope` | `usr/lib/BRF Dokument-AI/runtime` | presence of a payload component | **pass** |
| `distribution-inventory` | site-packages | parsed `Name:` from all 38 `*.dist-info` METADATA | **pass** |
| `distribution` | `anthropic` | name present among the payload's parsed metadata | **absent** |
| `distribution` | `hf_xet` | same | **absent** |
| `distribution` | `pip` | same | **absent** |
| `distribution` | `setuptools` | same | **absent** |
| `path-pattern` | `**/huggingface_hub/inference/**` | glob over every file in the payload | **absent** |
| `path-pattern` | `**/huggingface_hub/inference_api.py*` | same | **absent** |
| `path-pattern` | `**/anthropic/**` | same | **absent** |
| `path-pattern` | `**/hf_xet/**` | same | **absent** |
| `path-pattern` | `**/app/llm_hosted.py*` | same | **absent** |
| `filename-scan` | `anthropic|hf_xet|llm_hosted|huggingface_hub/inference` | regex over all 4679 paths | **absent** |
| `entry-point-inventory` | site-packages | parsed all 18 entry points in 13 `entry_points.txt` | **pass** |
| `entry-point` | `anthropic|claude|hf_xet|huggingface_hub.inference|tiny-agents` | regex over every declared entry point | **absent** |
| `text-scan` | `runtime/backend` | regex over the contents of 22 readable files | **absent** |
| `text-scan` | `ui` | regex over the contents of 6 readable files | **absent** |
| `declared-reference` | `usr/bin/brfv2-desktop :: ANTHROPIC_API_KEY` | counted the declared literal *and* every forbidden name in the same file | **pass** (1 = 1, total 1) |
| `declared-reference` | `runtime/backend/app/schemas.py :: claude-opus-4-8` | same | **pass** (1 = 1, total 1) |
| `module-import` | `anthropic` | import attempted in the packaged interpreter | **absent** (`ModuleNotFoundError`) |
| `module-import` | `hf_xet` | same | **absent** (`ModuleNotFoundError`) |
| `module-import` | `huggingface_hub.inference` | same | **absent** (`ModuleNotFoundError`) |
| `module-import` | `huggingface_hub.inference._providers` | same | **absent** (`ModuleNotFoundError`) |
| `module-import` | `huggingface_hub.inference_api` | same | **absent** (`ModuleNotFoundError`) |
| `module-import` | `app.llm_hosted` | same | **absent** (`ModuleNotFoundError`) |
| `module-attribute` | `huggingface_hub.InferenceClient` | attribute access in the packaged interpreter | **absent** (`ModuleNotFoundError` from the lazy `__getattr__`) |
| `module-attribute` | `huggingface_hub.AsyncInferenceClient` | same | **absent** |
| `required-module` | `model2vec` | import attempted in the packaged interpreter | **pass** |
| `required-module` | `huggingface_hub` | same | **pass** (0.36.2) |
| `required-module` | `huggingface_hub.hf_api` | same | **pass** |
| `required-module` | `app.llm` | same | **pass** |
| `required-module` | `app.desktop` | same | **pass** |
| `guarded-optional-import` | `huggingface_hub.file_download → hf_xet` | imported the host module, called `is_xet_available()` | **pass** (host imports, availability `False`) |
| `retained-module-inert` | `huggingface_hub._inference_endpoints` | read the source of `client` / `async_client` and attempted every import they perform | **pass** (both resolve only to `huggingface_hub.inference._client` / `._generated._async_client`, both `ModuleNotFoundError`) |
| `hosted-plugin-registry` | `app.llm.hosted_providers()` | called the registry the packaged code uses | **pass** (`[]`) |
| `provider-selection` | auto + `ANTHROPIC_API_KEY` exported | `pick_provider()` in the packaged interpreter | **pass** → `none` |
| `provider-selection` | auto + a `claude` executable on `PATH` | same | **pass** → `none` |
| `provider-selection` | `BRF_LLM=api` + `ANTHROPIC_API_KEY` | same | **pass** → `none` |
| `provider-selection` | `BRF_LLM=cli` + `claude` on `PATH` | same | **pass** → `none` |
| `provider-selection` | `BRF_LLM=api` (declared key) | same | **pass** → `none` |
| `provider-selection` | `BRF_LLM=cli` (declared key) | same | **pass** → `none` |
| `provider-selection` | `BRF_LLM=selfhosted` + loopback base URL | same | **pass** → `selfhosted`, model `gemma4:e12b` |
| `endpoint-policy` | `app.model_endpoint.classify_endpoint` | classified third-party and loopback endpoints | **pass** (`api.openai.com` `False`, `api.anthropic.com` `False`, `127.0.0.1:8000` `True`) |
| `model2vec` | `app.embeddings.Model2VecEmbedder` | loaded the bundled weights and embedded a Swedish sentence, offline | **pass** (`model2vec:potion-multilingual-128M`, dim 256, all finite) |

### 4.1 The two declared references, and why they are not exemptions

Both are *counted*, and the count includes every forbidden name in the file, so
a second undeclared occurrence still fails.

* **`usr/bin/brfv2-desktop` :: `ANTHROPIC_API_KEY`** — the compiled shell removes
  that variable from the backend child's environment
  (`src-tauri/src/main.rs:350`). The literal is the name of something being
  *deleted*. It is retained deliberately: removing a security scrub to make a
  string search pass would weaken the product to flatter the evidence.
* **`runtime/backend/app/schemas.py` :: `claude-opus-4-8`** — the default value
  of the per-tenant `aiModel` setting. It names no implementation, registers
  nothing and selects nothing. The desktop never uses it for generation
  (`apply_model_runtime` always exports `ModelRuntimeConfig.model`, default
  `gemma4:e12b`, and `app.answer` prefers the provider's own model over the
  setting — the selection probe above shows the packaged runtime reporting
  `gemma4:e12b`), and the desktop UI has no control that displays it. Left
  alone because changing a persisted per-tenant default is a persistence change
  with no packaging necessity, and it would break the repository's hosted
  dev/eval default, which this repair must preserve. See §8.

### 4.2 One module retained, proven inert

`huggingface_hub._inference_endpoints` stays. `huggingface_hub.hf_api` imports
it at module scope, and model2vec reaches `hf_api` through its model-card path,
so removing it breaks the approved embedder outright — verified:
`ModuleNotFoundError: No module named 'huggingface_hub._inference_endpoints'`
raised from `model2vec/persistence/persistence.py`. It is a management dataclass
for HF Inference Endpoints, not an inference-provider adapter, and the only
route from it to a hosted client is `InferenceEndpoint.client` /
`.async_client`, whose imports the inspection resolves and shows to fail.

`huggingface_hub` also keeps guarded optional imports of `hf_xet` in its own
sources. The distribution is gone, `is_xet_available()` returns `False`, and
`huggingface_hub.file_download` imports cleanly — proven, not asserted. Vendored
third-party sources are held to the structural rules rather than to a content
sweep; editing them to erase names would risk the approved embedder for no gain.

---

## 5. The approved runtime still works

Real model path, no mocks and no hosted substitutions.

* **model2vec** — loaded from the bundled weights inside the package, offline
  (`HF_HUB_OFFLINE=1`), embedding a Swedish sentence to a 256-dimension finite
  vector. Verified in three places: the runtime build's smoke test, the
  inspection of the unpacked RPM, and the inspection of the installed tree.
* **Self-hosted provider** — selectable from the packaged interpreter
  (`selfhosted`, `gemma4:e12b`), and exercised for real by the installed
  acceptance against Gemma 4 12B on `agenntserver` via
  `http://127.0.0.1:8000/v1` (served:
  `…/gemma-4-12b-it-UD-Q4_K_XL.gguf`).
* **Endpoint policy** — unchanged and present in the package;
  `https://api.anthropic.com/v1` is refused with `hostname_not_allowed`.

### Installed acceptance — `/usr/bin/brfv2-desktop`

`docs/evidence/xs51-desktop-acceptance-installed.json`, exit 0, 121.8 s.
Screenshots: `xs51-desktop-{setup,documents,answer-highlight,refusal,settings}.png`.

```
backend/.venv/bin/python backend/scripts/desktop_acceptance.py \
  --application /usr/bin/brfv2-desktop \
  --artifact dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm \
  --evidence-dir <scratch> \
  --output docs/evidence/xs51-desktop-acceptance-installed.json
```

* installed package `brf-dokument-ai-0.2.0-1.fc44.x86_64`; `rpm --verify` exit 0,
  zero differences — the installed tree is still the artifact.
* artifact SHA-256 recorded in the evidence matches §3.
* model runtime: `selfhosted` / `gemma4:e12b` / label `agenntserver` / ready.
* embedder: `model2vec:potion-multilingual-128M`; OCR available (`swe`).
* grounded answer: *"Styrelsen har sitt säte i Göteborgs kommun."* with a
  verbatim citation resolved to *Stadgar Brf Gjutformen 12.pdf* p.1 and a page
  highlight rect; provenance rendered as **"Gemma 4 12B · Self-hosted"**.
* refusal: *"Vilka öppettider har föreningens planetarium?"* → `OTILLRÄCKLIGT
  UNDERLAG`, 0 citations.
* security boundary: `api.openai.com` and `api.anthropic.com` rejected
  `hostname_not_allowed`; `8.8.8.8` rejected `address_not_self_hosted`;
  off-host plaintext rejected `plaintext_off_host`; loopback approved;
  tampered config file recovered; CSP blocked a direct `connect-src` to the
  model service from the web view; `window.__TAURI__` undefined; a remote IPC
  `set_title` denied by ACL.
* lifecycle: clean shutdown, abrupt termination, retained state, backup/restore,
  model-runtime-unavailable — all exercised.
* failure surfaces: backend death and startup failure surfaced to the user.

---

## 6. Reproducibility — two clean checkouts

```
ops/verify-reproducible.sh \
  /home/aidev/brfv2-repro-xs51/a \
  /home/aidev/brfv2-repro-xs51/b-longer-checkout-path \
  eef3b66d072fde00e0ef45f1c251013c70f14cf5
```

`ops/verify-reproducible.sh` clones this repository twice with `git clone
--no-local`, detaches each at the commit, asserts both are clean, and installs
each checkout's dependencies from the locks (`uv sync`, `npm ci`). No build
output, installed tree, virtual environment or cache is shared between them:
each stages its own 778 MB runtime and compiles its own Rust shell. The pinned
inputs (CPython, uv, embedder weights) are content-addressed by SHA-256 in
`ops/pins.json` and re-verified from bytes on every build — a cache may hold
them, it never decides what they are.

| | checkout A | checkout B |
|---|---|---|
| path | `/home/aidev/brfv2-repro-xs51/a` | `/home/aidev/brfv2-repro-xs51/b-longer-checkout-path` |
| filename | `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm` | same |
| size | 574 604 029 bytes | 574 604 029 bytes |
| SHA-256 | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` |
| `commit` in receipt | `eef3b66d072fde00e0ef45f1c251013c70f14cf5` | same |
| `dirty` | `false` | `false` |
| delivery tree | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` | same |
| payload inspection | 45 checks, **0 findings** | 45 checks, **0 findings** |
| whole-artifact payload hash | `b44a5bb286e4dba0bca2b5c65962486d6afb479f99c14cf268c11573e1b86964` | same |

**Byte comparison:** `cmp -s A B` → identical (exit 0). Machine-readable
result: `docs/evidence/xs51-reproducibility.json`.

The artifact delivered from this checkout
(`dist/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm`) was independently compared
against checkout A with `cmp -s` — also byte-identical. Three different
absolute paths, one artifact.

Build epoch, build host and source prefix are fixed inputs, not observations:
`SOURCE_DATE_EPOCH=1785196800` from `ops/pins.json`, `%{_buildhost}` overridden
to `reproducible.brfdokumentai.se`, and the checkout path remapped to
`/builddir/brfv2` (plus `/builddir/cargo` and `/builddir/rustup`) via
`--remap-path-prefix`; the Tauri crate is compiled through the canonical
symlink `/var/tmp/brfv2-desktop-shell` so `CARGO_MANIFEST_DIR` is the same
string from every checkout.

---

## 7. Verification run

Fedora 44, kernel 7.1.5-200.fc44.x86_64. Toolchain: rpm/rpmbuild 6.0.2,
add-determinism 0.7.3, rustc 1.97.1, cargo 1.97.1, node 22.22.2, npm 10.9.7,
uv 0.11.32, system python 3.14.6, bundled + venv CPython 3.12.13 (+20260718,
Clang 22.1.3), git 2.55.0. Build epoch `SOURCE_DATE_EPOCH=1785196800`
(`ops/pins.json`, `2026-07-28T00:00:00Z`).

| step | command | outcome |
|---|---|---|
| clean dependency install | `ops/setup.sh` | exit 0 — uv, `backend/.venv`, both `node_modules`, embedder cache, chromium |
| backend suite (incl. provider, packaging, isolation, artifact) | `cd backend && BRFV2_REQUIRE_ARTIFACT=1 uv run pytest -q` | **650 passed, 3 skipped**, 1 warning |
| — of which artifact-level | `make desktop-verify-artifact` (`BRFV2_REQUIRE_ARTIFACT=1 pytest backend/tests/test_desktop_artifact.py`) | **40 passed** |
| — of which provider plug-in | `… pytest -q tests/test_llm.py` | 44 passed, 1 skipped |
| isolation subset | `cd backend && uv run pytest -q tests/test_isolation.py tests/test_lifecycle.py tests/test_auth.py` | **48 passed** |
| canonical frontend | `cd brfv2-mockup && npm run test` | **21 passed** (1 file) |
| legacy root frontend | `npm test` | **68 passed** (11 files) |
| browser E2E | `cd brfv2-mockup && npm run test:e2e` | **11 passed** (chromium) |
| Rust | `cargo test --locked --manifest-path src-tauri/Cargo.toml` | **5 passed**, 0 failed |
| lint (canonical) | `cd brfv2-mockup && npm run lint` | clean, 0 findings |
| lint (legacy root) | `npm run lint` | 0 errors, pre-existing `no-unused-vars` warnings in `src/` (untouched legacy prototype) |
| production build (canonical) | `cd brfv2-mockup && npm run build` | exit 0 (chunk-size advisory only) |
| production build (legacy) | `npm run build` | exit 0 (chunk-size advisory only) |
| staged-runtime inspection | `ops/build-runtime.sh` | 45 checks, **0 findings** |
| artifact inspection | `ops/package-desktop.sh` | 45 checks, **0 findings**; manifest ↔ package payload hash equal |
| installed inspection | `ops/inspect_payload.py --installed` | 45 checks, **0 findings** |
| installed acceptance | `desktop_acceptance.py --application /usr/bin/brfv2-desktop` | exit 0, all phases |
| reproducible build | `ops/verify-reproducible.sh /home/aidev/brfv2-repro-xs51/a /home/aidev/brfv2-repro-xs51/b-longer-checkout-path eef3b66d` | **byte-identical**, exit 0 — §6 |
| whitespace | `git diff --check HEAD~1 HEAD` | clean, 0 findings |
| patch integrity | `git format-patch -1 --stdout HEAD` then `git apply --check --whitespace=error-all --reverse` on a clean tree | reverse-applies cleanly, 0 whitespace errors |
| working tree | `git status --porcelain` | empty — `dirty: false` |

**Skipped tests (3, all self-skipping and unrelated to this change):** the
`llm`-marked real-provider smoke test (`RUN_LLM_TESTS` unset), and two
`realdata`-marked tests that walk the gitignored `backend/data/tenants`.
The 40 previously-skipped `artifact` tests now run.

**No check was weakened, skipped or rewritten to obtain a pass.** Three checks
failed during the work and each was fixed at the cause:

1. the manifest ↔ package payload-hash assertion (fixed by disabling the two
   BRP passes that rewrote the buildroot after the manifest was written — §2.5);
2. `.dist-info` name parsing, which split on the hyphen inside `dist-info` and
   therefore matched nothing (fixed in both the pruner and the inspector);
3. the artifact test's unpack directory, which exhausted a 7.3 GB tmpfs (moved
   next to the build output).

**Type checking:** none is configured in this repository. The JavaScript
surfaces have no `tsc`/`jsconfig` checked-JS setup and the Python backend has no
mypy/pyright configuration; `oxlint` and `cargo`'s own type checking are what
exist and both ran. Recorded rather than silently omitted.

---

## 8. Remaining limitations

1. **`Settings.aiModel` still defaults to `claude-opus-4-8`** in the shipped
   `schemas.py`. It is a per-tenant preference that the desktop never uses for
   generation and never displays (§4.1), it is declared and counted by the
   inspection rather than hidden, and the packaged runtime demonstrably reports
   `gemma4:e12b`. Changing it is a persistence change with no packaging
   necessity that would also break the repository's hosted dev/eval default, so
   it is left for a deliberate decision. A reviewer grepping the payload for
   "claude" will find this one string.
2. **The acceptance screenshot filenames are hardcoded `xs49-*`** in
   `backend/scripts/desktop_acceptance.py`. Running the acceptance with the
   default `--evidence-dir docs/evidence` silently overwrites XS-49's committed
   screenshots. This run used an isolated evidence directory and copied the
   images to `xs51-*` names; the XS-49 files are unmodified. The hardcoded names
   are a pre-existing trap, not repaired here.
3. **`npm run build` at the repository root writes to `dist/`**, the same
   directory the RPM is delivered into, and deletes the artifact. Hit once
   during this run; the package was rebuilt (byte-identically). Pre-existing and
   not repaired here — the ordering requirement is: build the legacy frontend
   *before* packaging, never after.
4. **`brp-strip-lto` produced non-deterministic static archives** before this
   change (§2.5). It was masked by add-determinism, so the XS-49 reproducibility
   claim was not wrong — but it rested on one BRP pass cancelling another.
   It is now removed at the cause rather than compensated.
5. **The `text-scan` rule does not cover vendored third-party sources or the
   compiled shell.** Both are covered instead by structural rules and behavioural
   probes, and the reason is recorded in `forbidden_providers.json`
   (`textScan.notScanned`). This is a deliberate scoping decision, stated so it
   is reviewable rather than discovered.
6. **The committed acceptance JSON names the pre-evidence commit** in its
   embedded provenance receipt (§3). Unavoidable without an infinite regress;
   the delivery tree and artifact SHA-256 are identical, and the two
   clean-checkout builds from the final commit demonstrate it.
7. **Hosted-provider support outside the desktop is untested end to end here.**
   `make eval` against the hosted provider needs a logged-in `claude` CLI or an
   API key, which this environment does not have. The unit-level contract is
   covered (`TestHostedProviderPlugin`), and no hosted code path was modified
   other than being moved between modules.

---

## 9. Status

Repaired candidate, ready for independent BP2 review. **BP2 is not approved by
this record.**
