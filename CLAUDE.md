# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

URL to Markdown is a Python CLI tool that extracts entire websites to Markdown files. It automatically discovers sitemaps, falls back to crawling when needed, and converts HTML content to clean Markdown format.

## Architecture

### Core Components

- **`url_to_markdown.py`** - Single-file implementation containing:
  - `WebCrawler` class - Handles site crawling with robots.txt compliance
  - `URLToMarkdown` class - Main orchestrator for sitemap discovery and content extraction  
  - `SitemapDiscoverer` class - Automatic sitemap detection from multiple sources
  - Content extraction using `html2text` for clean Markdown conversion

### Key Features

- **Sitemap Discovery**: Checks robots.txt hints, common paths (/sitemap.xml, /sitemap_index.xml), and HTML link elements
- **Crawling Fallback**: Respects robots.txt disallow rules, configurable depth/page limits
- **Output Formats**: Either directory tree preserving URL structure or single consolidated file
- **Content Processing**: Main content extraction with `html2text`, metadata preservation

## Development Commands

### Installation for Development
```bash
# Create virtual environment and install in editable mode
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -e .
```

### Running the Tool
```bash
# Direct execution during development
python url_to_markdown.py https://example.com

# After installation
url-to-markdown https://example.com --limit 10
url-to-markdown https://example.com --single-file
```

### Production Installation
```bash
# Recommended: Install with pipx for isolated environment
pipx install .

# Upgrade after changes
pipx reinstall url-to-markdown
```

### Testing the Tool
```bash
# Test with a small site
python url_to_markdown.py https://example.com --limit 5 --verbose

# Test single file output
python url_to_markdown.py https://example.com --single-file --limit 3
```

## Configuration

The tool uses these key configuration options:
- `--delay`: Request delay (default 0.5s)
- `--timeout`: Request timeout (default 10s)  
- `--crawl-depth`: Max crawl depth (default 3)
- `--max-crawl-pages`: Max crawl pages (default 500)

## Dependencies

Core dependencies managed via `pyproject.toml`:
- `requests` - HTTP client
- `beautifulsoup4` - HTML parsing
- `tqdm` - Progress bars
- `html2text` - HTML to Markdown conversion

## Code Organization

- **Session Management**: Uses `requests.Session` with proper User-Agent headers
- **Error Handling**: Graceful degradation with detailed error reporting
- **Progress Tracking**: Visual progress bars for long operations
- **File Organization**: Smart URL-to-filesystem path mapping
- **Content Filtering**: Focuses on main content, strips navigation/ads

## Important Implementation Notes

- Respects robots.txt disallow rules during crawling
- Handles both XML sitemaps and sitemap index files
- Creates directory structure mirroring website URL paths
- Generates summary files with extraction statistics
- Includes proper timeout handling and rate limiting
- Uses temporary files for sitemap processing with cleanup