#!/usr/bin/env python3
import argparse, sqlite3, os
from pathlib import Path
from collections import defaultdict

DB_PATH  = os.environ.get('UNITEDSYS_DB', str(Path.home() / '.catalog' / 'catalog.db'))
DOCS_DIR = Path(__file__).parent.parent / 'docs'

def get_conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def md_escape(s):
    return (s or '').replace('\r', '').strip()

def get_entries():
    db = get_conn()
    rows = db.execute("SELECT name, description, hex, b58, category, state, version, backend, amended, grace_until FROM glossary_view WHERE state != 'evicted' ORDER BY name").fetchall()
    db.close()
    return [dict(r) for r in rows]

def build_az_block(resolver=None, heading_level=2):
    rows = get_entries()
    buckets = defaultdict(list)
    for r in rows:
        letter = (r['name'] or '#')[0].upper()
        if not ('A' <= letter <= 'Z'):
            letter = '#'
        buckets[letter].append(r)
    letters = [c for c in '#ABCDEFGHIJKLMNOPQRSTUVWXYZ' if c in buckets]
    if not letters:
        return '_No glossary entries found._'
    bar = ' | '.join(f"[{L}](#{L.lower()})" for L in letters)
    h   = '#' * heading_level
    out = [f'<div class="az-bar">{bar}</div>', '']
    for L in letters:
        out.append(f'<a id="{L.lower()}"></a>')
        out.append(f'{h} {L}')
        out.append('')
        for r in buckets[L]:
            name    = md_escape(r['name'])
            desc    = md_escape(r['description']) or '_No description yet_'
            b58     = r['b58'] or ''
            hex_id  = r['hex'] or ''
            cat     = r['category'] or 'unknown'
            ver     = r['version'] or ''
            amended = 'Yes' if r['amended'] else 'No'
            out.append(f'- **{name}** -- {desc}')
            out.append(f'  - Category: `{cat}` | Version: `{ver}` | Amended: {amended}')
            out.append(f'  - Hex: `{hex_id[:24]}...` | B58: `{b58}`')
            out.append('')
        out.append('[Back to top](#top)')
        out.append('')
    return '\n'.join(out).strip()

def build_categories_block(resolver=None, heading_level=2):
    rows = get_entries()
    buckets = defaultdict(list)
    for r in rows:
        buckets[r['category'] or 'unknown'].append(r)
    if not buckets:
        return '_No categorized entries found._'
    h   = '#' * heading_level
    out = []
    for cat in sorted(buckets.keys()):
        out.append(f'<a id="{cat.lower()}"></a>')
        out.append(f'{h} {cat}')
        out.append('')
        for r in buckets[cat]:
            name    = md_escape(r['name'])
            desc    = md_escape(r['description']) or '_No description yet_'
            b58     = r['b58'] or ''
            ver     = r['version'] or ''
            amended = 'Yes' if r['amended'] else 'No'
            out.append(f'- **{name}** -- {desc}')
            out.append(f'  - Version: `{ver}` | Amended: {amended} | B58: `{b58}`')
            out.append('')
        out.append('[Back to top](#top)')
        out.append('')
    return '\n'.join(out).strip()

def build_toc_block():
    rows = get_entries()
    buckets = defaultdict(list)
    for r in rows:
        buckets[r['category'] or 'unknown'].append(r['name'])
    out = []
    for cat in sorted(buckets.keys()):
        out.append(f'- **{cat}**')
        for name in buckets[cat]:
            out.append(f'  - {md_escape(name)}')
    return '\n'.join(out) if out else '_No entries._'

def build_rolodex():
    rows = get_entries()
    buckets = defaultdict(list)
    for r in rows:
        letter = (r['name'] or '#')[0].upper()
        if not ('A' <= letter <= 'Z'):
            letter = '#'
        buckets[letter].append(r)
    letters = sorted(buckets.keys())
    total   = len(rows)
    tab_btns = ''.join(
        f'<button class="tab-btn" data-letter="{L}" onclick="showLetter(\'{L}\')">{L}</button>'
        for L in letters
    )
    sections = []
    for L in letters:
        cards = []
        for r in buckets[L]:
            name  = (r['name'] or '').replace('<','&lt;').replace('>','&gt;')
            desc  = (r['description'] or 'No description yet').replace('<','&lt;').replace('>','&gt;')
            cat   = r['category'] or 'unknown'
            ver   = r['version'] or ''
            b58   = r['b58'] or ''
            hx    = (r['hex'] or '')[:24]
            amt   = 'YES' if r['amended'] else 'NO'
            grace = r['grace_until'] or ''
            cards.append(
                f'<div class="card">'
                f'<div class="card-name">{name}</div>'
                f'<div class="card-desc">{desc}</div>'
                f'<div class="card-meta">'
                f'<span class="tag cat">{cat}</span>'
                f'<span class="tag ver">{ver}</span>'
                f'<span class="tag amt">AMENDED:{amt}</span>'
                f'</div>'
                f'<div class="card-ids">'
                f'<span class="id-label">B58</span><span class="id-val">{b58}</span><br>'
                f'<span class="id-label">HEX</span><span class="id-val">{hx}...</span>'
                f'</div>'
                f'<div class="card-grace">GRACE: {grace}</div>'
                f'</div>'
            )
        sections.append(
            f'<div class="letter-section" id="section-{L}" style="display:none">'
            f'<div class="letter-header">{L}</div>'
            f'<div class="cards-grid">{"".join(cards)}</div>'
            f'</div>'
        )
    letters_js = str(letters).replace("'", '"')
    total_entries = total
    tab_btns_html = tab_btns
    sections_html = ''.join(sections)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UnitedSys Rolodex</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0c10;--surf:#111318;--bdr:#1e2330;--acc:#00ff9d;--acc2:#00aaff;--txt:#c8d0e0;--mut:#4a5568;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--txt);font-family:'Share Tech Mono',monospace;min-height:100vh;}}
body::before{{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,255,157,.015) 2px,rgba(0,255,157,.015) 4px);pointer-events:none;z-index:9999;}}
header{{padding:1.5rem 2rem;border-bottom:1px solid var(--bdr);display:flex;align-items:baseline;gap:1rem;}}
.logo{{font-family:'Orbitron',monospace;font-weight:900;font-size:1.5rem;color:var(--acc);letter-spacing:.15em;text-shadow:0 0 20px rgba(0,255,157,.4);}}
.subtitle{{color:var(--mut);font-size:.75rem;letter-spacing:.1em;}}
.count{{margin-left:auto;color:var(--acc2);font-size:.85rem;}}
.search-bar{{padding:.75rem 2rem;border-bottom:1px solid var(--bdr);}}
.search-bar input{{width:100%;background:var(--surf);border:1px solid var(--bdr);color:var(--acc);font-family:'Share Tech Mono',monospace;font-size:.9rem;padding:.5rem 1rem;outline:none;}}
.search-bar input:focus{{border-color:var(--acc);box-shadow:0 0 10px rgba(0,255,157,.15);}}
.search-bar input::placeholder{{color:var(--mut);}}
.tab-strip{{display:flex;flex-wrap:wrap;gap:2px;padding:.75rem 2rem;border-bottom:1px solid var(--bdr);background:var(--surf);position:sticky;top:0;z-index:100;}}
.tab-btn{{background:transparent;border:1px solid var(--bdr);color:var(--mut);font-family:'Orbitron',monospace;font-size:.65rem;font-weight:700;padding:.25rem .45rem;cursor:pointer;min-width:1.8rem;text-align:center;transition:all .15s;}}
.tab-btn:hover{{border-color:var(--acc);color:var(--acc);}}
.tab-btn.active{{background:var(--acc);border-color:var(--acc);color:var(--bg);box-shadow:0 0 12px rgba(0,255,157,.4);}}
.nav-row{{display:flex;align-items:center;gap:.5rem;padding:.5rem 2rem;}}
.nav-btn{{background:var(--surf);border:1px solid var(--bdr);color:var(--acc);font-family:'Orbitron',monospace;font-size:.7rem;padding:.3rem .8rem;cursor:pointer;transition:all .15s;}}
.nav-btn:hover{{background:var(--acc);color:var(--bg);}}
.nav-cur{{color:var(--mut);font-size:.75rem;margin:0 .5rem;}}
.content{{padding:1.5rem 2rem;}}
.letter-header{{font-family:'Orbitron',monospace;font-size:4rem;font-weight:900;color:var(--acc);opacity:.12;margin-bottom:1.5rem;}}
.cards-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem;}}
.card{{background:var(--surf);border:1px solid var(--bdr);padding:1.1rem;transition:border-color .2s,transform .2s;animation:fi .25s ease both;}}
.card:hover{{border-color:var(--acc);transform:translateY(-2px);box-shadow:0 4px 20px rgba(0,255,157,.1);}}
@keyframes fi{{from{{opacity:0;transform:translateY(6px);}}to{{opacity:1;transform:translateY(0);}}}}
.card-name{{font-family:'Orbitron',monospace;font-size:.82rem;font-weight:700;color:var(--acc2);margin-bottom:.4rem;word-break:break-all;}}
.card-desc{{font-size:.78rem;color:var(--txt);margin-bottom:.7rem;line-height:1.5;min-height:2.2rem;}}
.card-meta{{display:flex;flex-wrap:wrap;gap:.3rem;margin-bottom:.6rem;}}
.tag{{font-size:.62rem;padding:.1rem .4rem;border:1px solid;letter-spacing:.04em;}}
.tag.cat{{border-color:var(--acc2);color:var(--acc2);}}
.tag.ver{{border-color:var(--mut);color:var(--mut);}}
.tag.amt{{border-color:var(--acc);color:var(--acc);}}
.card-ids{{font-size:.62rem;color:var(--mut);margin-bottom:.3rem;line-height:1.8;}}
.id-label{{color:var(--acc);font-weight:bold;margin-right:.3rem;}}
.id-val{{word-break:break-all;}}
.card-grace{{font-size:.6rem;color:var(--mut);border-top:1px solid var(--bdr);padding-top:.3rem;margin-top:.3rem;}}
.search-results{{display:none;}}
.no-results{{color:var(--mut);text-align:center;padding:3rem;}}
</style>
</head>
<body>
<header>
  <div class="logo">UNITEDSYS</div>
  <div class="subtitle">// LIBRARY ROLODEX //</div>
  <div class="count">{total_entries} ENTRIES</div>
</header>
<div class="search-bar">
  <input type="text" id="search" placeholder="search name, category, description, b58..." oninput="doSearch(this.value)">
</div>
<div class="tab-strip">{tab_btns_html}</div>
<div class="nav-row">
  <button class="nav-btn" onclick="prevLetter()">&#9664; PREV</button>
  <span class="nav-cur" id="nav-cur"></span>
  <button class="nav-btn" onclick="nextLetter()">NEXT &#9654;</button>
</div>
<div class="content">
  {sections_html}
  <div class="search-results" id="search-results">
    <div class="cards-grid" id="search-grid"></div>
    <div class="no-results" id="no-results" style="display:none">No entries found.</div>
  </div>
</div>
<script>
const letters={letters_js};
let idx=0;
function showLetter(L){{
  document.querySelectorAll('.letter-section').forEach(s=>s.style.display='none');
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('search-results').style.display='none';
  document.getElementById('search').value='';
  const sec=document.getElementById('section-'+L);
  if(sec)sec.style.display='block';
  const btn=document.querySelector('[data-letter="'+L+'"]');
  if(btn)btn.classList.add('active');
  idx=letters.indexOf(L);
  document.getElementById('nav-cur').textContent=L+' ('+(idx+1)+'/'+letters.length+')';
  window.scrollTo(0,0);
}}
function nextLetter(){{if(idx<letters.length-1)showLetter(letters[idx+1]);}}
function prevLetter(){{if(idx>0)showLetter(letters[idx-1]);}}
function doSearch(q){{
  if(!q){{showLetter(letters[idx]);return;}}
  q=q.toLowerCase();
  document.querySelectorAll('.letter-section').forEach(s=>s.style.display='none');
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  const all=Array.from(document.querySelectorAll('.letter-section .card'));
  const hits=all.filter(c=>c.textContent.toLowerCase().includes(q));
  const grid=document.getElementById('search-grid');
  grid.innerHTML='';
  hits.forEach(c=>grid.appendChild(c.cloneNode(true)));
  document.getElementById('no-results').style.display=hits.length?'none':'block';
  document.getElementById('search-results').style.display='block';
}}
document.addEventListener('keydown',e=>{{
  if(document.activeElement===document.getElementById('search'))return;
  if(e.key==='ArrowRight')nextLetter();
  if(e.key==='ArrowLeft')prevLetter();
}});
showLetter(letters[0]);
</script>
</body>
</html>"""

def replace_placeholder(path, placeholder, content):
    if not path.exists():
        return
    txt = path.read_text(encoding='utf-8')
    if placeholder in txt:
        path.write_text(txt.replace(placeholder, content), encoding='utf-8')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--resolver', default='')
    args = ap.parse_args()
    resolver = args.resolver.strip() or None

    az_h2  = build_az_block(resolver, 2)
    az_h3  = build_az_block(resolver, 3)
    cat_h2 = build_categories_block(resolver, 2)
    toc    = build_toc_block()

    d = DOCS_DIR
    replace_placeholder(d / 'index.md',               '<!-- TOC_CONTENT -->',         toc)
    replace_placeholder(d / 'index.md',               '<!-- GLOSSARY_AZ -->',         az_h3)
    replace_placeholder(d / 'toc.md',                 '<!-- TOC_CONTENT -->',         toc)
    replace_placeholder(d / 'glossary/index.md',      '<!-- GLOSSARY_AZ -->',         az_h2)
    replace_placeholder(d / 'glossary/categories.md', '<!-- GLOSSARY_CATEGORIES -->', cat_h2)

    rolodex      = build_rolodex()
    rolodex_path = d / 'rolodex.html'
    rolodex_path.write_text(rolodex, encoding='utf-8')

    print('Export complete.')
    print(f'  DB      : {DB_PATH}')
    print(f'  Docs    : {d}')
    print(f'  Rolodex : {rolodex_path}')
    print(f'  Entries : {len(get_entries())}')

if __name__ == '__main__':
    main()
