.PHONY: backend backend-pilot frontend test test-isolation eval eval-b eval-fast eval-sweep \
        eval-selfhosted demo-reset build

# Self-hosted LLM endpoint (EU GPU host in production; local Ollama for the demo).
BRF_LLM_BASE_URL ?= http://127.0.0.1:11434/v1
BRF_LLM_MODEL ?= gemma4:e4b
SELFHOSTED_ENV = BRF_LLM=selfhosted BRF_LLM_BASE_URL=$(BRF_LLM_BASE_URL) BRF_LLM_MODEL=$(BRF_LLM_MODEL)

backend:            ## API-server på :8787 (dev-läge)
	cd backend && uv run uvicorn app.main:create_app --factory --port 8787

backend-pilot:      ## API-server i pilot-läge (kräver självhostad LLM)
	cd backend && BRF_MODE=pilot $(SELFHOSTED_ENV) uv run uvicorn app.main:create_app --factory --port 8787

frontend:           ## Vite dev-server på :5173
	npm run dev

test:               ## Backend-tester (offline, deterministiska)
	cd backend && uv run pytest -q

test-isolation:     ## Bara isolering + livscykel + auth
	cd backend && uv run pytest -q tests/test_isolation.py tests/test_lifecycle.py tests/test_auth.py

eval:               ## Full eval, tenant A, självhostad LLM + nätverksrevision
	cd backend && $(SELFHOSTED_ENV) uv run python -m scripts.eval --workers 2 --network-audit

eval-b:             ## Full eval, tenant B (Sjöutsikten 7)
	cd backend && $(SELFHOSTED_ENV) uv run python -m scripts.eval --golden eval/golden_b.json --workers 2 --network-audit

eval-fast:          ## Retrieval-eval utan LLM
	cd backend && uv run python -m scripts.eval --retrieval-only

eval-sweep:         ## Bevis: inställningsrattarna ändrar siffrorna
	cd backend && uv run python -m scripts.eval --sweep

demo-reset:         ## Nollställ och seeda om de två demoföreningarna + golden set
	cd backend && uv run python -m scripts.seed --reset

build:              ## Produktionsbygge av frontend
	npm run build
