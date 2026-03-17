#!/usr/bin/env python3
"""Export MkDocs-ready Markdown from a SQLite Book DB.

Expected tables:
- category(category_id, parent_id, name, description)
- glossary_term(term_id, term, definition, asset_hex_id, binary_included, tags, updated_at)
- glossary_term_category(term_id, category_id)
- toc_node(node_id, parent_id, title, sort_order, target_hex_id, target_type)

Outputs (overwrites placeholders):
- docs/index.md
- docs/toc.md
- docs/glossary/index.md
- docs/glossary/categories.md

Live links:
  --resolver https://YOUR-HOST/resolve
"""

import argparse
import sqlite3
from pathlib import Path
from collections import defaultdict


def md_escape(s: str) -> str:
    return (s or '').replace('', '').strip()


def make_link(hex_id: str, resolver: str | None):
    if not hex_id or not resolver:
        return None
    return f"{resolver.rstrip('/')}/{hex_id}"


def q(conn, sql, params=()):
    cur = conn.execute(sql, params)
    return cur.fetchall()


def build_toc_block(conn, resolver: str | None) -> str:
    toc_sql = """
    WITH RECURSIVE toc AS (
      SELECT
        node_id, parent_id, title, sort_order, target_hex_id, target_type,
        0 AS depth,
        printf('%06d', sort_order) || ':' || title AS path
      FROM toc_node
      WHERE parent_id IS NULL
      UNION ALL
      SELECT
        c.node_id, c.parent_id, c.title, c.sort_order, c.target_hex_id, c.target_type,
        p.depth + 1 AS depth,
        p.path || ' / ' || printf('%06d', c.sort_order) || ':' || c.title AS path
      FROM toc_node c
      JOIN toc p ON c.parent_id = p.node_id
    )
    SELECT title, depth, target_hex_id
    FROM toc
    ORDER BY path;
    """
    rows = q(conn, toc_sql)
    lines = []
    for title, depth, target_hex_id in rows:
        indent = '  ' * int(depth)
        title = md_escape(title)
        url = make_link(target_hex_id, resolver)
        lines.append(f"{indent}- [{title}]({url})" if url else f"{indent}- {title}")
    return '
'.join(lines) if lines else '_No TOC items found._'


def build_glossary_az_block(conn, resolver: str | None, heading_level: int = 2) -> str:
    sql = """
    SELECT
      upper(substr(term,1,1)) AS letter,
      term,
      definition,
      asset_hex_id,
      binary_included
    FROM glossary_term
    ORDER BY letter, term;
    """
    rows = q(conn, sql)
    buckets = defaultdict(list)
    for letter, term, definition, asset_hex_id, binary_included in rows:
        letter = (letter or '#').upper()
        if letter < 'A' or letter > 'Z':
            continue
        buckets[letter].append((term, definition, asset_hex_id, binary_included))

    letters = [c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if c in buckets]

    # Sticky A–Z bar
    if letters:
        bar_links = ' | '.join(f"[{L}](#{L.lower()})" for L in letters)
        bar = f"<div class="az-bar">{bar_links}</div>"
    else:
        return '_No glossary terms found._'

    h = '#' * heading_level
    out = [bar, '']

    for L in letters:
        out.append(f"<a id="{L.lower()}"></a>")
        out.append(f"{h} {L}")
        out.append('')
        for term, definition, asset_hex_id, binary_included in buckets[L]:
            term = md_escape(term)
            definition = md_escape(definition)
            flag = 'Yes' if int(binary_included or 0) == 1 else 'No'
            url = make_link(asset_hex_id, resolver)
            if url:
                out.append(f"- **[{term}]({url})** — {definition} _(binary included: {flag})_")
            else:
                out.append(f"- **{term}** — {definition} _(binary included: {flag})_")
        out.append('')
        out.append('[Back to top](#top)')
        out.append('')

    return '
'.join(out).strip()


def build_categories_block(conn, resolver: str | None, heading_level: int = 2) -> str:
    sql = """
    SELECT
      c.name AS category,
      g.term,
      g.definition,
      g.asset_hex_id,
      g.binary_included
    FROM category c
    JOIN glossary_term_category gc ON gc.category_id = c.category_id
    JOIN glossary_term g ON g.term_id = gc.term_id
    ORDER BY c.name, g.term;
    """
    rows = q(conn, sql)
    buckets = defaultdict(list)
    for category, term, definition, asset_hex_id, binary_included in rows:
        buckets[category].append((term, definition, asset_hex_id, binary_included))

    if not buckets:
        return '_No categorized glossary terms found._'

    h = '#' * heading_level
    out = []
    for category in sorted(buckets.keys(), key=lambda x: (x or '').lower()):
        out.append(f"{h} {md_escape(category)}")
        out.append('')
        for term, definition, asset_hex_id, binary_included in buckets[category]:
            term = md_escape(term)
            definition = md_escape(definition)
            flag = 'Yes' if int(binary_included or 0) == 1 else 'No'
            url = make_link(asset_hex_id, resolver)
            if url:
                out.append(f"- **[{term}]({url})** — {definition} _(binary included: {flag})_")
            else:
                out.append(f"- **{term}** — {definition} _(binary included: {flag})_")
        out.append('')
        out.append('[Back to top](#top)')
        out.append('')

    return '
'.join(out).strip()


def replace_placeholder(path: Path, placeholder: str, content: str):
    txt = path.read_text(encoding='utf-8')
    path.write_text(txt.replace(placeholder, content), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True, help='Path to the Book DB (SQLite)')
    ap.add_argument('--out', default='docs', help='MkDocs docs directory (default: docs)')
    ap.add_argument('--resolver', default='', help='Base URL for live links, e.g. https://YOUR-HOST/resolve')
    args = ap.parse_args()

    resolver = args.resolver.strip() or None
    out_docs = Path(args.out)

    conn = sqlite3.connect(args.db)
    try:
        toc_block = build_toc_block(conn, resolver)
        gloss_block_index = build_glossary_az_block(conn, resolver, heading_level=3)  # index page uses h3 for letters
        gloss_block_page = build_glossary_az_block(conn, resolver, heading_level=2)
        cat_block_index = build_categories_block(conn, resolver, heading_level=3)
        cat_block_page = build_categories_block(conn, resolver, heading_level=2)

        replace_placeholder(out_docs/'index.md', '<!-- TOC_CONTENT -->', toc_block)
        replace_placeholder(out_docs/'index.md', '<!-- GLOSSARY_AZ -->', gloss_block_index)
        replace_placeholder(out_docs/'index.md', '<!-- GLOSSARY_CATEGORIES -->', cat_block_index)

        replace_placeholder(out_docs/'toc.md', '<!-- TOC_CONTENT -->', toc_block)
        replace_placeholder(out_docs/'glossary'/'index.md', '<!-- GLOSSARY_AZ -->', gloss_block_page)
        replace_placeholder(out_docs/'glossary'/'categories.md', '<!-- GLOSSARY_CATEGORIES -->', cat_block_page)

    finally:
        conn.close()

    print('Export complete.')


if __name__ == '__main__':
    main()
