# Portable Glossary + TOC “Online Book” (MkDocs)

This project generates a **portable, static documentation site** (an “online book”) from a **SQLite Book DB**.

## What you get
- **Single-page Index**: one page that contains your Table of Contents + Glossary A–Z + Glossary by Category.
- Separate pages for TOC and Glossary sections (optional, still included).
- Optional **live links** that point to your resolver endpoint: `/resolve/<hex_id>`.
- **Rolodex jump**: press **A–Z** to jump to that letter section.
- **Sticky A–Z bar** and **client-side glossary search**.

## Requirements
- Python 3 (for the exporter)
- MkDocs installed (to build/serve the site)

## Quick start
1) Put your SQLite Book DB next to this project as `book.db` (or use any path).

2) Export Markdown pages from the DB:

```bash
python scripts/export_book.py --db book.db --out docs --resolver https://YOUR-HOST/resolve
```

3) Preview locally with MkDocs:

```bash
mkdocs serve
```

4) Build the static site:

```bash
mkdocs build
```

The generated site will be in the `site/` directory.

## Notes
- The Book DB is meant to be **durable** and **portable**.
- Binaries can be purged after retention; the book remains valid because it stores **terms, definitions, categories, and TOC structure**, plus pointers.
- If you don’t want live links, omit `--resolver`.
