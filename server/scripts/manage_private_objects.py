"""Compatibility wrapper for the installed operational command."""

from bookpile_server.cli.private_objects import main


if __name__ == "__main__":
    raise SystemExit(main())
