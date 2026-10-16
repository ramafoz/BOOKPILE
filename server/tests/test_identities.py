from bookpile_server.security.identities import normalize_account_identifier


def test_account_identifier_normalization_is_shared_and_type_agnostic() -> None:
    assert normalize_account_identifier("  Reader_Name  ") == "reader_name"
    assert normalize_account_identifier("  READER@EXAMPLE.COM ") == "reader@example.com"
