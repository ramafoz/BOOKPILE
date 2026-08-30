"""Create or revoke temporary beta account invitations.

The raw invitation token is printed once and is never stored by BOOKPILE.
"""
import argparse
from uuid import UUID

from bookpile_server.config import get_settings
from bookpile_server.database import SessionFactory
from bookpile_server.repositories.account_invitations import (
    AccountInvitationRepository,
)
from bookpile_server.services.account_invitations import (
    AccountInvitationError,
    AccountInvitationService,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("create", help="Create a single-use 7-day invitation")
    revoke = subcommands.add_parser("revoke", help="Revoke an unused invitation")
    revoke.add_argument("invitation_id", type=UUID)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with SessionFactory() as session:
        service = AccountInvitationService(AccountInvitationRepository(session))
        if args.command == "create":
            result = service.create()
            base_url = get_settings().public_base_url.rstrip("/")
            print(f"Invitation ID: {result.invitation_id}")
            print(f"Expires at: {result.expires_at.isoformat()}")
            print(f"Registration URL: {base_url}/register?invite={result.raw_token}")
            print("This URL will not be shown again.")
            return 0
        try:
            service.revoke(args.invitation_id)
        except AccountInvitationError as exc:
            print(str(exc))
            return 1
        print(f"Revoked invitation: {args.invitation_id}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
