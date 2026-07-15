import os

import pytest

# Tests must be offline + deterministic: no model downloads, no real LLM.
os.environ.setdefault("BRF_EMBEDDER", "hashed")
os.environ.setdefault("BRF_LLM", "fake")


def pytest_collection_modifyitems(config, items):
    run_llm = os.environ.get("RUN_LLM_TESTS") == "1"
    skip_llm = pytest.mark.skip(reason="set RUN_LLM_TESTS=1 to run real-LLM tests")
    for item in items:
        if "llm" in item.keywords and not run_llm:
            item.add_marker(skip_llm)
