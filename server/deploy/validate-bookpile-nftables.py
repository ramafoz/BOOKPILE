#!/usr/bin/env python3
"""Validate the exact privacy-safe BOOKPILE nftables policy shape."""

from __future__ import annotations

import json
import sys
from typing import Any


EXPECTED_SETS = {
    "health_live_ipv4",
    "health_ready_ipv4",
}
EXPECTED_COMMENTS = {
    "bookpile health live": "health_live_ipv4",
    "bookpile health ready": "health_ready_ipv4",
}


class PolicyValidationError(RuntimeError):
    pass


def _reject_extra_keys(
    value: dict[str, Any], allowed: set[str], description: str
) -> None:
    if set(value) - allowed:
        raise PolicyValidationError(f"Unexpected {description} attributes")


def _validate_rule_expression(expression: object, set_name: str) -> None:
    if not isinstance(expression, list) or len(expression) != 4:
        raise PolicyValidationError("Unsafe rule expression count")

    expected_l4 = {
        "match": {
            "op": "==",
            "left": {"meta": {"key": "l4proto"}},
            "right": "tcp",
        }
    }
    if expression[0] != expected_l4:
        raise PolicyValidationError("Unsafe transport match")

    port_match = expression[1]
    if not isinstance(port_match, dict) or set(port_match) != {"match"}:
        raise PolicyValidationError("Unsafe public-port match")
    port_value = port_match["match"]
    if not isinstance(port_value, dict):
        raise PolicyValidationError("Unsafe public-port match")
    ports = port_value.get("right")
    if (
        port_value.get("op") != "=="
        or port_value.get("left")
        != {"ct": {"key": "proto-dst", "dir": "original"}}
        or not isinstance(ports, dict)
        or set(ports) != {"set"}
        or not isinstance(ports["set"], list)
        or set(ports["set"]) != {80, 443}
        or len(ports["set"]) != 2
    ):
        raise PolicyValidationError("Unsafe public-port match")

    address_match = expression[2]
    if not isinstance(address_match, dict) or set(address_match) != {"match"}:
        raise PolicyValidationError("Unsafe address-set match")
    address_value = address_match["match"]
    if not isinstance(address_value, dict):
        raise PolicyValidationError("Unsafe address-set match")
    reference = address_value.get("right")
    if reference not in (set_name, f"@{set_name}") and reference != {
        "set": set_name
    }:
        raise PolicyValidationError("Unsafe address-set reference")
    if (
        address_value.get("op") != "=="
        or address_value.get("left")
        != {"payload": {"protocol": "ip", "field": "saddr"}}
        or set(address_value) != {"op", "left", "right"}
    ):
        raise PolicyValidationError("Unsafe address-set match")

    if expression[3] != {"drop": None}:
        raise PolicyValidationError("Unsafe rule verdict")


def validate(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or not isinstance(payload.get("nftables"), list):
        raise PolicyValidationError("Invalid nftables JSON document")

    objects: dict[str, list[dict[str, Any]]] = {
        "table": [],
        "set": [],
        "chain": [],
        "rule": [],
        "element": [],
    }
    for entry in payload["nftables"]:
        if not isinstance(entry, dict):
            raise PolicyValidationError("Invalid nftables object")
        if "metainfo" in entry:
            continue
        kinds = [kind for kind in objects if kind in entry]
        if len(kinds) != 1 or len(entry) != 1:
            raise PolicyValidationError("Unexpected nftables object")
        value = entry[kinds[0]]
        if not isinstance(value, dict):
            raise PolicyValidationError("Invalid nftables object value")
        objects[kinds[0]].append(value)

    tables = objects["table"]
    if (
        len(tables) != 1
        or tables[0].get("family") != "inet"
        or tables[0].get("name") != "bookpile"
    ):
        raise PolicyValidationError("Unexpected table")
    _reject_extra_keys(tables[0], {"family", "name", "handle"}, "table")

    sets = objects["set"]
    if {item.get("name") for item in sets} != EXPECTED_SETS or len(sets) != 2:
        raise PolicyValidationError("Unexpected address sets")
    for item in sets:
        _reject_extra_keys(
            item,
            {"family", "table", "name", "type", "flags", "timeout", "elem", "handle"},
            "set",
        )
        if (
            item.get("family") != "inet"
            or item.get("table") != "bookpile"
            or item.get("type") != "ipv4_addr"
            or set(item.get("flags", [])) != {"timeout"}
            or item.get("timeout") != 600
        ):
            raise PolicyValidationError("Unsafe address-set definition")

    chains = objects["chain"]
    if len(chains) != 1:
        raise PolicyValidationError("Unexpected chains")
    chain = chains[0]
    _reject_extra_keys(
        chain,
        {"family", "table", "name", "type", "hook", "prio", "policy", "handle"},
        "chain",
    )
    if (
        chain.get("family") != "inet"
        or chain.get("table") != "bookpile"
        or chain.get("name") != "public_web_guard"
        or chain.get("type") != "filter"
        or chain.get("hook") != "forward"
        or chain.get("prio") != -10
        or chain.get("policy") != "accept"
    ):
        raise PolicyValidationError("Unsafe base chain")

    rules = objects["rule"]
    if len(rules) != 2:
        raise PolicyValidationError("Unexpected rule count")
    seen_comments: set[str] = set()
    for rule in rules:
        _reject_extra_keys(
            rule,
            {"family", "table", "chain", "expr", "comment", "handle"},
            "rule",
        )
        if (
            rule.get("family") != "inet"
            or rule.get("table") != "bookpile"
            or rule.get("chain") != "public_web_guard"
            or rule.get("comment") not in EXPECTED_COMMENTS
        ):
            raise PolicyValidationError("Unexpected rule location")
        comment = str(rule["comment"])
        set_name = EXPECTED_COMMENTS[comment]
        _validate_rule_expression(rule.get("expr"), set_name)
        seen_comments.add(comment)
    if seen_comments != set(EXPECTED_COMMENTS):
        raise PolicyValidationError("Missing policy rule")

    for element in objects["element"]:
        if (
            element.get("family") != "inet"
            or element.get("table") != "bookpile"
            or element.get("name") not in EXPECTED_SETS
        ):
            raise PolicyValidationError("Unexpected set element")

    return {
        "chain": "public_web_guard",
        "family": "inet",
        "policy_sets": sorted(EXPECTED_SETS),
        "rules": 2,
        "ssh_port_matched": False,
    }


def main() -> int:
    try:
        result = validate(json.load(sys.stdin))
    except (
        json.JSONDecodeError,
        OSError,
        PolicyValidationError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"BOOKPILE nftables validation failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
