.PHONY: backend frontend test eval eval-fast eval-sweep demo-reset build

backend:            ## API-server på :8787
	cd backend && uv run uvicorn app.main:create_app --factory --port 8787

frontend:           ## Vite dev-server på :5173
	npm run dev

test:               ## Backend-tester (offline, deterministiska)
	cd backend && uv run pytest -q

eval:               ## Full eval med riktig LLM (gates; exit 1 vid miss)
	cd backend && uv run python -m scripts.eval --workers 5

eval-fast:          ## Retrieval-eval utan LLM
	cd backend && uv run python -m scripts.eval --retrieval-only

eval-sweep:         ## Bevis: inställningsrattarna ändrar siffrorna
	cd backend && uv run python -m scripts.eval --sweep

demo-reset:         ## Nollställ och seeda om demokorpusen + golden set
	cd backend && uv run python -m scripts.seed --reset

build:              ## Produktionsbygge av frontend
	npm run build
