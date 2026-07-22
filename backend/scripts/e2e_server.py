"""Run an isolated, synthetic backend for browser acceptance tests.

The server owns a temporary data root for its entire lifetime and removes it
on shutdown. It never reads, resets, or writes the normal backend/data tree.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import uvicorn

from app.auth import AuthStore
from app.main import create_app
from app.registry import TenantRegistry
from scripts.seed import seed_demo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="brfv2-e2e-") as temp_dir:
        root = Path(temp_dir)
        auth = AuthStore(root / "auth.db")
        registry = TenantRegistry(root, auth)
        seed_demo(registry, auth)
        app = create_app(registry=registry, auth=auth, data_root=root)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
