<?php
// Phoenix Desktop — sector2/desktop/index.php
// Shade UI | Dropdown File Tree (drag+drop) | Switches | Dock
// Dark cockpit — #07090c / #00ff88 / monospace
// Phoenix DevOps OS | jwl247 | GPL v3
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Phoenix Desktop</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#07090c; --bg2:#0d1117; --bg3:#111820; --bg4:#161e28;
  --border:#1e2632; --accent:#00ff88; --accent2:#00aaff;
  --warn:#ffaa00; --danger:#ff4455; --text:#d0d8e0; --dim:#5a6677;
  --font:'JetBrains Mono','Fira Code','Courier New',monospace;
  --dock-h:52px; --title-h:32px; --radius:4px;
}
html,body{width:100%;height:100%;overflow:hidden;
  background:var(--bg);color:var(--text);
  font-family:var(--font);font-size:13px;user-select:none}

/* ── Desktop ─────────────────────────────────────────────────── */
#desktop{
  position:fixed;inset:0;bottom:var(--dock-h);
  background:var(--bg);
  background-image:
    radial-gradient(circle at 15% 85%, rgba(0,255,136,.04) 0%, transparent 45%),
    radial-gradient(circle at 85% 15%, rgba(0,170,255,.04) 0%, transparent 45%),
    linear-gradient(rgba(0,255,136,.012) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,255,136,.012) 1px, transparent 1px);
  background-size:100% 100%,100% 100%,28px 28px,28px 28px;
  overflow:hidden;
}

/* drop overlay — shows on active drag over desktop/windows */
.drop-zone-active{
  outline:2px dashed rgba(0,255,136,.5)!important;
  background:rgba(0,255,136,.04)!important;
}

/* ── Windows ─────────────────────────────────────────────────── */
.win{
  position:absolute;display:flex;flex-direction:column;
  min-width:300px;min-height:var(--title-h);
  background:var(--bg2);border:1px solid var(--border);
  border-radius:var(--radius);box-shadow:0 8px 32px rgba(0,0,0,.6);
  overflow:hidden;transition:box-shadow .15s,border-color .15s;
}
.win.focused{
  border-color:rgba(0,255,136,.4);
  box-shadow:0 12px 48px rgba(0,0,0,.8),0 0 0 1px rgba(0,255,136,.12)}
.win.shaded .win-body{display:none!important}
.win-title{
  display:flex;align-items:center;gap:6px;
  height:var(--title-h);padding:0 8px;cursor:grab;
  background:var(--bg3);border-bottom:1px solid var(--border);flex-shrink:0;
}
.win-title:active{cursor:grabbing}
.win-btns{display:flex;gap:5px;flex-shrink:0}
.wb{width:12px;height:12px;border-radius:50%;border:none;cursor:pointer;opacity:.7;transition:opacity .15s}
.wb:hover{opacity:1}
.wb-c{background:#ff4455}.wb-s{background:#ffaa00}.wb-m{background:#00ff88}
.win-label{flex:1;font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--accent);text-align:center;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.win-body{flex:1;overflow:hidden;position:relative}
.win-body iframe{width:100%;height:100%;border:none;background:var(--bg)}
.win-content{width:100%;height:100%;overflow:auto}
/* resize handles */
.rz{position:absolute;z-index:10}
.rz-se{bottom:0;right:0;width:14px;height:14px;cursor:se-resize}
.rz-s{bottom:0;left:14px;right:14px;height:5px;cursor:s-resize}
.rz-e{top:14px;right:0;bottom:14px;width:5px;cursor:e-resize}
.rz-sw{bottom:0;left:0;width:14px;height:14px;cursor:sw-resize}
.rz-n{top:0;left:14px;right:14px;height:5px;cursor:n-resize}
.rz-w{top:14px;left:0;bottom:14px;width:5px;cursor:w-resize}
.rz-ne{top:0;right:0;width:14px;height:14px;cursor:ne-resize}
.rz-nw{top:0;left:0;width:14px;height:14px;cursor:nw-resize}

/* ── File dropdown panel ─────────────────────────────────────── */
#files-panel{
  position:fixed;bottom:var(--dock-h);left:8px;
  width:288px;max-height:72vh;
  background:rgba(13,17,23,.98);border:1px solid var(--border);
  border-bottom:none;border-radius:var(--radius) var(--radius) 0 0;
  display:flex;flex-direction:column;z-index:850;
  box-shadow:0 -8px 32px rgba(0,0,0,.6);
  transform:translateY(100%);opacity:0;pointer-events:none;
  transition:transform .2s cubic-bezier(.4,0,.2,1),opacity .2s;
}
#files-panel.open{transform:translateY(0);opacity:1;pointer-events:auto}
#fp-head{
  display:flex;align-items:center;gap:8px;padding:10px 12px;
  border-bottom:1px solid var(--border);flex-shrink:0;
}
#fp-head span{font-size:10px;letter-spacing:.15em;text-transform:uppercase;
  color:var(--accent);flex:1}
#fp-search{
  background:var(--bg);border:1px solid var(--border);
  border-radius:var(--radius);color:var(--text);
  padding:3px 7px;font-family:var(--font);font-size:11px;
  outline:none;width:110px;
}
#fp-search:focus{border-color:var(--accent)}
#fp-tree{flex:1;overflow-y:auto;padding:4px 0}

/* tree nodes */
.tree-folder{
  display:flex;align-items:center;gap:6px;
  padding:6px 12px;cursor:pointer;font-size:11px;
  color:var(--dim);letter-spacing:.06em;
  transition:color .1s,background .1s;
}
.tree-folder:hover{color:var(--accent);background:rgba(0,255,136,.04)}
.tree-folder .tf-arrow{font-size:9px;transition:transform .15s;display:inline-block;width:10px}
.tree-folder.open .tf-arrow{transform:rotate(90deg)}
.tree-children{display:none;padding-left:4px}
.tree-folder.open + .tree-children{display:block}

.tree-file{
  display:flex;align-items:center;gap:7px;
  padding:4px 12px 4px 26px;cursor:grab;font-size:12px;
  color:var(--text);transition:all .1s;
  border-left:2px solid transparent;
}
.tree-file:hover{
  color:var(--accent);background:rgba(0,255,136,.05);
  border-left-color:var(--accent);cursor:grab;
}
.tree-file:active{cursor:grabbing}
.tree-file.dragging{opacity:.4}
.tf-icon{font-style:normal;flex-shrink:0;font-size:13px}
.tf-tav{font-size:9px;color:var(--dim);margin-left:auto;flex-shrink:0}

/* drag ghost */
#drag-ghost{
  position:fixed;pointer-events:none;z-index:9999;
  background:var(--bg3);border:1px solid var(--accent);
  border-radius:var(--radius);padding:5px 10px;font-size:11px;
  color:var(--accent);opacity:.92;display:none;white-space:nowrap;
}

/* ── Dock ─────────────────────────────────────────────────────── */
#dock{
  position:fixed;bottom:0;left:0;right:0;height:var(--dock-h);
  background:rgba(7,9,12,.97);border-top:1px solid var(--border);
  backdrop-filter:blur(14px);z-index:900;
  display:flex;align-items:center;padding:0 10px;gap:2px;
}
.dock-sep{width:1px;height:28px;background:var(--border);margin:0 5px;flex-shrink:0}
.da{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  width:46px;height:44px;border-radius:var(--radius);cursor:pointer;
  border:1px solid transparent;transition:all .15s;position:relative;gap:2px;
  flex-shrink:0;
}
.da:hover{background:rgba(0,255,136,.08);border-color:rgba(0,255,136,.2)}
.da.active{border-color:rgba(0,255,136,.3);background:rgba(0,255,136,.06)}
.da.running::after{
  content:'';position:absolute;bottom:2px;left:50%;transform:translateX(-50%);
  width:4px;height:4px;border-radius:50%;background:var(--accent);
}
.da .di{font-size:19px;line-height:1}
.da .dl{font-size:9px;color:var(--dim);letter-spacing:.04em}
.da:hover .dl{color:var(--accent)}

/* tray */
#tray{margin-left:auto;display:flex;align-items:center;gap:8px;flex-shrink:0}
.tray-chip{
  display:flex;align-items:center;gap:4px;font-size:10px;
  color:var(--dim);padding:3px 8px;border-radius:12px;
  border:1px solid transparent;transition:all .15s;cursor:default;
}
.tray-chip:hover{border-color:var(--border);color:var(--text)}
.tled{width:6px;height:6px;border-radius:50%;flex-shrink:0;transition:background .4s}
.lon{background:var(--accent);box-shadow:0 0 5px var(--accent)}
.loff{background:var(--dim)}
.lwarn{background:var(--warn);box-shadow:0 0 5px var(--warn)}
#tray-clock{font-size:12px;color:var(--text);min-width:70px;text-align:right;
  letter-spacing:.04em;padding-left:6px}

/* ── Switches ─────────────────────────────────────────────────── */
.sw-grid{display:grid;grid-template-columns:1fr auto}
.sw-lbl{
  padding:11px 14px;font-size:12px;color:var(--text);
  border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:2px;
}
.sw-lbl small{font-size:10px;color:var(--dim)}
.sw-ctrl{padding:11px 14px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:flex-end}
.tog{position:relative;width:36px;height:20px;cursor:pointer}
.tog input{opacity:0;position:absolute;width:0;height:0}
.tog-track{position:absolute;inset:0;background:var(--bg);
  border:1px solid var(--border);border-radius:10px;transition:all .2s}
.tog input:checked + .tog-track{background:rgba(0,255,136,.18);border-color:var(--accent)}
.tog-thumb{position:absolute;top:2px;left:2px;width:14px;height:14px;
  border-radius:50%;background:var(--dim);transition:all .2s;pointer-events:none}
.tog input:checked ~ .tog-thumb{transform:translateX(16px);background:var(--accent)}

/* ── Win content helpers ──────────────────────────────────────── */
.wp{padding:18px 20px}
.wp h2{font-size:14px;color:var(--accent);letter-spacing:.1em;
  text-transform:uppercase;margin-bottom:12px}
.wp p{color:var(--dim);line-height:1.7;font-size:12px;margin-bottom:8px}
.phx-btn{
  display:inline-flex;align-items:center;gap:5px;
  background:transparent;border:1px solid var(--accent);
  color:var(--accent);padding:5px 12px;border-radius:var(--radius);
  font-family:var(--font);font-size:11px;letter-spacing:.07em;
  cursor:pointer;text-transform:uppercase;transition:all .15s;margin:2px;
}
.phx-btn:hover{background:rgba(0,255,136,.1)}

/* scrollbar */
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
::-webkit-scrollbar-thumb:hover{background:var(--dim)}

/* toast */
#toasts{position:fixed;top:10px;right:10px;z-index:2000;
  display:flex;flex-direction:column;gap:5px;pointer-events:none}
.toast{
  background:var(--bg3);border:1px solid var(--border);
  border-left:3px solid var(--accent);border-radius:var(--radius);
  padding:7px 12px;font-size:11px;color:var(--text);max-width:280px;
  animation:tin .18s ease, tout .28s ease 2.7s forwards;pointer-events:auto;
}
.toast.w{border-left-color:var(--warn)}.toast.e{border-left-color:var(--danger)}
@keyframes tin{from{opacity:0;transform:translateX(16px)}to{opacity:1;transform:none}}
@keyframes tout{from{opacity:1}to{opacity:0;transform:translateX(16px)}}

/* context menu */
#ctx{position:fixed;z-index:1500;background:var(--bg3);
  border:1px solid var(--border);border-radius:var(--radius);
  padding:4px 0;min-width:165px;box-shadow:0 8px 24px rgba(0,0,0,.6);display:none}
.cx{padding:6px 14px;font-size:12px;color:var(--text);cursor:pointer}
.cx:hover{background:rgba(0,255,136,.08);color:var(--accent)}
.cx-sep{height:1px;background:var(--border);margin:3px 0}

/* tooltip */
[title]:hover::after{
  content:attr(title);position:absolute;bottom:100%;left:50%;
  transform:translateX(-50%);white-space:nowrap;
  background:var(--bg3);border:1px solid var(--border);
  color:var(--text);font-size:10px;padding:3px 7px;border-radius:var(--radius);
  pointer-events:none;margin-bottom:4px;z-index:9000;
}
</style>
</head>
<body>

<div id="desktop" ondragover="deskDragOver(event)" ondrop="deskDrop(event)"></div>

<!-- File dropdown panel -->
<div id="files-panel">
  <div id="fp-head">
    <span>⬡ File System</span>
    <input id="fp-search" type="text" placeholder="filter..." oninput="fsFilter(this.value)">
    <button class="phx-btn" onclick="fsLoad()" style="padding:2px 8px;margin:0;font-size:10px">↻</button>
  </div>
  <div id="fp-tree"></div>
</div>

<!-- Drag ghost -->
<div id="drag-ghost"></div>

<!-- Dock -->
<div id="dock">
  <div class="da" id="da-files" onclick="Files.toggle()" title="Files">
    <span class="di">📁</span><span class="dl">Files</span>
  </div>
  <div class="dock-sep"></div>
  <div class="da" id="da-office"    onclick="App.open('office')"    title="Office">
    <span class="di">📄</span><span class="dl">Office</span>
  </div>
  <div class="da" id="da-sketchpad" onclick="App.open('sketchpad')" title="Sketchpad">
    <span class="di">🎨</span><span class="dl">Sketch</span>
  </div>
  <div class="da" id="da-glossary"  onclick="App.open('glossary')"  title="Glossary">
    <span class="di">📚</span><span class="dl">Glossary</span>
  </div>
  <div class="da" id="da-review"    onclick="App.open('review')"    title="Review">
    <span class="di">⚖️</span><span class="dl">Review</span>
  </div>
  <div class="da" id="da-manual"    onclick="App.open('manual')"    title="Manual">
    <span class="di">📖</span><span class="dl">Manual</span>
  </div>
  <div class="da" id="da-lifefirst" onclick="App.open('lifefirst')" title="Life First — Laurie">
    <span class="di">💜</span><span class="dl">Laurie</span>
  </div>
  <div class="dock-sep"></div>
  <div class="da" onclick="App.open('switches')" title="Switches">
    <span class="di">⚙️</span><span class="dl">Switches</span>
  </div>
  <div class="da" onclick="App.open('terminal')" title="Terminal">
    <span class="di">⬛</span><span class="dl">Term</span>
  </div>

  <div id="tray">
    <div class="tray-chip" title="Frank kernel — port 7347">
      <div class="tled loff" id="led-frank"></div>Frank
    </div>
    <div class="tray-chip" title="Ollama AI engine">
      <div class="tled loff" id="led-ollama"></div>
      <span id="tray-model">AI</span>
    </div>
    <div class="tray-chip" title="WireGuard mesh 10.77.0.x">
      <div class="tled loff" id="led-wg"></div>WG
    </div>
    <div id="tray-clock">--:--</div>
  </div>
</div>

<div id="toasts"></div>
<div id="ctx">
  <div class="cx" onclick="App.open('office')">New Document</div>
  <div class="cx" onclick="App.open('sketchpad')">New Sketchpad</div>
  <div class="cx-sep"></div>
  <div class="cx" onclick="Files.toggle()">Toggle File Tree</div>
  <div class="cx" onclick="App.open('switches')">Switches</div>
  <div class="cx-sep"></div>
  <div class="cx" onclick="fetchStatus()">Refresh Status</div>
</div>

<script>
'use strict';

// ── Window Manager ─────────────────────────────────────────────────────────────

const WM = (() => {
  const wins = new Map();
  let zTop = 100, focused = null;
  const desk = document.getElementById('desktop');

  function open(id, title, content, opts = {}) {
    if (wins.has(id)) { focus(id); return; }

    const w = document.createElement('div');
    w.className = 'win';
    w.id = 'win-' + id;
    w.style.cssText = `left:${opts.x||80+rnd(160)}px;top:${opts.y||55+rnd(100)}px;
      width:${opts.w||720}px;height:${opts.h||500}px;z-index:${++zTop}`;

    const isSrc = typeof content === 'string' && content.startsWith('__src__');
    const src   = isSrc ? content.slice(7) : null;

    w.innerHTML = `
      <div class="win-title" data-winid="${id}">
        <div class="win-btns">
          <button class="wb wb-c" onclick="WM.close('${id}')" title="Close"></button>
          <button class="wb wb-s" onclick="WM.shade('${id}')" title="Shade"></button>
          <button class="wb wb-m" onclick="WM.maximize('${id}')" title="Maximize"></button>
        </div>
        <span class="win-label">${title}</span>
      </div>
      <div class="win-body">
        ${src
          ? `<iframe src="${src}" allow="clipboard-write;fullscreen"></iframe>`
          : `<div class="win-content">${content}</div>`}
      </div>
      ${['se','s','e','sw','n','w','ne','nw'].map(d=>`<div class="rz rz-${d}"></div>`).join('')}
    `;

    desk.appendChild(w);
    wins.set(id, { el:w, shaded:false, _max:null });
    _drag(w, id);
    _resize(w);
    _dropTarget(w, id);
    focus(id);

    const da = document.getElementById('da-' + id);
    if (da) da.classList.add('running');
  }

  function close(id) {
    const w = wins.get(id); if (!w) return;
    w.el.remove(); wins.delete(id);
    if (focused === id) focused = null;
    const da = document.getElementById('da-' + id);
    if (da) da.classList.remove('running');
  }

  function shade(id) {
    const w = wins.get(id); if (!w) return;
    w.shaded = !w.shaded;
    w.el.classList.toggle('shaded', w.shaded);
    if (!w.shaded && w._sh) w.el.style.height = w._sh;
    else { w._sh = w.el.style.height; w.el.style.height = ''; }
  }

  function maximize(id) {
    const w = wins.get(id); if (!w) return;
    if (w._max) {
      Object.assign(w.el.style, w._max); w._max = null;
    } else {
      w._max = { left:w.el.style.left, top:w.el.style.top,
                 width:w.el.style.width, height:w.el.style.height };
      w.el.style.cssText += `;left:0;top:0;width:${desk.clientWidth}px;height:${desk.clientHeight}px`;
    }
    focus(id);
  }

  function focus(id) {
    if (focused) wins.get(focused)?.el.classList.remove('focused');
    focused = id;
    const w = wins.get(id); if (!w) return;
    w.el.classList.add('focused');
    w.el.style.zIndex = ++zTop;
  }

  function _drag(el, id) {
    const bar = el.querySelector('.win-title');
    let ox, oy, on = false;
    bar.addEventListener('mousedown', e => {
      if (e.target.classList.contains('wb')) return;
      on = true; ox = e.clientX - el.offsetLeft; oy = e.clientY - el.offsetTop;
      focus(id); e.preventDefault();
    });
    document.addEventListener('mousemove', e => {
      if (!on) return;
      el.style.left = Math.max(0, Math.min(e.clientX-ox, desk.clientWidth-60))+'px';
      el.style.top  = Math.max(0, Math.min(e.clientY-oy, desk.clientHeight-32))+'px';
    });
    document.addEventListener('mouseup', ()=>{ on=false; });
    el.addEventListener('mousedown', ()=>focus(id));
  }

  function _resize(el) {
    el.querySelectorAll('.rz').forEach(h => {
      const dir = [...h.classList].find(c=>c.startsWith('rz-')).slice(3);
      let on=false,sx,sy,sw,sh,sl,st;
      h.addEventListener('mousedown', e => {
        on=true; sx=e.clientX; sy=e.clientY;
        sw=el.offsetWidth; sh=el.offsetHeight;
        sl=el.offsetLeft;  st=el.offsetTop;
        e.preventDefault(); e.stopPropagation();
      });
      document.addEventListener('mousemove', e => {
        if (!on) return;
        const dx=e.clientX-sx, dy=e.clientY-sy;
        let nw=sw,nh=sh,nl=sl,nt=st;
        if (dir.includes('e')) nw=Math.max(300,sw+dx);
        if (dir.includes('s')) nh=Math.max(120,sh+dy);
        if (dir.includes('w')){nw=Math.max(300,sw-dx); nl=sl+(sw-nw);}
        if (dir.includes('n')){nh=Math.max(120,sh-dy); nt=st+(sh-nh);}
        el.style.width=nw+'px'; el.style.height=nh+'px';
        el.style.left=nl+'px';  el.style.top=nt+'px';
      });
      document.addEventListener('mouseup', ()=>{on=false;});
    });
  }

  function _dropTarget(el, id) {
    el.addEventListener('dragover', e => {
      e.preventDefault(); e.dataTransfer.dropEffect = 'copy';
      el.classList.add('drop-zone-active');
    });
    el.addEventListener('dragleave', () => el.classList.remove('drop-zone-active'));
    el.addEventListener('drop', e => {
      e.preventDefault();
      el.classList.remove('drop-zone-active');
      try {
        const f = JSON.parse(e.dataTransfer.getData('text/plain'));
        _openFileInWin(f, id);
      } catch {}
    });
  }

  function _openFileInWin(file, winId) {
    // Open file in Office if it's a doc, or in the appropriate app
    const docMimes = ['text/','application/json','application/vnd.','application/pdf'];
    const isDoc = docMimes.some(m => (file.mime_type||'').startsWith(m));
    if (isDoc) {
      // Pass TAV to Office via URL param
      const w = wins.get('office');
      if (w) {
        const iframe = w.el.querySelector('iframe');
        if (iframe) { iframe.src = `/office/?tav=${file.tav}`; return; }
      }
      open('office', '⬡ OFFICE — ' + file.filename,
        `__src__/office/?tav=${file.tav}`, { x:80, y:40, w:1100, h:660 });
      focus('office');
    }
    toast(`Opening ${file.filename}`);
  }

  return { open, close, shade, maximize, focus };
})();

function rnd(n){ return Math.floor(Math.random()*n); }


// ── App registry ───────────────────────────────────────────────────────────────

const App = (() => {
  const DEFS = {
    office:    { t:'⬡ OFFICE — Document',   c:'__src__/office/',    o:{x:80, y:40, w:1100,h:660}},
    sketchpad: { t:'⬡ SKETCHPAD',           c:'__src__/sketchpad/', o:{x:120,y:60, w:820, h:580}},
    glossary:  { t:'⬡ GLOSSARY',            c:'__src__/glossary/',  o:{x:180,y:70, w:900, h:600}},
    review:    { t:'⬡ REVIEW PLATFORM',     c:'__src__/review/',    o:{x:160,y:80, w:900, h:600}},
    manual:    { t:'⬡ OPERATOR MANUAL',     c:'__src__/manual/',    o:{x:150,y:60, w:860, h:600}},
    lifefirst: { t:'⬡ LIFE FIRST — Laurie', c:'__src__/lifefirst/', o:{x:100,y:60, w:700, h:560}},
    switches:  { t:'⬡ SWITCHES',            c:switchesHTML,          o:{x:300,y:80, w:360, h:450}},
    terminal:  { t:'⬡ TERMINAL',            c:termHTML,              o:{x:220,y:100,w:640, h:400}},
    welcome:   { t:'⬡ PHOENIX OS',          c:welcomeHTML,           o:{x:80, y:55, w:500, h:320}},
  };
  function open(id) {
    const d = DEFS[id];
    if (!d) { toast('Unknown app: '+id,'w'); return; }
    const content = typeof d.c === 'function' ? d.c() : d.c;
    WM.open(id, d.t, content, d.o);
  }
  return { open };
})();


// ── File system dropdown ───────────────────────────────────────────────────────

const Files = (() => {
  const panel  = document.getElementById('files-panel');
  const tree   = document.getElementById('fp-tree');
  const ghost  = document.getElementById('drag-ghost');
  const da     = document.getElementById('da-files');
  let   open   = false;
  let   allFiles = [];

  const SECTORS = [
    { key:'sector1', label:'Sector 1 — Boot/Kernel', icon:'⚙' },
    { key:'sector2', label:'Sector 2 — Packages',    icon:'📦' },
    { key:'sector3', label:'Sector 3 — Comms',       icon:'📡' },
    { key:'sector4', label:'Sector 4 — Helix+Frank', icon:'⬡' },
    { key:'laurie',  label:'Life First — Laurie',    icon:'💜' },
  ];

  const MIME_ICONS = {
    'text/x-python':'🐍','text/javascript':'🟨','text/x-php':'🐘',
    'application/json':'{}','text/markdown':'📝','text/html':'🌐',
    'application/pdf':'📕','text/csv':'📊','text/plain':'📄',
    'text/x-sh':'⬛','text/x-c':'⚙',
  };
  function icon(m){ return MIME_ICONS[m] || '📄'; }

  function toggle() {
    open = !open;
    panel.classList.toggle('open', open);
    da.classList.toggle('active', open);
    if (open && !allFiles.length) load();
  }

  function load() {
    fetch('/desktop/api/files.php')
      .then(r => r.json())
      .then(d => { allFiles = d.documents || []; render(allFiles); })
      .catch(() => { allFiles = MOCK; render(MOCK); });
  }

  function render(files) {
    const q = (document.getElementById('fp-search').value||'').toLowerCase();
    const items = q ? files.filter(f=>f.filename.toLowerCase().includes(q)) : files;
    const by = {};
    items.forEach(f => { const k=f.owner==='laurie'?'laurie':(f.sector||'sector2');
      (by[k]=by[k]||[]).push(f); });

    tree.innerHTML = '';
    SECTORS.forEach(s => {
      const list = by[s.key]||[];
      if (!list.length) return;

      const folder = document.createElement('div');
      folder.innerHTML = `
        <div class="tree-folder" onclick="this.classList.toggle('open');
          this.nextElementSibling.style.display=this.classList.contains('open')?'block':'none'">
          <span class="tf-arrow">▶</span>
          <span style="margin-right:5px">${s.icon}</span>
          <span>${s.label}</span>
          <span style="margin-left:auto;font-size:10px;color:var(--dim)">${list.length}</span>
        </div>
        <div class="tree-children" style="display:none"></div>
      `;
      const children = folder.querySelector('.tree-children');
      list.slice(0, 100).forEach(f => {
        const row = document.createElement('div');
        row.className = 'tree-file';
        row.draggable = true;
        row.innerHTML = `<i class="tf-icon">${icon(f.mime_type)}</i>
          <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${f.filename}</span>
          <span class="tf-tav">${(f.tav||'').slice(0,6)}</span>`;
        row.addEventListener('dblclick', () => {
          WM.open('office','⬡ OFFICE — '+f.filename,`__src__/office/?tav=${f.tav}`,
                  {x:80,y:40,w:1100,h:660});
          toast('Opening '+f.filename);
        });
        row.addEventListener('dragstart', e => startDrag(e, f, row));
        row.addEventListener('dragend',   () => endDrag(row));
        children.appendChild(row);
      });
      tree.appendChild(folder);
    });
  }

  // drag + drop
  function startDrag(e, file, el) {
    e.dataTransfer.setData('text/plain', JSON.stringify(file));
    e.dataTransfer.effectAllowed = 'copy';
    el.classList.add('dragging');
    ghost.textContent = icon(file.mime_type) + '  ' + file.filename;
    ghost.style.display = 'block';
    document.addEventListener('mousemove', moveGhost);
  }

  function moveGhost(e) {
    ghost.style.left = (e.clientX + 14) + 'px';
    ghost.style.top  = (e.clientY + 8)  + 'px';
  }

  function endDrag(el) {
    el.classList.remove('dragging');
    ghost.style.display = 'none';
    document.removeEventListener('mousemove', moveGhost);
  }

  window.fsFilter = v => render(allFiles);
  window.fsLoad   = load;

  const MOCK = [
    {tav:'3vKmRp4x',filename:'frank.py',          sector:'sector4',mime_type:'text/x-python'},
    {tav:'9nQxBf2y',filename:'helix.py',           sector:'sector4',mime_type:'text/x-python'},
    {tav:'7cJhLm8z',filename:'warthunder_suit.py', sector:'sector2',mime_type:'text/x-python'},
    {tav:'5pWsKr1v',filename:'intake.sh',          sector:'sector2',mime_type:'text/x-sh'},
    {tav:'2mLqBn6t',filename:'frank_pager.py',     sector:'sector4',mime_type:'text/x-python'},
    {tav:'8kRjPn3w',filename:'config.php',         sector:'sector2',mime_type:'text/x-php'},
    {tav:'4hXcMd7q',filename:'module_7_voice_ai.php',sector:'sector2',mime_type:'text/x-php',owner:'laurie'},
  ];

  return { toggle, load };
})();

// desktop drop (opens file in new Office window)
function deskDragOver(e){ e.preventDefault(); e.dataTransfer.dropEffect='copy'; }
function deskDrop(e){
  e.preventDefault();
  try {
    const f = JSON.parse(e.dataTransfer.getData('text/plain'));
    WM.open('office-'+f.tav,'⬡ OFFICE — '+f.filename,
      `__src__/office/?tav=${f.tav}`,{x:e.clientX-400,y:e.clientY-200,w:1100,h:660});
    toast('Opened '+f.filename);
  } catch {}
}

// close files panel on outside click
document.addEventListener('click', e => {
  const panel = document.getElementById('files-panel');
  const da    = document.getElementById('da-files');
  if (panel.classList.contains('open') &&
      !panel.contains(e.target) && !da.contains(e.target)) {
    panel.classList.remove('open');
    da.classList.remove('active');
  }
});


// ── App content builders ───────────────────────────────────────────────────────

function welcomeHTML(){return`<div class="wp">
  <h2>Phoenix Desktop</h2>
  <p>Deterministic. Agnostic. Self-healing. Versioned.<br>
  Easier than anything on the planet.</p>
  <p style="font-size:11px;color:var(--dim)">
    Click <b style="color:var(--accent)">Files</b> in the dock → expand sectors → drag files into windows<br>
    Right-click desktop for quick actions</p>
  <div style="margin-top:16px">
    <button class="phx-btn" onclick="App.open('office')"  style="border-color:var(--accent2)">Office</button>
    <button class="phx-btn" onclick="App.open('sketchpad')">Sketchpad</button>
    <button class="phx-btn" onclick="App.open('glossary')">Glossary</button>
    <button class="phx-btn" onclick="App.open('manual')">Manual</button>
    <button class="phx-btn" onclick="App.open('lifefirst')">Life First</button>
  </div>
</div>`;}

function switchesHTML(){
  const sw=[
    {id:'sw-ai',       lbl:'AI Suggestions',      sub:'Office right-pane AI',  def:true },
    {id:'sw-autoforge',lbl:'Auto-Forge on Save',  sub:'Seals doc on Ctrl+S',   def:false},
    {id:'sw-index',    lbl:'Index New Documents', sub:'Add to Glossary + FTS', def:true },
    {id:'sw-lifefirst',lbl:'Life First Security', sub:'Laurie privacy active',  def:true },
    {id:'sw-wg',       lbl:'WireGuard',           sub:'10.77.0.x mesh',        def:true },
    {id:'sw-audit',    lbl:'Full Audit Log',      sub:'All ops to D1',         def:true },
    {id:'sw-quadling', lbl:'Quadralingual Vault', sub:'L1 security layer',     def:true },
    {id:'sw-witness',  lbl:'Witness Required',    sub:'2-signer for Restricted',def:false},
  ];
  return`<div class="sw-grid">${sw.map(s=>{
    const ck = localStorage.getItem(s.id)!==null ? localStorage.getItem(s.id)==='1' : s.def;
    return`<div class="sw-lbl">${s.lbl}<small>${s.sub}</small></div>
    <div class="sw-ctrl"><label class="tog">
      <input type="checkbox" id="${s.id}" ${ck?'checked':''}
        onchange="localStorage.setItem('${s.id}',this.checked?'1':'0');
          toast(this.checked?'${s.lbl} ON':'${s.lbl} OFF')">
      <div class="tog-track"></div><div class="tog-thumb"></div>
    </label></div>`;}).join('')}</div>`;
}

function termHTML(){return`
<div style="background:#000;height:100%;display:flex;flex-direction:column">
  <div id="tlines" style="flex:1;overflow-y:auto;padding:10px 12px;
    font-family:var(--font);font-size:12px;color:#00ff88;line-height:1.65">
    <div>Phoenix Terminal [read-only status interface]</div>
    <div style="color:#5a6677">Type 'help' for commands</div>
  </div>
  <div style="display:flex;align-items:center;padding:6px 12px;
    border-top:1px solid #1e2632;background:#000">
    <span style="color:#00ff88;font-size:12px;flex-shrink:0">ϕ $&nbsp;</span>
    <input id="tin" style="flex:1;background:transparent;border:none;
      color:#00ff88;font-family:var(--font);font-size:12px;outline:none"
      onkeydown="if(event.key==='Enter'){termRun(this.value);this.value=''}">
  </div>
</div>`;}

function termRun(cmd){
  const o=document.getElementById('tlines'); if(!o) return;
  const cmds={
    help:()=>'status | frank | ollama | wg | clear | apps',
    status:()=>{fetchStatus();return'Polling...'},
    frank:()=>'Frank HTTP: localhost:7347 | phoenix-kernel.service',
    ollama:()=>'Ollama: localhost:11434 | llama3.1 / llama3.2:3b / deepseek-r1:1.5b',
    wg:()=>'WireGuard: 10.77.0.1 (win) 10.77.0.2 (wsl) 10.77.0.3 (ext)',
    apps:()=>'office | sketchpad | glossary | review | manual | lifefirst',
    clear:()=>{o.innerHTML='';return null},
  };
  const fn=cmds[cmd.trim().toLowerCase()];
  const r=fn?fn():`not found: ${cmd}`;
  if(r!==null){
    const d=document.createElement('div');
    d.innerHTML=`<span style="color:#5a6677">$ ${cmd}</span><br>
      <span style="color:#d0d8e0">${r}</span>`;
    o.appendChild(d); o.scrollTop=o.scrollHeight;
  }
}


// ── System status ──────────────────────────────────────────────────────────────

function fetchStatus(){
  fetch('/desktop/api/status.php')
    .then(r=>r.json())
    .then(d=>{
      setLED('frank', d.frank?.ok);
      setLED('ollama',d.ollama?.ok);
      setLED('wg',    d.wg?.ok);
      const m=d.ollama?.model||'';
      document.getElementById('tray-model').textContent =
        m ? m.replace('llama3.1','ll3.1').replace('llama3.2:3b','ll3.2').replace('deepseek-r1','ds-r1') : 'AI';
    }).catch(()=>{});
}
function setLED(n,ok){
  const el=document.getElementById('led-'+n); if(!el) return;
  el.className='tled '+(ok===true?'lon':ok===false?'loff':'lwarn');
}
function startClock(){
  const el=document.getElementById('tray-clock');
  const tick=()=>{el.textContent=new Date().toLocaleTimeString('en-US',
    {hour:'2-digit',minute:'2-digit',hour12:false})};
  tick(); setInterval(tick,1000);
}

function toast(msg,t){
  const el=document.createElement('div');
  el.className='toast'+(t?' '+t:'');
  el.textContent=msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(()=>el.remove(),3200);
}

// context menu
const ctx=document.getElementById('ctx');
document.getElementById('desktop').addEventListener('contextmenu',e=>{
  e.preventDefault();
  ctx.style.display='block';
  ctx.style.left=Math.min(e.clientX,innerWidth-175)+'px';
  ctx.style.top=Math.min(e.clientY,innerHeight-155)+'px';
});
document.addEventListener('click',()=>{ctx.style.display='none';});


// ── Global Shell Toggle — backtick or F12 ────────────────────────────────────
//
// Slides down from top of screen over everything.
// Real commands POST to api/shell.php (exec wrapper).
// Falls back to local status commands when offline.

const Shell = (() => {
  let open   = false;
  let hist   = [];
  let hIdx   = -1;
  let el, output, input;

  function build() {
    el = document.createElement('div');
    el.id = 'global-shell';
    el.style.cssText = `
      position:fixed;top:0;left:0;right:0;z-index:99999;
      height:340px;background:rgba(5,8,14,0.97);
      border-bottom:2px solid var(--accent);
      display:flex;flex-direction:column;
      transform:translateY(-100%);
      transition:transform 0.22s cubic-bezier(0.4,0,0.2,1);
      font-family:var(--font);font-size:12px;
      box-shadow:0 8px 40px rgba(0,0,0,0.8);
    `;

    const hdr = document.createElement('div');
    hdr.style.cssText = `
      display:flex;align-items:center;gap:10px;padding:5px 12px;
      background:rgba(0,255,136,0.06);border-bottom:1px solid var(--border);
      flex-shrink:0;
    `;
    hdr.innerHTML = `
      <span style="color:var(--accent);letter-spacing:2px;font-size:9px;text-transform:uppercase">Phoenix Shell</span>
      <span style="color:var(--dim);font-size:9px;" id="gsh-cwd">jwlef@phoenix-ext</span>
      <span style="margin-left:auto;color:var(--dim);font-size:8px;letter-spacing:1px">F12 / \` to close</span>
    `;

    output = document.createElement('div');
    output.id = 'gsh-output';
    output.style.cssText = `
      flex:1;overflow-y:auto;padding:8px 12px;color:#aac;
      font-size:11px;line-height:1.7;
    `;
    output.innerHTML = `<span style="color:var(--accent)">Phoenix Shell ready — type help for commands</span>\n`;

    const inputRow = document.createElement('div');
    inputRow.style.cssText = `
      display:flex;align-items:center;gap:6px;padding:6px 12px;
      border-top:1px solid var(--border);flex-shrink:0;
      background:rgba(0,0,0,0.3);
    `;
    inputRow.innerHTML = `
      <span style="color:var(--accent);font-size:11px;flex-shrink:0">jwlef@phoenix ›</span>
    `;
    input = document.createElement('input');
    input.style.cssText = `
      flex:1;background:transparent;border:none;outline:none;
      color:var(--text);font-family:var(--font);font-size:11px;
      caret-color:var(--accent);
    `;
    input.placeholder = '';
    inputRow.appendChild(input);

    el.appendChild(hdr);
    el.appendChild(output);
    el.appendChild(inputRow);
    document.body.appendChild(el);

    input.addEventListener('keydown', onKey);
  }

  function onKey(e) {
    if (e.key === 'Enter') {
      const cmd = input.value.trim();
      input.value = '';
      if (!cmd) return;
      hist.unshift(cmd); hIdx = -1;
      if (hist.length > 100) hist.pop();
      run(cmd);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      hIdx = Math.min(hIdx + 1, hist.length - 1);
      input.value = hist[hIdx] || '';
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      hIdx = Math.max(hIdx - 1, -1);
      input.value = hIdx < 0 ? '' : hist[hIdx];
    } else if (e.key === 'Escape') {
      toggle(false);
    }
  }

  function print(text, color) {
    const line = document.createElement('div');
    line.style.color = color || 'var(--text)';
    line.style.whiteSpace = 'pre-wrap';
    line.textContent = text;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
  }

  function prompt_echo(cmd) {
    const line = document.createElement('div');
    line.style.cssText = 'color:var(--dim);';
    line.textContent = `› ${cmd}`;
    output.appendChild(line);
  }

  // Built-in commands (no server needed)
  const BUILTINS = {
    help: () => {
      print(`Phoenix Shell — Commands:
  status          System status (Frank, Ollama, WireGuard)
  mixer           Open Mixer
  switches        Open Switches
  files           Open File Tree
  desk            Open Desktop window
  clear           Clear output
  frank           Frank kernel status
  ollama          Ollama status + models
  wg              WireGuard status
  threat          Current threat level
  services        All service states
  run <cmd>       Execute shell command on phoenix-ext`, 'var(--accent)');
    },
    clear: () => { output.innerHTML = ''; },
    mixer:    () => { App.open('mixer');    toggle(false); },
    switches: () => { App.open('switches'); toggle(false); },
    files:    () => { Files.toggle();       toggle(false); },
    desk:     () => { App.open('welcome');  toggle(false); },
    frank:    () => fetchAndPrint('/desktop/api/sysinfo.php', d => `Frank: ${d.security?.buffer_level||'─'} | Threat: ${d.threat?.label||'─'}`),
    ollama:   () => fetchAndPrint('/desktop/api/sysinfo.php', d => `Ollama: running`),
    wg:       () => fetchAndPrint('/desktop/api/sysinfo.php', d => `WireGuard: see mixer`),
    threat:   () => fetchAndPrint('/desktop/api/sysinfo.php', d => {
      const t = d.threat || {};
      return `Threat: ${t.label||'─'} (${t.level||'─'}/5)\nLoad: ${t.load1||'─'} / ${t.load5||'─'} / ${t.load15||'─'}\n${(t.detail||[]).join(', ')||'No anomalies'}`;
    }),
    status:   () => fetchAndPrint('/desktop/api/sysinfo.php', d => {
      const m = d.memory || {};
      return `CPU: ${d.cpu_pct||'─'}%  RAM: ${m.ram_used_mb||'─'}/${m.ram_total_mb||'─'}MB (${m.ram_pct||'─'}%)  Swap: ${m.swap_pct||'─'}%\nThreat: ${d.threat?.label||'─'}  Buffer: ${d.security?.buffer_level||'─'}`;
    }),
    services: () => fetchAndPrint('/desktop/api/service.php', d => {
      return (d.services||[]).map(s => `  ${s.state==='active'?'●':'○'} ${s.label.padEnd(16)} ${s.state}`).join('\n');
    }),
  };

  function fetchAndPrint(url, fmt) {
    fetch(url).then(r=>r.json()).then(d => print(fmt(d), 'var(--accent)')).catch(e => print(`Error: ${e.message}`, 'var(--danger)'));
  }

  async function run(cmd) {
    prompt_echo(cmd);
    const parts  = cmd.trim().split(/\s+/);
    const name   = parts[0].toLowerCase();
    const args   = parts.slice(1).join(' ');

    // Built-in
    if (BUILTINS[name]) { BUILTINS[name](args); return; }

    // run <command> → POST to api/shell.php
    if (name === 'run' && args) {
      print(`Executing: ${args}`, 'var(--dim)');
      try {
        const res  = await fetch('/desktop/api/shell.php', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cmd: args }),
        });
        const data = await res.json();
        if (data.out)  print(data.out.trimEnd());
        if (data.err)  print(data.err.trimEnd(), 'var(--warn)');
        if (data.error) print(data.error, 'var(--danger)');
      } catch(e) { print(`shell.php offline: ${e.message}`, 'var(--danger)'); }
      return;
    }

    // Unknown — try as shell command via run
    print(`Unknown command: ${name}  (use 'run ${cmd}' to execute on phoenix-ext)`, 'var(--dim)');
  }

  function toggle(force) {
    open = (force !== undefined) ? force : !open;
    if (!el) build();
    el.style.transform = open ? 'translateY(0)' : 'translateY(-100%)';
    if (open) setTimeout(() => input?.focus(), 250);
  }

  // Global keyboard listener
  document.addEventListener('keydown', e => {
    // Backtick or F12 — ignore if typing in an input/textarea (except our own shell input)
    const inInput = document.activeElement.tagName === 'INPUT' ||
                    document.activeElement.tagName === 'TEXTAREA';
    if (inInput && document.activeElement !== input) return;

    if (e.key === '`' || e.key === 'F12') {
      e.preventDefault();
      toggle();
    }
  });

  return { toggle, run, print };
})();


// ── Boot ───────────────────────────────────────────────────────────────────────

startClock();
fetchStatus();
setInterval(fetchStatus, 28000);
App.open('welcome');
setTimeout(()=>toast('Phoenix Desktop'),500);
setTimeout(()=>toast('` or F12 — Global Shell',),1800);
</script>
</body>
</html>
