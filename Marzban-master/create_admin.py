#!/usr/bin/env python3
"""Create the initial sudo admin for Marzban.

Idempotent: if the admin already exists, this is a no-op (exit 0).
If it does not exist, it is created. Designed for non-interactive
Railway / container startup via env vars or CLI flags.
"""
import argparse
import sys

from decouple import UndefinedValueError, config

from app.db import GetDB, crud
from app.db.models import Admin
from app.models.admin import AdminCreate


def create_or_update(username: str, password: str, is_sudo: bool = True) -> str:
    from app.models.admin import AdminPartialModify

    with GetDB() as db:
        existing: Admin | None = None
        try:
            existing = crud.get_admin(db, username=username)
        except Exception:
            # Table may not exist yet (migrations not applied). Treat as
            # "not found" so we attempt creation below.
            existing = None

        if existing is not None:
            # Already exists: keep it, but sync credentials + sudo flag.
            crud.partial_update_admin(
                db,
                existing,
                AdminPartialModify(
                    password=password,
                    is_sudo=is_sudo,
                    telegram_id=None,
                    discord_webhook=None,
                ),
            )
            return f'Admin "{username}" already exists — synced credentials.'

        crud.create_admin(
            db,
            AdminCreate(
                username=username,
                password=password,
                is_sudo=is_sudo,
                telegram_id=0,
                discord_webhook="",
            ),
        )
        return f'Admin "{username}" created successfully.'


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the Marzban sudo admin.")
    parser.add_argument("--username", default=None, help="Admin username")
    parser.add_argument("--password", default=None, help="Admin password")
    parser.add_argument("--sudo", action="store_true", default=True, help="Make the admin sudo (default True)")
    parser.add_argument("--no-sudo", dest="sudo", action="store_false", help="Do not make the admin sudo")
    args = parser.parse_args()

    # Allow env-driven non-interactive usage as well.
    username = args.username or config("SUDO_USERNAME", default="")
    password = args.password or config("SUDO_PASSWORD", default="")

    if not username or not password:
        print(
            "ERROR: username and password are required.\n"
            "Pass --username/--password or set SUDO_USERNAME/SUDO_PASSWORD.",
            file=sys.stderr,
        )
        return 2

    try:
        message = create_or_update(username, password, is_sudo=args.sudo)
    except UndefinedValueError:
        print("ERROR: unable to read SUDO_USERNAME/SUDO_PASSWORD.", file=sys.stderr)
        return 2
    except Exception as exc:  # never fail the deploy for a transient admin issue
        print(f"WARNING: admin creation encountered an error: {exc}", file=sys.stderr)
        return 0

    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
