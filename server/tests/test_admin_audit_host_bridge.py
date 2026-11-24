import json
from importlib.machinery import SourceFileLoader
from pathlib import Path
import types


SCRIPT = Path(__file__).parents[1] / "deploy" / "bookpile-admin-audit"


def _module():
    module = types.ModuleType("admin_audit_bridge")
    SourceFileLoader(module.__name__, str(SCRIPT)).exec_module(module)
    return module


def test_bridge_has_a_fixed_socket_and_narrow_commands() -> None:
    module = _module()
    assert module.SOCKET_PATH.as_posix() == "/run/bookpile-admin-audit/audit.sock"
    assert module.COMMANDS == {"append-host-evidence-access"}
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("--database", "--socket", "--output", "subprocess", "shell=True"):
        assert forbidden not in source


def test_bridge_source_never_prints_the_submitted_payload() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "print(content" not in source
    assert "print(payload" not in source
    assert json.dumps({"client_ip": "192.0.2.10"}) not in source
