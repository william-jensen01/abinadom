"""Key management CLI for the LDS MCP server auth module.

Usage:
    pipenv run py scripts/manage_keys.py create --name alice
    pipenv run py scripts/manage_keys.py revoke --name alice
    pipenv run py scripts/manage_keys.py list
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.store import SqliteKeyStore

AUTH_DB_PATH = os.environ.get(
    "AUTH_DB_PATH",
    str(Path(__file__).parent.parent / "auth.db"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage API keys for the MCP server")
    sub = parser.add_subparsers(dest="command", required=True)

    create_p = sub.add_parser("create", help="Issue a new API key")
    create_p.add_argument("--name", required=True, help="Name for the key (e.g. 'alice')")

    revoke_p = sub.add_parser("revoke", help="Revoke a key by name")
    revoke_p.add_argument("--name", required=True, help="Name of the key to revoke")

    sub.add_parser("list", help="List all key names and creation dates")

    args = parser.parse_args()
    store = SqliteKeyStore(AUTH_DB_PATH)

    if args.command == "create":
        try:
            token = store.create_key(args.name)
        except sqlite3.IntegrityError:
            print(f"Error: A key named '{args.name}' already exists.", file=sys.stderr)
            sys.exit(1)
        print(f"Key '{args.name}' created.")
        print(f"Token (save this — it will not be shown again):\n{token}")

    elif args.command == "revoke":
        removed = store.revoke_key(args.name)
        if removed:
            print(f"Key '{args.name}' revoked.")
        else:
            print(f"No key named '{args.name}' found.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list":
        keys = store.list_keys()
        if not keys:
            print("No keys found.")
        else:
            print(f"{'Name':<30} {'Created'}")
            print("-" * 60)
            for k in keys:
                print(f"{k['name']:<30} {k['created_at']}")


if __name__ == "__main__":
    main()
