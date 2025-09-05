#!/usr/bin/env python3
"""
URL to Markdown - Automatic Sitemap Discovery and Content Extraction

This script takes a website URL, automatically finds its sitemap,
and extracts all content to Markdown files organized in directories.

Usage:
    python url_to_markdown.py https://example.com
    python url_to_markdown.py https://example.com --limit 10
"""

import sys
import argparse
import xml.etree.ElementTree as ET
import time
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime
import re
import os
import shutil
from urllib.parse import urljoin, urlparse
import tempfile

# Third-party imports (need to be installed)
try:
    import requests
    from bs4 import BeautifulSoup
    from tqdm import tqdm
    import html2text
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Install required packages with:")
    print("pip install requests beautifulsoup4 tqdm html2text")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WebCrawler:
    """Crawl a website to discover all pages."""
    
    def __init__(self, base_url: str, max_depth: int = 3, max_pages: int = 500, timeout: int = 10):
        """Initialize the web crawler."""
        self.base_url = base_url.rstrip('/')
        self.domain = urlparse(base_url).netloc
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.timeout = timeout
        self.visited_urls = set()
        self.discovered_urls = []
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; WebCrawler/1.0)'
        })
        
        # Check robots.txt
        self.disallowed_paths = self._get_robots_disallow()
    
    def _get_robots_disallow(self) -> List[str]:
        """Get disallowed paths from robots.txt."""
        disallowed = []
        robots_url = urljoin(self.base_url, '/robots.txt')
        
        try:
            response = self.session.get(robots_url, timeout=self.timeout)
            if response.status_code == 200:
                for line in response.text.split('\n'):
                    if line.strip().lower().startswith('disallow:'):
                        path = line.split(':', 1)[1].strip()
                        if path:
                            disallowed.append(path)
        except:
            pass
        
        return disallowed
    
    def _is_allowed(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt."""
        path = urlparse(url).path
        for disallowed in self.disallowed_paths:
            if path.startswith(disallowed):
                return False
        return True
    
    def _is_valid_url(self, url: str) -> bool:
        """Check if URL should be crawled."""
        parsed = urlparse(url)
        
        # Must be same domain
        if parsed.netloc != self.domain:
            return False
        
        # Skip non-HTTP(S) protocols
        if parsed.scheme not in ['http', 'https']:
            return False
        
        # Skip common non-content extensions
        skip_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.zip', '.rar', '.tar', '.gz', '.7z',
            '.mp3', '.mp4', '.avi', '.mov', '.wmv',
            '.css', '.js', '.json', '.xml', '.rss', '.atom'
        ]
        
        path_lower = parsed.path.lower()
        for ext in skip_extensions:
            if path_lower.endswith(ext):
                return False
        
        # Skip common non-content paths
        skip_paths = ['/wp-admin', '/admin', '/login', '/logout', '/api/', '/feed/', '/.well-known']
        for skip in skip_paths:
            if skip in path_lower:
                return False
        
        # Check robots.txt
        if not self._is_allowed(url):
            return False
        
        return True
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL to canonical form for deduplication.
        - Keep scheme and netloc
        - Root path becomes '/'
        - Non-root paths drop trailing slash
        - Remove fragment and query
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return url
        path = parsed.path or ''
        if path == '' or path == '/':
            norm_path = '/'
        else:
            norm_path = path.rstrip('/')
        return f"{parsed.scheme}://{parsed.netloc}{norm_path}"
    
    def _extract_links(self, url: str, html: str) -> List[str]:
        """Extract all links from HTML page."""
        links = []
        soup = BeautifulSoup(html, 'html.parser')
        
        for tag in soup.find_all(['a', 'link']):
            href = tag.get('href')
            if href:
                # Convert relative URLs to absolute
                absolute_url = urljoin(url, href)
                # Remove fragment and query parameters for cleaner URLs
                parsed = urlparse(absolute_url)
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                normalized = self._normalize_url(clean_url)
                if self._is_valid_url(normalized):
                    links.append(normalized)
        
        return list(set(links))  # Remove duplicates
    
    def crawl(self) -> List[str]:
        """Crawl the website and discover all pages."""
        logger.info(f"Starting web crawl of {self.base_url}")
        logger.info(f"Max depth: {self.max_depth}, Max pages: {self.max_pages}")
        
        # Queue: (url, depth)
        start_url = self._normalize_url(self.base_url)
        queue = [(start_url, 0)]
        self.visited_urls.add(start_url)
        
        with tqdm(total=self.max_pages, desc="Crawling pages") as pbar:
            while queue and len(self.discovered_urls) < self.max_pages:
                current_url, depth = queue.pop(0)
                
                if depth > self.max_depth:
                    continue
                
                try:
                    response = self.session.get(current_url, timeout=self.timeout)
                    if response.status_code == 200 and 'text/html' in response.headers.get('content-type', ''):
                        # Add to discovered URLs
                        self.discovered_urls.append(current_url)
                        pbar.update(1)
                        
                        # Extract links if not at max depth
                        if depth < self.max_depth:
                            links = self._extract_links(current_url, response.text)
                            for link in links:
                                if link not in self.visited_urls:
                                    self.visited_urls.add(link)
                                    queue.append((link, depth + 1))
                        
                        # Be respectful
                        time.sleep(0.1)
                    
                except Exception as e:
                    logger.debug(f"Error crawling {current_url}: {e}")
                    continue
        
        logger.info(f"Crawl complete. Discovered {len(self.discovered_urls)} pages")
        return self.discovered_urls
    
    def generate_sitemap(self, urls: List[str]) -> str:
        """Generate a sitemap XML from discovered URLs."""
        logger.info(f"Generating sitemap with {len(urls)} URLs")
        
        sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        
        for url in urls:
            sitemap_xml += '  <url>\n'
            sitemap_xml += f'    <loc>{url}</loc>\n'
            sitemap_xml += f'    <lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod>\n'
            sitemap_xml += '    <changefreq>weekly</changefreq>\n'
            sitemap_xml += '    <priority>0.5</priority>\n'
            sitemap_xml += '  </url>\n'
        
        sitemap_xml += '</urlset>'
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(sitemap_xml)
            temp_path = f.name
        
        logger.info(f"Generated sitemap saved to: {temp_path}")
        return temp_path


class SitemapFinder:
    """Find and download sitemap from a website."""
    
    def __init__(self, base_url: str, timeout: int = 10):
        """Initialize the sitemap finder."""
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; SitemapFinder/1.0)'
        })
    
    def find_sitemap_url(self) -> Optional[str]:
        """Find the sitemap URL for the website."""
        # Common sitemap locations to check
        common_paths = [
            '/sitemap.xml',
            '/sitemap_index.xml',
            '/sitemap-index.xml',
            '/sitemapindex.xml',
            '/sitemap/',
            '/sitemap.txt',
            '/sitemap.xml.gz',
            '/wp-sitemap.xml',  # WordPress
            '/page-sitemap.xml',
            '/post-sitemap.xml',
            '/news-sitemap.xml',
        ]
        
        # First, check robots.txt for sitemap location
        sitemap_from_robots = self._check_robots_txt()
        if sitemap_from_robots:
            logger.info(f"Found sitemap in robots.txt: {sitemap_from_robots}")
            return sitemap_from_robots
        
        # Try common sitemap locations
        for path in common_paths:
            url = urljoin(self.base_url, path)
            try:
                response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
                if response.status_code == 200:
                    # Verify it's actually XML
                    response = self.session.get(url, timeout=self.timeout)
                    if 'xml' in response.headers.get('content-type', '').lower() or \
                       response.text.strip().startswith('<?xml'):
                        logger.info(f"Found sitemap at: {url}")
                        return url
            except requests.RequestException:
                continue
        
        # Try to find sitemap link in the HTML
        sitemap_from_html = self._check_html_for_sitemap()
        if sitemap_from_html:
            logger.info(f"Found sitemap link in HTML: {sitemap_from_html}")
            return sitemap_from_html
        
        logger.warning("Could not find sitemap automatically")
        return None
    
    def _check_robots_txt(self) -> Optional[str]:
        """Check robots.txt for sitemap location."""
        robots_url = urljoin(self.base_url, '/robots.txt')
        try:
            response = self.session.get(robots_url, timeout=self.timeout)
            if response.status_code == 200:
                # Look for Sitemap: directive
                for line in response.text.split('\n'):
                    if line.strip().lower().startswith('sitemap:'):
                        sitemap_url = line.split(':', 1)[1].strip()
                        # Make sure it's an absolute URL
                        if not sitemap_url.startswith('http'):
                            sitemap_url = urljoin(self.base_url, sitemap_url)
                        return sitemap_url
        except requests.RequestException:
            pass
        return None
    
    def _check_html_for_sitemap(self) -> Optional[str]:
        """Check the homepage HTML for sitemap links."""
        try:
            response = self.session.get(self.base_url, timeout=self.timeout)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for links containing 'sitemap'
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if 'sitemap' in href.lower():
                        sitemap_url = urljoin(self.base_url, href)
                        # Verify it's XML
                        try:
                            resp = self.session.head(sitemap_url, timeout=self.timeout)
                            if resp.status_code == 200:
                                return sitemap_url
                        except:
                            continue
        except requests.RequestException:
            pass
        return None
    
    def download_sitemap(self, sitemap_url: str) -> str:
        """Download sitemap to a temporary file."""
        logger.info(f"Downloading sitemap from: {sitemap_url}")
        
        response = self.session.get(sitemap_url, timeout=self.timeout)
        response.raise_for_status()
        
        # Check if it's a sitemap index
        if 'sitemapindex' in response.text:
            logger.info("Found sitemap index, processing multiple sitemaps...")
            return self._process_sitemap_index(response.text, sitemap_url)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(response.text)
            temp_path = f.name
        
        logger.info(f"Sitemap downloaded to: {temp_path}")
        return temp_path
    
    def _process_sitemap_index(self, index_content: str, index_url: str) -> str:
        """Process a sitemap index and combine all sitemaps."""
        # Parse the index
        root = ET.fromstring(index_content)
        
        all_urls = []
        sitemap_urls = []
        
        # Find all sitemap URLs in the index
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == 'loc' and elem.text:
                sitemap_urls.append(elem.text.strip())
        
        logger.info(f"Found {len(sitemap_urls)} sitemaps in index")
        
        # Download and parse each sitemap
        for sitemap_url in tqdm(sitemap_urls, desc="Downloading sitemaps"):
            try:
                response = self.session.get(sitemap_url, timeout=self.timeout)
                if response.status_code == 200:
                    # Parse this sitemap
                    sitemap_root = ET.fromstring(response.text)
                    for elem in sitemap_root.iter():
                        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                        if tag == 'url':
                            url_data = {}
                            for child in elem:
                                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                                if child_tag in ['loc', 'lastmod', 'changefreq', 'priority']:
                                    url_data[child_tag] = child.text
                            if 'loc' in url_data:
                                all_urls.append(url_data)
                
                time.sleep(0.1)  # Be respectful
            except Exception as e:
                logger.warning(f"Error processing sitemap {sitemap_url}: {e}")
        
        # Create combined sitemap
        combined_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        combined_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        
        for url_data in all_urls:
            combined_xml += '  <url>\n'
            for key, value in url_data.items():
                if value:
                    combined_xml += f'    <{key}>{value}</{key}>\n'
            combined_xml += '  </url>\n'
        
        combined_xml += '</urlset>'
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(combined_xml)
            temp_path = f.name
        
        logger.info(f"Combined {len(all_urls)} URLs into single sitemap")
        return temp_path


class WebsiteContentExtractor:
    """Extract content from all pages of a website."""
    
    def __init__(self, delay: float = 0.5, timeout: int = 10):
        """Initialize the extractor."""
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; WebsiteContentExtractor/1.0)'
        })
        # Initialize html2text converter
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = False
        self.h2t.ignore_emphasis = False
        self.h2t.body_width = 0  # Don't wrap lines
        self.h2t.single_line_break = True
    
    def parse_sitemap(self, sitemap_path: str) -> List[str]:
        """Parse sitemap XML file and extract URLs."""
        logger.info(f"Parsing sitemap: {sitemap_path}")
        
        try:
            tree = ET.parse(sitemap_path)
            root = tree.getroot()
            
            urls = []
            seen = set()
            
            # Get all url elements
            for elem in root.iter():
                tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                
                if tag == 'url':
                    for child in elem:
                        child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                        if child_tag == 'loc' and child.text:
                            raw = child.text.strip()
                            # Normalize for trailing-slash duplicates
                            parsed = urlparse(raw)
                            path = parsed.path or ''
                            if path == '' or path == '/':
                                norm_path = '/'
                            else:
                                norm_path = path.rstrip('/')
                            normalized = f"{parsed.scheme}://{parsed.netloc}{norm_path}"
                            if normalized not in seen:
                                urls.append(normalized)
                                seen.add(normalized)
                            break
            
            logger.info(f"Found {len(urls)} URLs in sitemap")
            return urls
            
        except Exception as e:
            logger.error(f"Error parsing sitemap: {e}")
            raise
    
    def extract_content(self, url: str) -> Dict[str, str]:
        """Extract title and article content from a URL."""
        result = {
            'url': url,
            'title': None,
            'content': None,
            'error': None
        }
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            
            if response.status_code != 200:
                result['error'] = f"HTTP {response.status_code}"
                logger.warning(f"Error fetching {url}: HTTP {response.status_code}")
                return result
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract title
            title_tag = soup.find('title')
            if title_tag:
                result['title'] = title_tag.get_text(strip=True)
            else:
                h1_tag = soup.find('h1')
                if h1_tag:
                    result['title'] = h1_tag.get_text(strip=True)
            
            # Extract article content
            article = soup.find('article')
            
            if not article:
                # Try common content containers
                for selector in ['main', '.content', '#content', '.post', '.entry-content', 
                               '.page-content', '.documentation-content', '.docs-content']:
                    if selector.startswith('.') or selector.startswith('#'):
                        content_elem = soup.select_one(selector)
                    else:
                        content_elem = soup.find(selector)
                    
                    if content_elem:
                        article = content_elem
                        break
            
            if article:
                # Remove script and style tags
                for script in article.find_all(['script', 'style']):
                    script.decompose()
                
                # Convert to markdown
                article_html = str(article)
                article_markdown = self.h2t.handle(article_html)
                
                # Clean up the markdown
                article_markdown = self._clean_markdown(article_markdown)
                result['content'] = article_markdown
            else:
                # Fallback to body content
                body = soup.find('body')
                if body:
                    for script in body.find_all(['script', 'style', 'nav', 'header', 'footer']):
                        script.decompose()
                    
                    body_html = str(body)
                    body_markdown = self.h2t.handle(body_html)
                    result['content'] = self._clean_markdown(body_markdown)
                else:
                    result['content'] = "No article content found"
            
        except requests.RequestException as e:
            result['error'] = str(e)
            logger.warning(f"Error fetching {url}: {e}")
        except Exception as e:
            result['error'] = f"Parsing error: {str(e)}"
            logger.warning(f"Error parsing {url}: {e}")
        
        return result
    
    def _clean_markdown(self, markdown: str) -> str:
        """Clean up markdown content."""
        # Remove HTML comments first so we don't reintroduce extra blank lines later
        markdown = re.sub(r'<!--.*?-->', '', markdown, flags=re.DOTALL)

        # Remove trailing whitespace per line
        lines = [line.rstrip() for line in markdown.split('\n')]
        markdown = '\n'.join(lines)

        # Collapse excessive blank lines (allow at most a single blank line between blocks)
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)

        return markdown.strip()
    
    def process_website(self, url: str, limit: Optional[int] = None, 
                       separate_files: bool = False, output_path: str = None,
                       crawl_depth: int = 3, max_crawl_pages: int = 500) -> Tuple[int, int]:
        """Process entire website: find sitemap, extract content."""
        # Find and download sitemap
        finder = SitemapFinder(url)
        sitemap_url = finder.find_sitemap_url()
        sitemap_path = None
        sitemap_source = None
        
        if sitemap_url:
            # Download existing sitemap
            sitemap_path = finder.download_sitemap(sitemap_url)
            sitemap_source = 'found'
            print(f"✅ Found sitemap at: {sitemap_url}")
        else:
            # No sitemap found - offer to crawl
            print(f"\n⚠️ No sitemap found for {url}")
            print("\nWould you like to:")
            print("1. Crawl the website to discover pages automatically")
            print("2. Enter a sitemap URL manually")
            print("3. Cancel")
            
            choice = input("\nYour choice (1/2/3): ").strip()
            
            if choice == '1':
                # Crawl the website
                print(f"\n🕷️ Starting web crawl (depth={crawl_depth}, max_pages={max_crawl_pages})...")
                print("This may take a while depending on the website size...")
                
                crawler = WebCrawler(url, max_depth=crawl_depth, max_pages=max_crawl_pages)
                discovered_urls = crawler.crawl()
                
                if discovered_urls:
                    print(f"✅ Discovered {len(discovered_urls)} pages")
                    sitemap_path = crawler.generate_sitemap(discovered_urls)
                    sitemap_source = 'generated'
                else:
                    raise ValueError("No pages could be discovered through crawling")
                    
            elif choice == '2':
                # Manual entry
                sitemap_url = input("Enter the sitemap URL: ").strip()
                if sitemap_url:
                    sitemap_path = finder.download_sitemap(sitemap_url)
                    sitemap_source = 'manual'
                else:
                    raise ValueError("No sitemap URL provided")
            else:
                raise ValueError("Operation cancelled by user")
        
        # Create output directory if using separate files
        if separate_files:
            os.makedirs(output_path, exist_ok=True)
        
        # Save sitemap to output directory
        if sitemap_path and os.path.exists(sitemap_path):
            if separate_files:
                sitemap_save_path = os.path.join(output_path, 'sitemap.xml')
            else:
                # For single file mode, save sitemap next to the markdown file
                output_dir = os.path.dirname(output_path) if output_path else '.'
                base_name = os.path.splitext(os.path.basename(output_path))[0] if output_path else 'website'
                sitemap_save_path = os.path.join(output_dir, f'{base_name}_sitemap.xml')
            
            # Copy sitemap to permanent location
            shutil.copy2(sitemap_path, sitemap_save_path)
            logger.info(f"Saved sitemap to: {sitemap_save_path}")
            print(f"📄 Sitemap saved to: {sitemap_save_path}")
        
        try:
            # Parse sitemap
            urls = self.parse_sitemap(sitemap_path)
            
            if limit:
                urls = urls[:limit]
                logger.info(f"Processing limited to {limit} URLs")
            
            results = []
            
            logger.info("Starting content extraction...")
            
            # Extract content from each URL
            for url_to_extract in tqdm(urls, desc="Extracting content"):
                content_data = self.extract_content(url_to_extract)
                results.append(content_data)
                time.sleep(self.delay)
            
            # Save results
            if separate_files:
                self._save_to_separate_files(results, output_path)
                
                # Also save a summary file
                summary_path = os.path.join(output_path, 'README.md')
                self._save_summary(results, summary_path, sitemap_source, sitemap_url or url)
            else:
                self._save_to_markdown(results, output_path)
            
            # Calculate statistics
            successful = sum(1 for r in results if r.get('content') and not r.get('error'))
            failed = sum(1 for r in results if r.get('error'))
            
            return successful, failed
            
        finally:
            # Clean up temp file
            if sitemap_path and os.path.exists(sitemap_path):
                try:
                    os.unlink(sitemap_path)
                except:
                    pass
    
    def _save_summary(self, results: List[Dict[str, str]], summary_path: str, 
                     sitemap_source: str, source_url: str):
        """Save a summary README file with extraction statistics and metadata."""
        with open(summary_path, 'w', encoding='utf-8') as f:
            # Calculate statistics
            successful = sum(1 for r in results if r.get('content') and not r.get('error'))
            failed = sum(1 for r in results if r.get('error'))
            total = len(results)
            
            f.write("# Website Content Extraction Summary\n\n")
            f.write(f"**Source Website:** {source_url}\n")
            f.write(f"**Extraction Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Sitemap Source:** {sitemap_source}\n\n")
            
            f.write("## Statistics\n\n")
            f.write(f"- **Total Pages:** {total}\n")
            f.write(f"- **Successfully Extracted:** {successful}\n")
            f.write(f"- **Failed:** {failed}\n")
            if total > 0:
                f.write(f"- **Success Rate:** {(successful/total*100):.1f}%\n\n")
            else:
                f.write("- **Success Rate:** N/A\n\n")
            
            if failed > 0:
                f.write("## Failed Extractions\n\n")
                for result in results:
                    if result.get('error'):
                        f.write(f"- {result['url']}: {result['error']}\n")
                f.write("\n")
            
            f.write("## File Structure\n\n")
            f.write("```\n")
            f.write(".\n")
            f.write("├── sitemap.xml          # Website sitemap\n")
            f.write("├── README.md           # This file\n")
            
            # Build a simple tree structure of extracted files
            dirs = set()
            for result in results:
                if result.get('content') and not result.get('error'):
                    parsed = urlparse(result['url'])
                    path = parsed.path.strip('/')
                    if path:
                        parts = path.split('/')
                        for i in range(1, len(parts)):
                            dir_path = '/'.join(parts[:i])
                            if dir_path:
                                dirs.add(dir_path)
            
            # Show first few directories as example
            for dir_path in sorted(dirs)[:10]:
                depth = dir_path.count('/')
                indent = "│   " * depth + "├── "
                dir_name = dir_path.split('/')[-1]
                f.write(f"{indent}{dir_name}/\n")
            
            if len(dirs) > 10:
                f.write("└── ... (and more directories)\n")
            
            f.write("```\n\n")
            
            f.write("## Notes\n\n")
            f.write("- Each markdown file includes frontmatter with title, URL, and extraction date\n")
            f.write("- The directory structure mirrors the website's URL structure\n")
            f.write("- Content is extracted from `<article>` tags or main content areas\n")
    
    def _save_to_separate_files(self, results: List[Dict[str, str]], output_dir: str):
        """Save each page to a separate Markdown file preserving URL structure."""
        logger.info(f"Saving results to separate files in {output_dir}")
        
        # Ensure base and pages directories exist
        os.makedirs(output_dir, exist_ok=True)
        pages_dir = os.path.join(output_dir, 'pages')
        os.makedirs(pages_dir, exist_ok=True)
        
        # Track created directories for summary
        created_dirs = set()
        saved_files = []
        
        for result in results:
            if result.get('content') and not result.get('error'):
                # Parse URL to create file path
                parsed_url = urlparse(result['url'])
                path = parsed_url.path.strip('/')
                
                if not path or path == '':
                    # Home page
                    file_path = os.path.join(pages_dir, 'index.md')
                else:
                    # Split path into directories and filename
                    path_parts = path.split('/')
                    
                    # Check if the last part looks like a file or a directory
                    last_part = path_parts[-1]
                    if '.' not in last_part or last_part.endswith('.html') or last_part.endswith('.htm'):
                        # Convert last part to filename
                        if last_part.endswith('.html') or last_part.endswith('.htm'):
                            filename = last_part.rsplit('.', 1)[0] + '.md'
                        else:
                            filename = last_part + '.md'
                        
                        # Create directory structure
                        if len(path_parts) > 1:
                            dir_path = os.path.join(pages_dir, *path_parts[:-1])
                        else:
                            dir_path = pages_dir
                    else:
                        # Treat entire path as directory structure
                        dir_path = os.path.join(pages_dir, *path_parts)
                        filename = 'index.md'
                    
                    # Create directory if needed
                    if dir_path != pages_dir:
                        os.makedirs(dir_path, exist_ok=True)
                        created_dirs.add(dir_path)
                    
                    file_path = os.path.join(dir_path, filename)
                
                # Ensure we don't overwrite files - add number suffix if needed
                original_path = file_path
                counter = 1
                while os.path.exists(file_path):
                    base = original_path.rsplit('.md', 1)[0]
                    file_path = f"{base}_{counter}.md"
                    counter += 1
                
                # Save the file
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    # Write frontmatter
                    f.write("---\n")
                    f.write(f"title: {result.get('title', 'Untitled')}\n")
                    f.write(f"url: {result['url']}\n")
                    f.write(f"extracted: {datetime.now().isoformat()}\n")
                    f.write("---\n\n")
                    
                    # Write content
                    f.write(f"# {result.get('title', 'Untitled')}\n\n")
                    if result.get('content'):
                        f.write(result['content'])
                
                saved_files.append(file_path)
                logger.debug(f"Saved: {file_path}")
        
        # Log summary
        logger.info(f"Created {len(created_dirs)} directories")
        logger.info(f"Saved {len(saved_files)} files")
    
    def _save_to_markdown(self, results: List[Dict[str, str]], output_path: str):
        """Save extracted content to a single Markdown file."""
        logger.info(f"Saving results to {output_path}")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write header
            f.write("# Extracted Website Content\n\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total pages: {len(results)}\n\n")
            
            # Table of contents
            f.write("## Table of Contents\n\n")
            for i, result in enumerate(results, 1):
                if result.get('title'):
                    anchor = f"page-{i}"
                    f.write(f"{i}. [{result['title']}](#{anchor})\n")
            
            f.write("\n---\n\n")
            
            # Content for each page
            for i, result in enumerate(results, 1):
                anchor = f"page-{i}"
                f.write(f'<a id="{anchor}"></a>\n\n')
                
                f.write(f"## {i}. {result.get('title', f'Page {i}')}\n\n")
                f.write(f"**URL:** {result['url']}\n\n")
                
                if result.get('error'):
                    f.write(f"**Error:** {result['error']}\n\n")
                elif result.get('content'):
                    f.write("### Content\n\n")
                    f.write(result['content'])
                    f.write("\n\n")
                else:
                    f.write("*No content extracted*\n\n")
                
                f.write("\n---\n\n")


def extract_domain_name(url: str) -> str:
    """Extract domain name without protocol and TLD."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace('www.', '')
    
    # Remove common TLDs and subdomains
    parts = domain.split('.')
    
    # Common TLDs to remove
    common_tlds = ['com', 'org', 'net', 'io', 'dev', 'app', 'co', 'edu', 'gov', 'mil']
    
    # Filter out TLDs and common subdomains
    filtered_parts = []
    for part in parts:
        if part not in common_tlds and part not in ['api', 'docs', 'www']:
            filtered_parts.append(part)
    
    # If we have parts left, use them, otherwise use the first part
    if filtered_parts:
        return '_'.join(filtered_parts)
    elif parts:
        return parts[0]
    else:
        return 'website'


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Extract all content from a website to Markdown files organized in directories'
    )
    parser.add_argument('url', help='Website URL (e.g., https://example.com)')
    parser.add_argument(
        'output', 
        nargs='?', 
        default=None,
        help='Output directory path (default: domain name without TLD)'
    )
    parser.add_argument(
        '--single-file',
        action='store_true',
        help='Save all content to a single Markdown file instead of separate files'
    )
    parser.add_argument(
        '--delay', 
        type=float, 
        default=0.5,
        help='Delay between requests in seconds (default: 0.5)'
    )
    parser.add_argument(
        '--timeout', 
        type=int, 
        default=10,
        help='Request timeout in seconds (default: 10)'
    )
    parser.add_argument(
        '--limit', 
        type=int, 
        default=None,
        help='Limit number of pages to process'
    )
    parser.add_argument(
        '--crawl-depth',
        type=int,
        default=3,
        help='Maximum depth for web crawling if no sitemap found (default: 3)'
    )
    parser.add_argument(
        '--max-crawl-pages',
        type=int,
        default=500,
        help='Maximum pages to crawl if no sitemap found (default: 500)'
    )
    parser.add_argument(
        '--verbose', 
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine output path
    if args.output is None:
        # Generate default output name from URL
        output_path = extract_domain_name(args.url)
        if args.single_file:
            output_path = f"{output_path}.md"
    else:
        output_path = args.output
    
    # Default to separate files (inverse of previous behavior)
    separate_files = not args.single_file
    
    # Create extractor
    extractor = WebsiteContentExtractor(delay=args.delay, timeout=args.timeout)
    
    try:
        print(f"\n🔍 Processing website: {args.url}")
        print(f"📁 Output directory: {output_path}")
        print(f"📄 Mode: {'Separate files with directory structure' if separate_files else 'Single file'}")
        
        # Process website
        successful, failed = extractor.process_website(
            args.url,
            limit=args.limit,
            separate_files=separate_files,
            output_path=output_path,
            crawl_depth=args.crawl_depth,
            max_crawl_pages=args.max_crawl_pages
        )
        
        # Print results
        print(f"\n✅ Processing complete!")
        print(f"📊 Summary:")
        print(f"   - Successful: {successful}")
        print(f"   - Failed: {failed}")
        print(f"   - Success Rate: {(successful/(successful+failed)*100):.1f}%" if (successful+failed) > 0 else "N/A")
        print(f"📁 Output saved to: {output_path}")
        
        if separate_files:
            print(f"📄 Sitemap saved to: {os.path.join(output_path, 'sitemap.xml')}")
            print(f"📋 Summary saved to: {os.path.join(output_path, 'README.md')}")
            print(f"📂 Pages saved to: {os.path.join(output_path, 'pages/')}")
            print(f"\n💡 Tip: All extracted content is in the 'pages/' subdirectory with the site's URL structure preserved")
        
    except KeyboardInterrupt:
        print("\n⚠️ Processing interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()