# URL to Markdown

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Extract an entire website to Markdown files using its sitemap (or crawl when no sitemap is available). Saves either a directory tree of Markdown files or a single consolidated Markdown document.

## Features

- Automatically discovers a sitemap (robots.txt hints, common paths, or links in HTML)
- Falls back to crawling with configurable depth and page limit
- Converts main content to Markdown using `html2text`
- Saves per-page files under a `pages/` subdirectory preserving URL structure, or a single `.md` file
- Generates a summary `README.md` and saves the sitemap alongside the output

## Installation (recommended: pipx)

```bash
# If you don't have pipx yet (macOS/Homebrew)
brew install pipx
pipx ensurepath  # follow instructions if prompted

# From the project root
pipx install .
```

This installs the CLI command `url-to-markdown` into an isolated environment and makes it available on your PATH.

To upgrade after making local changes:
```bash
pipx reinstall url-to-markdown
# or, if you installed from a local path, run again from the repo root:
pipx install . --force
```

To uninstall:
```bash
pipx uninstall url-to-markdown
```

## Usage

```bash
url-to-markdown https://example.com
url-to-markdown https://example.com --limit 10
url-to-markdown https://example.com --single-file
```

### Options

- `--single-file` Save all content to one Markdown file instead of separate files
- `--delay <float>` Delay between requests (default: 0.5s)
- `--timeout <int>` Request timeout in seconds (default: 10)
- `--limit <int>` Limit number of pages to process
- `--crawl-depth <int>` Max crawl depth if no sitemap found (default: 3)
- `--max-crawl-pages <int>` Max pages to crawl if no sitemap found (default: 500)
- `--verbose` Enable verbose logging

If no sitemap is found automatically, or a sitemap is found but contains 0 URLs, the CLI will prompt you to:
1) crawl the site,
2) enter a sitemap URL manually, or
3) cancel.

When you choose to crawl, a sitemap is generated from discovered pages and saved alongside your output. In separate-files mode, page files are saved under `OUTPUT_DIR/pages/`.

## Requirements

Python 3.8+.

Dependencies are installed automatically when installing the package:
- `requests`
- `beautifulsoup4`
- `tqdm`
- `html2text`

## Development

```bash
# Create/activate a virtual environment as you prefer, then:
pip install -e .

# Run locally without installing via pipx:
python url_to_markdown.py https://example.com

# Or after editable install:
url-to-markdown -h
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
