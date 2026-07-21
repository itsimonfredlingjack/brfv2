.PHONY: backend backend-pilot require-pilot-llm frontend frontend-legacy test test-isolation eval eval-b eval-fast eval-sweep \
        eval-selfhosted eval-b-selfhosted demo demo-stop demo-status demo-reset build build-legacy model-readiness model-readiness-selftest \
        model-readiness-selftest-negative

# Generation default for dev + eval is the standard hosted provider (logged-in `claude`
# CLI, or Anthropic SDK when ANTHROPIC_API_KEY is set) — no env needed. Dev/eval use only
# synthetic BRF data, so no data-residency constraint applies there.
#
# Pilot/production generation is the Gemma 4 12B service on `agenntserver`
# (Ubuntu + RTX 4070). The Mac must never silently fall back to its local e4b model.
# Supply BRF_LLM_BASE_URL explicitly: normally http://127.0.0.1:8000/v1 when the
# backend runs on agenntserver or when port 8000 is SSH-forwarded from that server.
BRF_LLM_BASE_URL ?=
BRF_LLM_MODEL ?= gemma4:e12b
SELFHOSTED_ENV = BRF_LLM=selfhosted BRF_LLM_BASE_URL=$(BRF_LLM_BASE_URL) BRF_LLM_MODEL=$(BRF_LLM_MODEL)

backend:            ## API-server på :8787 (dev-läge)
	cd backend && uv run uvicorn app.main:create_app --factory --port 8787

require-pilot-llm:
	@test -n "$(BRF_LLM_BASE_URL)" || (echo "BRF_LLM_BASE_URL måste peka på agenntserver Gemma 4 12B (oftast http://127.0.0.1:8000/v1 via tunnel)."; exit 1)

backend-pilot: require-pilot-llm  ## API-server i pilotläge mot Gemma 4 12B på agenntserver
	cd backend && BRF_MODE=pilot $(SELFHOSTED_ENV) uv run uvicorn app.main:create_app --factory --port 8787

frontend:           ## Kanoniska UI:t i brfv2-mockup på :5173
	@test -d brfv2-mockup || (echo "Kanoniska frontend-repot brfv2-mockup saknas i arbetsytan."; exit 1)
	cd brfv2-mockup && npm run dev

frontend-legacy:    ## Äldre backendkopplad prototyp i rotens src/
	npm run dev

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
	@test -d brfv2-mockup || (echo "Kanoniska frontend-repot brfv2-mockup saknas i arbetsytan."; exit 1)
	cd brfv2-mockup && npm run build

build-legacy:       ## Bygg den äldre rotfrontenden
	npm run build
