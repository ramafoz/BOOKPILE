"""Compatibility wrapper for the installed account-invitation command."""

from bookpile_server.cli.account_invitations import main


if __name__ == "__main__":
    raise SystemExit(main())
