# claude-code-blogs

Auto-generated machine-readable index of articles published on
[claude.com/blog](https://claude.com/blog), in the
[llms.txt](https://llmstxt.org/) convention.

## Public URL

```
https://raw.githubusercontent.com/inuro/claude-code-blogs/main/llms.txt
```

This file is the single source of truth for consumers. It is committed to
`main` by a scheduled GitHub Actions workflow and served via GitHub's raw
content CDN. A downstream Claude Code skill (e.g. `/claude-code-blogs`) can
fetch this URL to discover the latest Claude blog articles and their
descriptions.

## How it works

1. A GitHub Actions workflow runs daily at 05:00 UTC
   (`.github/workflows/update-index.yml`) and can also be triggered manually
   via **Actions → Update Claude Blog Index → Run workflow**.
2. `scripts/build_index.py` fetches `https://claude.com/blog`, enumerates
   article links, fetches each article page for title / description /
   publish date (OpenGraph + JSON-LD), and writes `llms.txt` in the
   repository root.
3. If `llms.txt` changed, `stefanzweifel/git-auto-commit-action` commits it
   back to `main` with message `chore: update llms.txt`.

No external services or secrets are required. The workflow uses only the
built-in `GITHUB_TOKEN`.

## Output format

```
# Claude Blog

> Index of articles published on https://claude.com/blog. ...

## Articles

- [Title](https://claude.com/blog/<slug>): One-line description. (YYYY-MM-DD)
- ...
```

Entries are ordered newest-first by `article:published_time`. Entries
without a parseable publish date are listed at the end, alphabetically.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt
python scripts/build_index.py
cat llms.txt
```

The script exits non-zero (and refuses to overwrite) if the blog listing
returns no article links, which keeps a stale-but-correct `llms.txt`
available if the site layout changes unexpectedly.

## Not in scope

- The consumer skill itself (`/claude-code-blogs` or similar).
- `anthropic.com/news` (company announcements). This index only tracks the
  Claude product blog.
- Rendering a browsable HTML page. If needed later, GitHub Pages can be
  layered on top without changing the scraper.
