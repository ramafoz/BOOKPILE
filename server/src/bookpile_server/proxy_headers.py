from collections.abc import Awaitable, Callable, Sequence
from ipaddress import IPv4Network, IPv6Network, ip_address
from typing import Any


ASGIApp = Callable[..., Awaitable[None]]
IPNetwork = IPv4Network | IPv6Network


class TrustedProxyHeadersMiddleware:
    """Accept sanitized forwarding data only from an explicitly trusted peer."""

    def __init__(self, app: ASGIApp, trusted_networks: Sequence[IPNetwork]) -> None:
        self.app = app
        self.trusted_networks = tuple(trusted_networks)

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http" and self._is_trusted_peer(scope.get("client")):
            scope = self._forwarded_scope(scope)
        await self.app(scope, receive, send)

    def _forwarded_scope(self, scope: dict[str, Any]) -> dict[str, Any]:
        client_values = self._header_values(scope, b"x-forwarded-for")
        proto_values = self._header_values(scope, b"x-forwarded-proto")
        updated = dict(scope)
        if len(client_values) == 1:
            try:
                raw_address = client_values[0].decode("ascii").strip()
                if "," not in raw_address:
                    updated["client"] = (str(ip_address(raw_address)), 0)
            except (UnicodeDecodeError, ValueError):
                pass
        if len(proto_values) == 1:
            try:
                proto = proto_values[0].decode("ascii").strip().lower()
                if proto in {"http", "https"}:
                    updated["scheme"] = proto
            except UnicodeDecodeError:
                pass
        return updated

    @staticmethod
    def _header_values(scope: dict[str, Any], target: bytes) -> list[bytes]:
        return [
            value
            for name, value in scope.get("headers", ())
            if name.lower() == target
        ]

    def _is_trusted_peer(self, client: object) -> bool:
        if not isinstance(client, (tuple, list)) or not client:
            return False
        try:
            peer = ip_address(str(client[0]))
        except ValueError:
            return False
        return any(peer in network for network in self.trusted_networks)
