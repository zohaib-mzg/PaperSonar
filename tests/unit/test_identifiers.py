"""Unit tests for DOI/title normalization and hashing."""

from papersonar.identifiers import (
    canonical_json_hash,
    normalize_doi,
    normalize_title,
    sha256_hex,
)


class TestNormalizeDoi:
    def test_plain_doi_unchanged(self):
        assert normalize_doi("10.1234/abcdef") == "10.1234/abcdef"

    def test_casefold(self):
        assert normalize_doi("10.1234/ABC.def") == "10.1234/abc.def"

    def test_doi_url_prefix(self):
        assert normalize_doi("https://doi.org/10.1234/x-y") == "10.1234/x-y"

    def test_dx_doi_http(self):
        assert normalize_doi("http://dx.doi.org/10.5555/old") == "10.5555/old"

    def test_doi_colon_prefix(self):
        assert normalize_doi("doi:10.1234/z") == "10.1234/z"

    def test_nested_prefixes(self):
        assert normalize_doi("doi:https://doi.org/10.1234/nested") == "10.1234/nested"

    def test_trailing_punctuation(self):
        assert normalize_doi("10.1234/trailing.") == "10.1234/trailing"
        assert normalize_doi("10.1234/trailing, ") == "10.1234/trailing"
        assert normalize_doi("10.1234/paren)") == "10.1234/paren"

    def test_internal_whitespace_removed(self):
        assert normalize_doi("10.1234/  spaced out ") == "10.1234/spacedout"

    def test_none_and_blank(self):
        assert normalize_doi(None) is None
        assert normalize_doi("") is None
        assert normalize_doi("   ") is None

    def test_malformed_rejected(self):
        assert normalize_doi("not-a-doi") is None
        assert normalize_doi("11.1234/weird") is None
        assert normalize_doi("https://doi.org/") is None


class TestNormalizeTitle:
    def test_collapse_whitespace_casefold(self):
        assert normalize_title("  A  Study of\tThings ") == "a study of things"

    def test_unicode_nfkc(self):
        assert normalize_title("café") == normalize_title("café")

    def test_none_blank(self):
        assert normalize_title(None) is None
        assert normalize_title("   ") is None


class TestHashing:
    def test_sha256_known_vector(self):
        # sha256("abc") well-known digest
        assert sha256_hex(b"abc") == (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )

    def test_canonical_json_hash_is_order_independent(self):
        assert canonical_json_hash({"a": 1, "b": [1, 2]}) == canonical_json_hash(
            {"b": [1, 2], "a": 1}
        )

    def test_canonical_json_hash_changes_on_content_change(self):
        assert canonical_json_hash({"a": 1}) != canonical_json_hash({"a": 2})
