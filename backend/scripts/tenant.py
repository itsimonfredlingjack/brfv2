"""Tenant/user ops CLI — how BRFs and board members are provisioned.
There is deliberately no public signup at pilot scale.

Usage:
    uv run python -m scripts.tenant create-tenant --name "Brf Exempel 1" [--brf-id exempel-1]
    uv run python -m scripts.tenant add-user --email x@y.se --password '...' [--name "..."]
    uv run python -m scripts.tenant add-membership --email x@y.se --brf-id exempel-1 --role admin
    uv run python -m scripts.tenant delete-tenant --brf-id exempel-1 --yes
    uv run python -m scripts.tenant list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import AuthError, AuthStore  # noqa: E402
from app.registry import TenantRegistry  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create-tenant")
    p.add_argument("--name", required=True)
    p.add_argument("--brf-id", default=None)

    p = sub.add_parser("add-user")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--name", default="")

    p = sub.add_parser("add-membership")
    p.add_argument("--email", required=True)
    p.add_argument("--brf-id", required=True)
    p.add_argument("--role", choices=["member", "admin"], required=True)

    p = sub.add_parser("delete-tenant")
    p.add_argument("--brf-id", required=True)
    p.add_argument("--yes", action="store_true", help="required: hard delete is irreversible")

    sub.add_parser("list")

    args = parser.parse_args()
    root = Path(args.data_root) if args.data_root else Path(__file__).resolve().parent.parent / "data"
    auth = AuthStore(root / "auth.db")
    registry = TenantRegistry(root, auth)

    try:
        if args.cmd == "create-tenant":
            brf_id = registry.create(args.name, args.brf_id)
            print(f"Skapade förening '{args.name}' → brf_id={brf_id}")
        elif args.cmd == "add-user":
            uid = auth.create_user(args.email, args.password, args.name)
            print(f"Skapade användare {args.email} → id={uid}")
        elif args.cmd == "add-membership":
            with auth._conn() as conn:  # CLI-only convenience lookup
                row = conn.execute("SELECT id FROM users WHERE email = ?", (args.email.strip().lower(),)).fetchone()
            if row is None:
                sys.exit(f"Ingen användare med e-post {args.email}")
            if auth.get_tenant(args.brf_id) is None:
                sys.exit(f"Ingen förening med brf_id {args.brf_id}")
            auth.add_membership(row["id"], args.brf_id, args.role)
            print(f"{args.email} är nu {args.role} i {args.brf_id}")
        elif args.cmd == "delete-tenant":
            if not args.yes:
                sys.exit("Hård radering är oåterkallelig — bekräfta med --yes")
            if registry.delete(args.brf_id):
                print(f"Föreningen {args.brf_id} och all dess data är raderad.")
            else:
                sys.exit(f"Ingen förening med brf_id {args.brf_id}")
        elif args.cmd == "list":
            for t in registry.list():
                store = registry.get(t["brf_id"])
                docs = len(store.documents) if store else 0
                print(f"{t['brf_id']:24s} {t['name']:32s} {docs} dokument")
    except AuthError as exc:
        sys.exit(f"Fel: {exc}")


if __name__ == "__main__":
    main()
