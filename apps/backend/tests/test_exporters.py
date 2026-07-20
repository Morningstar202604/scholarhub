"""Pure-function tests for exporters — no DB needed, uses SimpleNamespace stubs.

Verifies all four serializers without touching SQLAlchemy or the FastAPI app.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.modules.export.exporters import (
    export_resources,
    to_bibtex,
    to_csv,
    to_json,
    to_ris,
)


def _stub(**overrides: object) -> SimpleNamespace:
    """Build a minimal Exportable stub with sensible defaults."""
    base = SimpleNamespace(
        id="test-1",
        type="paper",
        title="A Test Paper",
        authors=["Alice Author", "Bob Reviewer"],
        year=2024,
        venue="Journal of Testing",
        discipline="computer-science",
        tags=["ml", "python"],
        abstract="This is a test abstract.",
        preview="Test preview.",
        download_url="https://example.com/download.pdf",
        external_url="https://example.com/paper",
        doi="10.1234/test.1",
        volume="10",
        issue="2",
        pages="1-20",
        keywords=["testing", "fixtures"],
    )
    return SimpleNamespace(**{**base.__dict__, **overrides})


def test_bibtex_renders_article_entry() -> None:
    out = to_bibtex([_stub()])
    assert out.startswith("@article{")
    # Citation key: surname + year + first title word
    assert "author2024a" in out
    assert "  author = {Alice Author and Bob Reviewer}" in out
    assert "  year = {2024}" in out
    assert "  journal = {Journal of Testing}" in out
    assert "  volume = {10}" in out
    assert "  number = {2}" in out
    assert "  pages = {1-20}" in out
    assert "  doi = {10.1234/test.1}" in out


def test_bibtex_book_uses_booktitle() -> None:
    out = to_bibtex([_stub(type="book")])
    assert "@book{" in out
    assert "  booktitle = {Journal of Testing}" in out


def test_bibtex_disambiguates_duplicate_keys() -> None:
    """Two resources with same author+year+title get a _N suffix."""
    res = _stub()
    out = to_bibtex([res, res])
    assert out.count("@article{") == 2
    # Second entry gets _2 suffix on key
    assert "_2" in out


def test_bibtex_folds_abstract_whitespace() -> None:
    out = to_bibtex([_stub(abstract="line one\n\nline two\ttabbed")])
    assert "  abstract = {line one line two tabbed}" in out


def test_ris_renders_jour_entry() -> None:
    out = to_ris([_stub()])
    assert out.startswith("TY  - JOUR\n")
    assert "TI  - A Test Paper" in out
    assert "AU  - Alice Author" in out
    assert "AU  - Bob Reviewer" in out
    assert "PY  - 2024" in out
    assert "JO  - Journal of Testing" in out
    assert "VL  - 10" in out
    assert "IS  - 2" in out
    assert "SP  - 1-20" in out
    assert "KW  - testing" in out
    assert "DO  - 10.1234/test.1" in out
    assert out.rstrip().endswith("ER  -")


def test_ris_uses_data_type_for_dataset() -> None:
    out = to_ris([_stub(type="dataset")])
    assert out.startswith("TY  - DATA\n")


def test_csv_has_canonical_headers() -> None:
    out = to_csv([_stub()])
    lines = out.strip().split("\n")
    assert lines[0] == "title,type,authors,year,venue,discipline,tags,abstract,doi,url"
    # Author field is " and "-joined
    assert "Alice Author and Bob Reviewer" in lines[1]
    # Keywords fall back to tags when keywords missing — but here we set
    # keywords explicitly so they appear as "; "-joined
    assert "testing; fixtures" in lines[1]


def test_csv_keywords_fall_back_to_tags() -> None:
    out = to_csv([_stub(keywords=None)])
    line2 = out.strip().split("\n")[1]
    assert "ml; python" in line2


def test_json_renders_normalized_records() -> None:
    import json

    out = to_json([_stub()])
    records = json.loads(out)
    assert len(records) == 1
    r = records[0]
    assert r["title"] == "A Test Paper"
    assert r["authors"] == ["Alice Author", "Bob Reviewer"]
    assert r["year"] == 2024
    assert r["venue"] == "Journal of Testing"
    assert r["doi"] == "10.1234/test.1"
    assert r["source_id"] == "test-1"
    assert r["keywords"] == ["testing", "fixtures"]
    assert r["volume"] == "10"


def test_dispatch_routes_by_format_name() -> None:
    res = _stub()
    assert "@article{" in export_resources("bibtex", [res])
    assert "TY  - JOUR" in export_resources("ris", [res])
    assert "title,type,authors" in export_resources("csv", [res])
    assert '"title": "A Test Paper"' in export_resources("json", [res])


def test_dispatch_is_case_insensitive() -> None:
    res = _stub()
    assert "TY  - JOUR" in export_resources("RIS", [res])


def test_dispatch_rejects_unknown_format() -> None:
    import pytest

    with pytest.raises(ValueError, match="Unsupported export format"):
        export_resources("yaml", [_stub()])
