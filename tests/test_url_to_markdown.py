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


def test_crawler_extract_links_normalizes_and_dedupes():
    html = """
    <a href="https://example.com">root no slash</a>
    <a href="https://example.com/">root with slash</a>
    <a href="/docs">docs no slash</a>
    <a href="/docs/">docs with slash</a>
    <a href="/blog/">blog with slash</a>
    <a href="/blog#frag">blog with fragment</a>
    <a href="https://other.com/">external domain</a>
    """

    crawler = utm.WebCrawler("https://example.com")
    links = crawler._extract_links("https://example.com/", html)

    assert set(links) == {
        "https://example.com/",
        "https://example.com/docs",
        "https://example.com/blog",
    }


def test_save_to_separate_files_uses_pages_subdir(tmp_path: Path):
    extractor = utm.WebsiteContentExtractor()
    results = [
        {
            "url": "https://example.com/",
            "title": "Home",
            "content": "Home content",
            "error": None,
        },
        {
            "url": "https://example.com/docs",
            "title": "Docs",
            "content": "Docs content",
            "error": None,
        },
        {
            "url": "https://example.com/blog/",
            "title": "Blog",
            "content": "Blog content",
            "error": None,
        },
    ]

    extractor._save_to_separate_files(results, str(tmp_path))

    # Ensure files are created under the pages/ subdirectory
    assert (tmp_path / "pages" / "index.md").exists()
    assert (tmp_path / "pages" / "docs.md").exists()
    # With current logic, trailing slash non-root becomes a file named <segment>.md
    assert (tmp_path / "pages" / "blog.md").exists()


def test_parse_sitemap_empty_file_returns_empty_list(tmp_path: Path):
    # Create an empty sitemap file
    p = tmp_path / "empty.xml"
    p.write_text("", encoding="utf-8")

    extractor = utm.WebsiteContentExtractor()
    urls = extractor.parse_sitemap(str(p))

    assert urls == []


def test_crawler_api_rules_allow_docs_api_and_skip_root_api():
    crawler = utm.WebCrawler("https://shopify.dev")

    # Should allow docs API pages
    assert crawler._is_valid_url("https://shopify.dev/docs/api/admin-graphql") is True

    # Should skip API root paths
    assert crawler._is_valid_url("https://shopify.dev/api/") is False
    assert crawler._is_valid_url("https://shopify.dev/api") is False


def test_augment_crawl_merges_urls_and_updates_sitemap(tmp_path: Path, monkeypatch):
    # Minimal sitemap with a single page
    base_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://shopify.dev/docs/api/admin-graphql</loc></url>
    </urlset>
    """

    class FakeFinder:
        def __init__(self, base_url: str, timeout: int = 10):
            self.base_url = base_url
        def find_sitemap_url(self):
            return "https://shopify.dev/sitemap.xml"
        def download_sitemap(self, sitemap_url: str) -> str:
            p = tmp_path / "sitemap.xml"
            p.write_text(base_xml, encoding="utf-8")
            return str(p)

    class FakeCrawler:
        def __init__(self, base_url: str, max_depth: int = 3, max_pages: int = 500, timeout: int = 10):
            self.base_url = base_url
        def crawl(self):
            return [
                "https://shopify.dev/docs/api/admin-graphql",  # duplicate in sitemap
                "https://shopify.dev/docs/api/admin-graphql/reference",  # new URL
            ]
        def generate_sitemap(self, urls):
            raise AssertionError("generate_sitemap should not be called in augment path")

    monkeypatch.setattr(utm, "SitemapFinder", FakeFinder)
    monkeypatch.setattr(utm, "WebCrawler", FakeCrawler)
    # Avoid network during extraction
    monkeypatch.setattr(utm.WebsiteContentExtractor, "extract_content", lambda self, url: {
        "url": url, "title": "t", "content": "c", "error": None
    })

    extractor = utm.WebsiteContentExtractor()
    successful, failed = extractor.process_website(
        "https://shopify.dev",
        separate_files=True,
        output_path=str(tmp_path),
        augment_crawl=True,
    )

    # Both original and newly discovered page should be saved under pages/
    assert (tmp_path / "pages" / "docs" / "api" / "admin-graphql.md").exists()
    assert (tmp_path / "pages" / "docs" / "api" / "admin-graphql" / "reference.md").exists()
    # Saved sitemap should include the reference URL
    saved_xml = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://shopify.dev/docs/api/admin-graphql/reference" in saved_xml


def test_sitemap_index_with_gzip_child_supported(tmp_path: Path):
    # Prepare a sitemap index XML that references a gzipped child sitemap
    index_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap>
        <loc>https://shopify.dev/sitemap_standard.xml.gz</loc>
      </sitemap>
    </sitemapindex>
    """

    child_sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://shopify.dev/docs/api/admin-graphql</loc></url>
      <url><loc>https://shopify.dev/docs/apps</loc></url>
    </urlset>
    """

    import gzip as _gzip

    # Fake responses
    class FakeResponse:
        def __init__(self, text: str = "", content: bytes = b"", headers=None, status_code=200):
            self._text = text
            self.content = content
            self.headers = headers or {}
            self.status_code = status_code
        @property
        def text(self):
            return self._text
        def raise_for_status(self):
            if int(self.status_code) >= 400:
                raise AssertionError(f"HTTP {self.status_code}")

    class FakeSession:
        def get(self, url, timeout=10, allow_redirects=True):
            if url.endswith("sitemap_index.xml") or url.endswith("/index.xml") or url.endswith("/sitemap.xml") or url == "https://shopify.dev/sitemap.xml":
                return FakeResponse(text=index_xml, headers={"content-type": "application/xml"})
            if url.endswith("sitemap_standard.xml.gz"):
                gz = _gzip.compress(child_sitemap_xml.encode("utf-8"))
                return FakeResponse(content=gz, headers={"content-type": "application/gzip"})
            raise AssertionError(f"Unexpected URL in FakeSession.get: {url}")

        def head(self, url, timeout=10, allow_redirects=True):
            # Not used in this test
            return FakeResponse(status_code=200)

    finder = utm.SitemapFinder("https://shopify.dev")
    finder.session = FakeSession()

    # Directly call download_sitemap on the index URL
    combined_path = finder.download_sitemap("https://shopify.dev/sitemap.xml")

    extractor = utm.WebsiteContentExtractor()
    urls = extractor.parse_sitemap(combined_path)

    assert urls == [
        "https://shopify.dev/docs/api/admin-graphql",
        "https://shopify.dev/docs/apps",
    ]


def test_process_no_sitemap_prompts_and_crawls(tmp_path: Path, monkeypatch):
    # Fake SitemapFinder that returns None (no sitemap found)
    class FakeFinder:
        def __init__(self, base_url: str, timeout: int = 10):
            self.base_url = base_url
        def find_sitemap_url(self):
            return None
        # Should not be called, but keep for interface compatibility
        def download_sitemap(self, sitemap_url: str) -> str:
            raise AssertionError("download_sitemap should not be called when no sitemap is found")

    class FakeCrawler:
        def __init__(self, base_url: str, max_depth: int = 3, max_pages: int = 500, timeout: int = 10):
            self.base_url = base_url
        def crawl(self):
            return ["https://example.com/", "https://example.com/docs/"]
        def generate_sitemap(self, urls):
            xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" \
                  + "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" \
                  + "\n".join([f"  <url><loc>{u}</loc></url>" for u in urls]) \
                  + "\n</urlset>"
            p = tmp_path / "gen.xml"
            p.write_text(xml, encoding="utf-8")
            return str(p)

    # Choose to crawl (option 1)
    monkeypatch.setattr("builtins.input", lambda prompt='': '1')
    monkeypatch.setattr(utm, "SitemapFinder", FakeFinder)
    monkeypatch.setattr(utm, "WebCrawler", FakeCrawler)
    # Avoid network during extraction
    monkeypatch.setattr(utm.WebsiteContentExtractor, "extract_content", lambda self, url: {
        "url": url, "title": "t", "content": "c", "error": None
    })

    extractor = utm.WebsiteContentExtractor()
    successful, failed = extractor.process_website(
        "https://example.com",
        separate_files=True,
        output_path=str(tmp_path),
    )

    # Pages should be saved under pages/ based on crawled URLs
    assert (tmp_path / "pages" / "index.md").exists()
    assert (tmp_path / "pages" / "docs.md").exists()
    # And sitemap should be saved
    assert (tmp_path / "sitemap.xml").exists()
    assert successful >= 0
    assert failed >= 0


def test_process_no_sitemap_cancel_raises(tmp_path: Path, monkeypatch):
    class FakeFinder:
        def __init__(self, base_url: str, timeout: int = 10):
            self.base_url = base_url
        def find_sitemap_url(self):
            return None

    monkeypatch.setattr("builtins.input", lambda prompt='': '3')
    monkeypatch.setattr(utm, "SitemapFinder", FakeFinder)

    extractor = utm.WebsiteContentExtractor()
    with pytest.raises(ValueError):
        extractor.process_website(
            "https://example.com",
            separate_files=True,
            output_path=str(tmp_path),
        )


def test_process_empty_sitemap_prompts_and_crawls(tmp_path: Path, monkeypatch):
    # Fake SitemapFinder that returns a URL but downloads an empty file
    class FakeFinder:
        def __init__(self, base_url: str, timeout: int = 10):
            self.base_url = base_url
        def find_sitemap_url(self):
            return "https://example.com/sitemap.xml"
        def download_sitemap(self, sitemap_url: str) -> str:
            p = tmp_path / "empty.xml"
            p.write_text("", encoding="utf-8")
            return str(p)

    # Fake WebCrawler that discovers two pages and generates a sitemap
    class FakeCrawler:
        def __init__(self, base_url: str, max_depth: int = 3, max_pages: int = 500, timeout: int = 10):
            self.base_url = base_url
        def crawl(self):
            return ["https://example.com/", "https://example.com/docs/"]
        def generate_sitemap(self, urls):
            xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" \
                  + "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" \
                  + "\n".join([f"  <url><loc>{u}</loc></url>" for u in urls]) \
                  + "\n</urlset>"
            p = tmp_path / "gen.xml"
            p.write_text(xml, encoding="utf-8")
            return str(p)

    # Choose to crawl (option 1)
    monkeypatch.setattr("builtins.input", lambda prompt='': '1')
    monkeypatch.setattr(utm, "SitemapFinder", FakeFinder)
    monkeypatch.setattr(utm, "WebCrawler", FakeCrawler)
    # Avoid network during extraction
    monkeypatch.setattr(utm.WebsiteContentExtractor, "extract_content", lambda self, url: {
        "url": url, "title": "t", "content": "c", "error": None
    })

    extractor = utm.WebsiteContentExtractor()
    successful, failed = extractor.process_website(
        "https://example.com",
        separate_files=True,
        output_path=str(tmp_path),
    )

    # Pages should be saved under pages/ based on crawled URLs
    assert (tmp_path / "pages" / "index.md").exists()
    assert (tmp_path / "pages" / "docs.md").exists()
    # And sitemap should be saved/updated
    assert (tmp_path / "sitemap.xml").exists()
    assert successful >= 0
    assert failed >= 0


def test_process_empty_sitemap_cancel_raises(tmp_path: Path, monkeypatch):
    class FakeFinder:
        def __init__(self, base_url: str, timeout: int = 10):
            self.base_url = base_url
        def find_sitemap_url(self):
            return "https://example.com/sitemap.xml"
        def download_sitemap(self, sitemap_url: str) -> str:
            p = tmp_path / "empty.xml"
            p.write_text("", encoding="utf-8")
            return str(p)

    monkeypatch.setattr("builtins.input", lambda prompt='': '3')
    monkeypatch.setattr(utm, "SitemapFinder", FakeFinder)
    # Avoid any extraction attempt if it were to happen
    monkeypatch.setattr(utm.WebsiteContentExtractor, "extract_content", lambda self, url: {
        "url": url, "title": "t", "content": "c", "error": None
    })

    extractor = utm.WebsiteContentExtractor()
    with pytest.raises(ValueError):
        extractor.process_website(
            "https://example.com",
            separate_files=True,
            output_path=str(tmp_path),
        )


def test_parse_sitemap_malformed_returns_empty_list(tmp_path: Path):
    # Create a malformed sitemap file
    p = tmp_path / "bad.xml"
    p.write_text("<not-xml>", encoding="utf-8")

    extractor = utm.WebsiteContentExtractor()
    urls = extractor.parse_sitemap(str(p))

    assert urls == []
