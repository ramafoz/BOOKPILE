import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "docs" / "OWNER_VIEWER_AUTHORIZATION_MATRIX.json"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
EVIDENCE_PATTERN = re.compile(
    r"^(server/tests/[a-z0-9_]+\.py)::([a-z0-9_]+)$"
)


def _matrix() -> dict[str, object]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_authorization_matrix_is_complete_and_traceable() -> None:
    matrix = _matrix()
    assert matrix["schema_version"] == 1
    assert matrix["status"] == "accepted"
    assert SHA_PATTERN.fullmatch(str(matrix["accepted_against_revision"]))
    assert matrix["unresolved_authorization_defects"] == []

    rows = matrix["rows"]
    assert isinstance(rows, list)
    assert {row["audit"] for row in rows} == {f"A{number}" for number in range(1, 10)}

    required = {
        "audit",
        "endpoint",
        "actor",
        "expected",
        "actual",
        "revision",
        "evidence",
    }
    for row in rows:
        assert set(row) == required
        assert all(isinstance(value, str) and value.strip() for value in row.values())
        assert SHA_PATTERN.fullmatch(row["revision"])
        match = EVIDENCE_PATTERN.fullmatch(row["evidence"])
        assert match is not None, row["evidence"]
        source = ROOT / match.group(1)
        assert source.is_file(), source
        assert f"def {match.group(2)}(" in source.read_text(encoding="utf-8")


def test_every_authorization_finding_has_a_live_regression() -> None:
    matrix = _matrix()
    findings = matrix["findings"]
    assert {finding["id"] for finding in findings} == {
        "AUTH-001",
        "AUDIT-001",
        "AUDIT-002",
    }
    for finding in findings:
        assert finding["kind"] in {"implementation_defect", "test_defect"}
        assert finding["disposition"] == "fixed"
        assert SHA_PATTERN.fullmatch(finding["revision"])
        match = EVIDENCE_PATTERN.fullmatch(finding["regression"])
        assert match is not None
        source = ROOT / match.group(1)
        assert source.is_file()
        assert f"def {match.group(2)}(" in source.read_text(encoding="utf-8")
