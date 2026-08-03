.PHONY: setup backend backend-pilot require-pilot-llm frontend frontend-legacy mobile mobile-build mobile-test \
        desktop-runtime desktop-build desktop-run desktop-check desktop-package desktop-install desktop-uninstall desktop-acceptance \
        invoice-acceptance intake-acceptance desktop-acceptance-full invoice-rules-lock \
        test test-isolation eval eval-b eval-fast eval-sweep \
        eval-selfhosted eval-b-selfhosted desktop-acceptance-installed desktop-verify-reproducible demo demo-stop demo-status demo-reset \
        build build-legacy model-readiness model-readiness-selftest \
        model-readiness-selftest-negative

# Generation default for dev + eval is the standard hosted provider (logged-in `claude`
# CLI, or Anthropic SDK when ANTHROPIC_API_KEY is set) — no env needed. Dev/eval use only
# synthetic BRF data, so no data-residency constraint applies there.
#
# Pilot/production generation is the Gemma 4 12B service on `agenntserver`
# (Ubuntu + RTX 4070). The client must never silently fall back to a smaller
# local model. Supply BRF_LLM_BASE_URL explicitly: normally
# http://127.0.0.1:8000/v1 when the backend runs on agenntserver or when port
# 8000 is SSH-forwarded from that server.
BRF_LLM_BASE_URL ?=
BRF_LLM_MODEL ?= gemma4:e12b
SELFHOSTED_ENV = BRF_LLM=selfhosted BRF_LLM_BASE_URL=$(BRF_LLM_BASE_URL) BRF_LLM_MODEL=$(BRF_LLM_MODEL)

setup:              ## Engångsuppsättning från ren checkout (uv, venv, node_modules, vikter, browser)
	@ops/setup.sh

backend:            ## API-server på :8787 (dev-läge)
	cd backend && uv run uvicorn app.main:create_app --factory --port 8787

require-pilot-llm:
	@test -n "$(BRF_LLM_BASE_URL)" || (echo "BRF_LLM_BASE_URL måste peka på agenntserver Gemma 4 12B (oftast http://127.0.0.1:8000/v1 via tunnel)."; exit 1)

backend-pilot: require-pilot-llm  ## API-server i pilotläge mot Gemma 4 12B på agenntserver
	cd backend && BRF_MODE=pilot $(SELFHOSTED_ENV) uv run uvicorn app.main:create_app --factory --port 8787

frontend:           ## Kanoniska UI:t i brfv2-mockup på :5173
	@test -d brfv2-mockup/node_modules || (echo "brfv2-mockup/node_modules saknas — kör 'make setup' först."; exit 1)
	cd brfv2-mockup && npm run dev

frontend-legacy:    ## Äldre backendkopplad prototyp i rotens src/
	npm run dev

mobile:             ## Mobilklienten Källa (xs_mobilapp) på :5174 — kräver backend på :8787
	@test -d xs_mobilapp/node_modules || (echo "xs_mobilapp/node_modules saknas — kör 'cd xs_mobilapp && npm install'."; exit 1)
	cd xs_mobilapp && npm run dev

mobile-build:       ## Produktionsbygge av mobilklienten; backend serverar den på /m
	cd xs_mobilapp && npm run build

mobile-test:        ## Mobilklientens enhetstester + browseracceptans + tillgänglighet
	cd xs_mobilapp && npm test && npm run lint && npm run typecheck && npm run test:e2e

desktop-runtime:    ## Stega den paketerade Python-körmiljön (src-tauri/runtime, ~776 MB)
	@ops/build-runtime.sh

desktop-build:      ## Bygg kanoniskt UI + release-skalet (ingen installatör)
	@test -x backend/.venv/bin/python || (echo "backend/.venv saknas — kör 'make setup' först."; exit 1)
	@test -d brfv2-mockup/node_modules || (echo "brfv2-mockup/node_modules saknas — kör 'make setup' först."; exit 1)
	cd brfv2-mockup && npm run build
	cargo build --release --locked --manifest-path src-tauri/Cargo.toml

desktop-run: desktop-build  ## Kör release-skalet mot checkouten (Ctrl+C eller stäng fönstret)
	./src-tauri/target/release/brfv2-desktop

desktop-check:      ## Rust-enhetstester + desktopadapterns pytest
	cargo test --locked --manifest-path src-tauri/Cargo.toml
	backend/.venv/bin/pytest -q backend/tests/test_desktop.py

desktop-package: desktop-runtime  ## Bygg distributionsartefakten (RPM) från ren checkout
	@ops/package-desktop.sh

desktop-install: desktop-runtime  ## Bygg och installera RPM:en (kräver sudo; dnf löser tesseract/webkit)
	@ops/package-desktop.sh --install

desktop-uninstall:  ## Avinstallera paketet (användardata under ~/.local/share lämnas kvar)
	sudo dnf remove -y brf-dokument-ai

# Acceptansens evidens namnges efter körningen, inte efter det ärende som råkade
# vara öppet när skriptet skrevs. Sätt RUN_LABEL=... för att låta flera körningar
# ligga sida vid sida; redan committad evidens skrivs aldrig över utan att
# --overwrite-evidence begärs uttryckligen.
RUN_LABEL ?= pilot

desktop-acceptance: desktop-build  ## Full journey-acceptans mot riktig Tauri/WebKitGTK + självhostad modell
	backend/.venv/bin/python backend/scripts/desktop_acceptance.py \
	  --run-label $(RUN_LABEL)

# Fakturaarbetsytan behöver ingen modell — granskningen är deterministisk hela
# vägen — så den här acceptansen körs på en maskin utan GPU och utan tunnel.
# Att den kan det är en egenskap hos funktionen, inte hos skriptet.
#
# Evidensen hamnar i docs/evidence under körningens etikett, precis som
# desktop-acceptansens: skärmbilder och ett maskinläsbart kvitto som går att
# committa. Redan committad evidens skrivs aldrig över utan att
# --overwrite-evidence begärs uttryckligen.
invoice-acceptance: desktop-build  ## Fakturaresan mot riktig Tauri/WebKitGTK (ingen modell krävs)
	backend/.venv/bin/python backend/scripts/invoice_acceptance.py \
	  --run-label $(RUN_LABEL) \
	  $(if $(INVOICE_EVIDENCE),--evidence-dir $(INVOICE_EVIDENCE),)

# Inkommande post-resan behöver lika lite en modell som fakturaresan, och av
# samma skäl: köns läsning är deterministisk — kategori, datum, belopp och
# leverantör kommer ur regler över texten med produktens egna läsare. Att den
# resan går igenom på en maskin utan GPU är alltså ett påstående om funktionen,
# inte om skriptet.
intake-acceptance: desktop-build  ## Inkommande post-resan mot riktig Tauri/WebKitGTK (ingen modell krävs)
	backend/.venv/bin/python backend/scripts/intake_acceptance.py \
	  --run-label $(RUN_LABEL) \
	  $(if $(INTAKE_EVIDENCE),--evidence-dir $(INTAKE_EVIDENCE),)

# Hela acceptansen på en maskin där tunneln till agenntserver är uppe: först de
# två modellfria resorna, som felar snabbt och billigt, sedan den fulla resan
# som kräver den självhostade modellen. Tre kvitton, tre skärmbildsserier, en
# etikett — `<etikett>-invoice-*`, `<etikett>-intake-*` och `<etikett>-desktop-*`
# kan aldrig skriva över varandra.
desktop-acceptance-full: invoice-acceptance intake-acceptance desktop-acceptance  ## Faktura- + post- + full journey-acceptans (kräver modelltunneln)
	@echo "Alla tre acceptanserna klara. Evidens: docs/evidence/$(RUN_LABEL)-{invoice,intake,desktop}-*"

invoice-rules-lock:  ## Spela in granskningsreglernas fingeravtryck för nuvarande ANALYSIS_ENGINE_VERSION
	cd backend && .venv/bin/python -m app.invoices.rules --write

desktop-acceptance-installed:  ## Samma acceptans mot det INSTALLERADE paketet (ange RPM=... för artefaktidentitet)
	backend/.venv/bin/python backend/scripts/desktop_acceptance.py \
	  --application /usr/bin/brfv2-desktop \
	  $(if $(RPM),--artifact $(RPM),) \
	  --run-label $(RUN_LABEL)-installed

desktop-verify-artifact:  ## Granska den byggda (och ev. installerade) RPM:en mot ops/forbidden_providers.json
	BRFV2_REQUIRE_ARTIFACT=1 $(if $(RPM),BRFV2_RPM=$(RPM),) backend/.venv/bin/pytest -q backend/tests/test_desktop_artifact.py

desktop-verify-reproducible:  ## Bygg RPM:en från två rena checkouter och jämför byte för byte
	@ops/verify-reproducible.sh \
	  $${REPRO_A:-/home/$$USER/brfv2-repro/a} \
	  $${REPRO_B:-/home/$$USER/brfv2-repro/b-longer-checkout-path}

test:               ## Backend-tester (offline, deterministiska)
	cd backend && uv run pytest -q

test-isolation:     ## Bara isolering + livscykel + auth
	cd backend && uv run pytest -q tests/test_isolation.py tests/test_lifecycle.py tests/test_auth.py

eval:               ## Full eval, tenant A, standardleverantör (dev/eval-default)
	cd backend && uv run python -m scripts.eval --workers 2

eval-b:             ## Full eval, tenant B (Sjöutsikten 7), standardleverantör
	cd backend && uv run python -m scripts.eval --golden eval/golden_b.json --workers 2

eval-selfhosted: require-pilot-llm    ## Egress-bevis: eval tenant A via Gemma 4 12B på agenntserver
	cd backend && $(SELFHOSTED_ENV) uv run python -m scripts.eval --workers 2 --network-audit

eval-b-selfhosted: require-pilot-llm  ## Egress-bevis: eval tenant B via Gemma 4 12B på agenntserver
	cd backend && $(SELFHOSTED_ENV) uv run python -m scripts.eval --golden eval/golden_b.json --workers 2 --network-audit

eval-fast:          ## Retrieval-eval utan LLM
	cd backend && uv run python -m scripts.eval --retrieval-only

eval-sweep:         ## Bevis: inställningsrattarna ändrar siffrorna
	cd backend && uv run python -m scripts.eval --sweep

demo:                ## Starta HELA demon: verifierar SSH-tunneln + Gemma 4 12B, startar backend (pilot, :8787) + kanoniska frontend (:5173)
	@ops/demo.sh start

demo-stop:           ## Stoppa bara de processer som `make demo` startade (PID-spårat, dödar inget annat)
	@ops/demo.sh stop

demo-status:         ## Visa om demo-backend/frontend körs
	@ops/demo.sh status

demo-reset:          ## DESTRUKTIVT: nollställ och seeda om de två demoföreningarna + golden set + konton
	cd backend && uv run python -m scripts.seed --reset

model-readiness:               ## Modell-redo-kontroll mot verkliga dokument, standardleverantör (ambient env)
	cd backend && uv run python -m scripts.model_readiness --network-audit

model-readiness-selftest:          ## Bevis: self-test med KORREKT scriptad FakeLLM -> READY, exit 0
	cd backend && uv run python -m scripts.model_readiness --selftest

model-readiness-selftest-negative: ## Bevis: self-test med FABRICERAD scriptad FakeLLM -> NOT READY, exit 1
	cd backend && uv run python -m scripts.model_readiness --selftest-negative

build:              ## Produktionsbygge av kanoniska brfv2-mockup
	@test -d brfv2-mockup/node_modules || (echo "brfv2-mockup/node_modules saknas — kör 'make setup' först."; exit 1)
	cd brfv2-mockup && npm run build

build-legacy:       ## Bygg den äldre rotfrontenden
	npm run build
