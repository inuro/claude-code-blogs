"""Generate llms.txt index of articles from https://claude.com/blog.

Scrapes the blog listing page, collects article links, fetches each
article's metadata (title, description, publish date), and writes a
markdown-style index in the llms.txt convention to ./llms.txt.
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BLOG_ROOT = "https://claude.com/blog"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "llms.txt"
USER_AGENT = (
    "Mozilla/5.0 (compatible; claude-code-blogs-indexer/1.0; "
    "+https://github.com/inuro/claude-code-blogs)"
)
REQUEST_TIMEOUT = 20
PER_ARTICLE_SLEEP_SEC = 0.2
DESCRIPTION_MAX_CHARS = 240


@dataclass
class Article:
    url: str
    title: str
    description: str
    published: str | None  # ISO date "YYYY-MM-DD" or None


def http_get(url: str) -> str:
    resp = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.text


def collect_article_urls(listing_html: str) -> list[str]:
    soup = BeautifulSoup(listing_html, "lxml")
    urls: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        abs_url = urljoin(BLOG_ROOT + "/", href)
        parsed = urlparse(abs_url)
        if parsed.netloc != "claude.com":
            continue
        path = parsed.path.rstrip("/")
        if not path.startswith("/blog/"):
            continue
        if path == "/blog":
            continue
        # Skip sub-paths like /blog/category/... if Anthropic ever adds them.
        # Article slugs are single-segment: /blog/<slug>
        segments = [s for s in path.split("/") if s]
        if len(segments) != 2:
            continue
        urls.add(f"https://claude.com{path}")
    return sorted(urls)


def _meta(soup: BeautifulSoup, **attrs) -> str | None:
    tag = soup.find("meta", attrs=attrs)
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def _extract_published_from_jsonld(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            for key in ("datePublished", "dateCreated", "uploadDate"):
                val = item.get(key)
                if isinstance(val, str) and val:
                    return val
    return None


def _iso_to_date(value: str) -> str | None:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", value)
    return m.group(1) if m else None


def _trim(text: str, limit: int = DESCRIPTION_MAX_CHARS) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rstrip()
    return cut + "\u2026"


def parse_article(url: str, html: str) -> Article:
    soup = BeautifulSoup(html, "lxml")

    title = (
        _meta(soup, property="og:title")
        or _meta(soup, name="twitter:title")
        or (soup.title.string.strip() if soup.title and soup.title.string else None)
        or url
    )
    # Strip " | Claude" suffix that appears in <title>.
    title = re.sub(r"\s*[|\-\u2013]\s*Claude\s*$", "", title).strip()

    description = (
        _meta(soup, name="description")
        or _meta(soup, property="og:description")
        or _meta(soup, name="twitter:description")
        or ""
    )
    description = _trim(description)

    published_raw = (
        _meta(soup, property="article:published_time")
        or _meta(soup, itemprop="datePublished")
        or _extract_published_from_jsonld(soup)
    )
    published = _iso_to_date(published_raw) if published_raw else None

    return Article(url=url, title=title, description=description, published=published)


def fetch_article(url: str) -> Article | None:
    try:
        html = http_get(url)
    except requests.RequestException as e:
        print(f"warn: failed to fetch {url}: {e}", file=sys.stderr)
        return None
    try:
        return parse_article(url, html)
    except Exception as e:  # noqa: BLE001 - defensive
        print(f"warn: failed to parse {url}: {e}", file=sys.stderr)
        return None


def render_llms_txt(articles: list[Article]) -> str:
    lines: list[str] = []
    lines.append("# Claude Blog")
    lines.append("")
    lines.append(
        "> Index of articles published on https://claude.com/blog. "
        "Product news, best practices, and stories for teams building with Claude. "
        "Auto-generated daily from the source site."
    )
    lines.append("")
    lines.append("## Articles")
    lines.append("")
    for a in articles:
        suffix = f" ({a.published})" if a.published else ""
        desc = a.description or "Claude blog article."
        lines.append(f"- [{a.title}]({a.url}): {desc}{suffix}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    print(f"fetching listing: {BLOG_ROOT}", file=sys.stderr)
    try:
        listing_html = http_get(BLOG_ROOT)
    except requests.RequestException as e:
        print(f"error: failed to fetch blog listing: {e}", file=sys.stderr)
        return 1

    article_urls = collect_article_urls(listing_html)
    print(f"discovered {len(article_urls)} article URLs", file=sys.stderr)
    if not article_urls:
        print(
            "error: no article URLs found on listing page; refusing to overwrite llms.txt",
            file=sys.stderr,
        )
        return 2

    articles: list[Article] = []
    for url in article_urls:
        art = fetch_article(url)
        if art is not None:
            articles.append(art)
        time.sleep(PER_ARTICLE_SLEEP_SEC)

    if not articles:
        print("error: no articles could be parsed; refusing to overwrite", file=sys.stderr)
        return 3

    # Newest first; unknown dates sink to the bottom (stable by title).
    articles.sort(key=lambda a: (a.published is None, a.published or "", a.title.lower()))
    articles.reverse()
    # The reverse above puts unknown-date entries first; move them to the end.
    dated = [a for a in articles if a.published]
    undated = [a for a in articles if not a.published]
    undated.sort(key=lambda a: a.title.lower())
    ordered = dated + undated

    output = render_llms_txt(ordered)
    OUTPUT_PATH.write_text(output, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT_PATH} ({len(ordered)} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
