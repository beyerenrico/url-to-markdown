import textwrap
from pathlib import Path

import pytest

import url_to_markdown as utm


def test_extract_domain_name_basic():
    assert utm.extract_domain_name("https://www.example.com") == "example"
    assert utm.extract_domain_name("http://example.org") == "example"
    assert utm.extract_domain_name("https://docs.example.io") == "example"


def test_extract_domain_name_complex():
    # Note: 'uk' is not filtered as a TLD in implementation, so it remains
    assert utm.extract_domain_name("https://api.sub.example.co.uk") == "sub_example_uk"


def test_clean_markdown_collapses_blank_lines_and_trailing_spaces():
    extractor = utm.WebsiteContentExtractor()
    raw = """
    Line 1   \n


    Line 2\t  \n
    <!-- comment -->

    Line 3
    """
    cleaned = extractor._clean_markdown(textwrap.dedent(raw))
    # No HTML comments, no >2 consecutive blank lines, trimmed trailing spaces
    assert "<!--" not in cleaned
    assert "Line 1" in cleaned
    assert "Line 2" in cleaned
    assert "Line 3" in cleaned
    # Ensure at most single blank line between content blocks
    assert "\n\n\n" not in cleaned


def test_parse_sitemap(tmp_path: Path):
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/</loc></url>
      <url><loc>https://example.com/about</loc></url>
    </urlset>
    """
    p = tmp_path / "sitemap.xml"
    p.write_text(sitemap_xml, encoding="utf-8")

    extractor = utm.WebsiteContentExtractor()
    urls = extractor.parse_sitemap(str(p))

    assert urls == [
        "https://example.com/",
        "https://example.com/about",
    ]


def test_parse_sitemap_deduplicates_trailing_slash(tmp_path: Path):
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com</loc></url>
      <url><loc>https://example.com/</loc></url>
      <url><loc>https://example.com/docs</loc></url>
      <url><loc>https://example.com/docs/</loc></url>
      <url><loc>https://example.com/blog/</loc></url>
      <url><loc>https://example.com/blog</loc></url>
    </urlset>
    """
    p = tmp_path / "sitemap.xml"
    p.write_text(sitemap_xml, encoding="utf-8")

    extractor = utm.WebsiteContentExtractor()
    urls = extractor.parse_sitemap(str(p))

    # Expect normalized canonical forms with duplicates removed:
    # - root becomes "/" form
    # - non-root paths drop trailing slash
    assert urls == [
        "https://example.com/",
        "https://example.com/docs",
        "https://example.com/blog",
    ]
