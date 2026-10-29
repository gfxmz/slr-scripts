"""Offline tests - they do not need an internet connection.

Run with:  pytest
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doi_downloader import PdfLinkParser, normalize_doi, read_dois, safe_filename  # noqa: E402


# ---------------------------------------------------------------- normalize_doi

def test_plain_doi():
    assert normalize_doi("10.1038/nature14539") == "10.1038/nature14539"


def test_doi_url():
    assert normalize_doi("https://doi.org/10.1038/nature14539") == "10.1038/nature14539"


def test_doi_prefix_and_trailing_dot():
    assert normalize_doi("doi:10.7717/peerj.4375.") == "10.7717/peerj.4375"


def test_not_a_doi():
    assert normalize_doi("not-a-doi") is None
    assert normalize_doi("") is None


# ---------------------------------------------------------------- read_dois

def test_detects_doi_column_and_semicolon(tmp_path):
    f = tmp_path / "list.csv"
    f.write_text("title;DOI\nA;10.1/aaa\nB;10.1234/bbb\n", encoding="utf-8")
    assert read_dois(f) == ["10.1234/bbb"]  # "10.1/aaa" is too short to be a DOI


def test_removes_duplicates_case_insensitive(tmp_path):
    f = tmp_path / "list.csv"
    f.write_text("doi\n10.1371/ABC\n10.1371/abc\n10.1371/xyz\n", encoding="utf-8")
    assert read_dois(f) == ["10.1371/ABC", "10.1371/xyz"]


def test_no_header_scans_all_cells(tmp_path):
    f = tmp_path / "list.csv"
    f.write_text("paper one,10.1371/aaa\npaper two,10.1371/bbb\n", encoding="utf-8")
    assert read_dois(f) == ["10.1371/aaa", "10.1371/bbb"]


def test_example_file():
    example = Path(__file__).resolve().parent.parent / "example_dois.csv"
    dois = read_dois(example)
    assert len(dois) == 5
    assert "10.1038/s41586-020-2649-2" in dois


# ---------------------------------------------------------------- safe_filename

def test_safe_filename():
    assert safe_filename("10.1371/journal.pcbi.1003285") == "10.1371_journal.pcbi.1003285.pdf"
    assert "/" not in safe_filename("10.1002/(SICI)1097-0258")


# ---------------------------------------------------------------- PdfLinkParser

def test_parser_finds_meta_and_links():
    html = """
    <html><head>
      <meta name="citation_pdf_url" content="https://example.org/paper.pdf">
    </head><body>
      <a href="/files/supplement.pdf?download=1">Supplement</a>
      <a href="/about">About</a>
    </body></html>
    """
    p = PdfLinkParser()
    p.feed(html)
    assert p.meta_pdf == ["https://example.org/paper.pdf"]
    assert p.links == ["/files/supplement.pdf?download=1"]
