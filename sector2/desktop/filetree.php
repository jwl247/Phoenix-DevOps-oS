<?php
/**
 * filetree.php — Phoenix Assignable File Tree
 * Dropdown file browser with user-defined assignable groups.
 *
 * - Drag any file → drop onto a group header to assign it
 * - Right-click any file → assign to group, remove from group
 * - Right-click any group → rename, delete, reorder
 * - Create new groups with the + button
 * - Drag files out of groups to unassign
 * - Groups persist to /var/phoenix/file_assignments.json
 * - Double-click any file → opens in Office window (if in Desktop)
 *   or direct download if standalone
 *
 * Phoenix DevOps OS | jwl247 | GPL v3
 */
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phoenix File Tree</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:      #07090c;
  --panel:   #0d1117;
  --item:    #111820;
  --border:  #1e2a38;
  --accent:  #00ff88;
  --red:     #ff3b5c;
  --amber:   #ffaa00;
  --blue:    #00aaff;
  --purple:  #9b59ff;
  --muted:   #556677;
  --text:    #c8d8e8;
  --font:    'Courier New', Courier, monospace;
  --indent:  14px;
}
body { background: var(--bg); color: var(--text); font-family: var(--font);
       font-size: 11px; height: 100vh; display: flex; flex-direction: column;
       overflow: hidden; user-select: none; }

/* ── Header ──────────────────────────────────────────────────────────────── */
#hdr { background: var(--panel); border-bottom: 1px solid var(--border);
       padding: 7px 10px; display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
#search { flex: 1; background: #0a1018; border: 1px solid var(--border); border-radius: 3px;
          color: var(--text); font-family: var(--font); font-size: 10px; padding: 4px 8px;
          outline: none; }
#search:focus { border-color: var(--accent); }
#search::placeholder { color: var(--muted); }
#add-group-btn { width: 22px; height: 22px; border-radius: 3px; border: 1px solid var(--border);
                 background: transparent; color: var(--muted); cursor: pointer; font-size: 14px;
                 display: flex; align-items: center; justify-content: center;
                 transition: all 0.15s; flex-shrink: 0; line-height: 1; }
#add-group-btn:hover { border-color: var(--accent); color: var(--accent); }

/* ── Tree container ──────────────────────────────────────────────────────── */
#tree { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 4px 0; }
#tree::-webkit-scrollbar { width: 4px; }
#tree::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ── Section (group or sector) ───────────────────────────────────────────── */
.section-hdr {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 8px; cursor: pointer;
  font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase;
  color: var(--muted); position: relative;
  border-bottom: 1px solid var(--border);
  transition: background 0.15s;
}
.section-hdr:hover { background: rgba(255,255,255,0.03); }
.section-hdr .arrow { font-size: 8px; transition: transform 0.2s; flex-shrink: 0; }
.section-hdr.open .arrow { transform: rotate(90deg); }
.section-hdr.group-hdr { color: var(--accent); border-left: 2px solid var(--accent); }
.section-hdr.group-hdr.drop-target { background: rgba(0,255,136,0.08); border-left-color: var(--accent);
  box-shadow: inset 0 0 0 1px rgba(0,255,136,0.3); }
.section-hdr .badge { margin-left: auto; background: var(--border); color: var(--muted);
                       border-radius: 10px; padding: 1px 6px; font-size: 8px; }
.section-children { display: none; }
.section-hdr.open ~ .section-children { display: block; }

/* ── File / dir item ─────────────────────────────────────────────────────── */
.tree-item {
  display: flex; align-items: center; gap: 5px;
  padding: 3px 8px; cursor: pointer; position: relative;
  transition: background 0.1s;
}
.tree-item:hover { background: rgba(255,255,255,0.04); }
.tree-item.selected { background: rgba(0,255,136,0.08); }
.tree-item.dragging { opacity: 0.4; }
.tree-item .item-icon { width: 12px; text-align: center; flex-shrink: 0; font-size: 10px; }
.tree-item .item-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
                         color: var(--text); font-size: 10px; }
.tree-item .item-ext  { font-size: 8px; color: var(--muted); flex-shrink: 0; }
.tree-item .assigned-badge { font-size: 7px; color: var(--accent); letter-spacing: 0;
                              border: 1px solid rgba(0,255,136,0.3); border-radius: 8px;
                              padding: 0 4px; flex-shrink: 0; }
/* indentation */
.tree-item[data-depth="1"] { padding-left: calc(8px + var(--indent) * 1); }
.tree-item[data-depth="2"] { padding-left: calc(8px + var(--indent) * 2); }
.tree-item[data-depth="3"] { padding-left: calc(8px + var(--indent) * 3); }

/* dir toggle */
.dir-toggle { font-size: 8px; color: var(--muted); flex-shrink: 0;
               transition: transform 0.15s; cursor: pointer; }
.dir-toggle.open { transform: rotate(90deg); }
.dir-children { display: none; }
.dir-children.open { display: block; }

/* ── EXT colors ──────────────────────────────────────────────────────────── */
.ext-py   { color: #3572A5; } .ext-js  { color: #f1e05a; }
.ext-php  { color: #4F5D95; } .ext-sh  { color: var(--accent); }
.ext-json { color: #f38020; } .ext-md  { color: #083fa1; }
.ext-sql  { color: #e38c00; } .ext-c   { color: #555555; }
.ext-conf { color: var(--muted); } .ext-doc { color: var(--blue); }
.ext-service { color: var(--purple); }

/* ── Drag ghost ──────────────────────────────────────────────────────────── */
#drag-ghost {
  position: fixed; pointer-events: none; z-index: 9999;
  background: var(--panel); border: 1px solid var(--accent); border-radius: 4px;
  padding: 4px 10px; font-size: 10px; color: var(--accent); letter-spacing: 1px;
  white-space: nowrap; box-shadow: 0 4px 16px rgba(0,0,0,0.6);
  transform: translate(-50%, -110%); display: none;
}

/* ── Context menu ────────────────────────────────────────────────────────── */
#ctx-menu {
  position: fixed; z-index: 9998; background: var(--panel);
  border: 1px solid var(--border); border-radius: 5px;
  padding: 4px 0; min-width: 160px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.6); display: none;
}
.ctx-item { padding: 6px 14px; cursor: pointer; font-size: 10px; color: var(--text);
             letter-spacing: 0.5px; transition: background 0.1s; }
.ctx-item:hover { background: rgba(255,255,255,0.06); color: var(--accent); }
.ctx-item.danger:hover { color: var(--red); }
.ctx-sep { height: 1px; background: var(--border); margin: 3px 0; }
.ctx-submenu-label { padding: 4px 14px; font-size: 8px; color: var(--muted);
                      letter-spacing: 2px; text-transform: uppercase; }

/* ── Inline rename input ─────────────────────────────────────────────────── */
.rename-input {
  background: #0a1018; border: 1px solid var(--accent); border-radius: 2px;
  color: var(--accent); font-family: var(--font); font-size: 9px;
  padding: 1px 6px; outline: none; width: 120px;
}

/* ── Footer ──────────────────────────────────────────────────────────────── */
#ftr { background: var(--panel); border-top: 1px solid var(--border);
       padding: 4px 10px; font-size: 8px; color: var(--muted); letter-spacing: 1px;
       display: flex; gap: 10px; flex-shrink: 0; }
#ftr #ftr-status { flex: 1; }
</style>
</head>
<body>

<div id="hdr">
  <input id="search" type="text" placeholder="Search files...">
  <button id="add-group-btn" title="New group">+</button>
</div>

<div id="tree">
  <div id="tree-inner" style="color:var(--muted);padding:12px;font-size:9px;">Loading...</div>
</div>

<div id="drag-ghost"></div>
<div id="ctx-menu"></div>

<div id="ftr">
  <span id="ftr-status">─</span>
  <span id="ftr-assigned">─ assigned</span>
</div>

<script>
'use strict';

const API = 'api/files.php';

// ── State ──────────────────────────────────────────────────────────────────
let treeData     = { groups: [], group_names: [], sectors: [] };
let allFiles     = [];   // flat list for search
let assignments  = {};   // path → group_name
let dragItem     = null;
let ctxTarget    = null;

// ── Ext → icon ─────────────────────────────────────────────────────────────
const EXT_ICON = {
  py:'🐍', js:'⚡', php:'🐘', sh:'🔧', bash:'🔧', json:'{}', yaml:'📋',
  yml:'📋', toml:'📋', conf:'⚙', ini:'⚙', cfg:'⚙', env:'🔑', md:'📝',
  txt:'📄', sql:'🗄', c:'⚙', h:'⚙', service:'⚙', target:'⚙', jmx:'🎯',
  doc:'📄', default:'📄',
};
function extIcon(ext) { return EXT_ICON[ext] || EXT_ICON.default; }
function extClass(ext) {
  return {'py':'ext-py','js':'ext-js','php':'ext-php','sh':'ext-sh','bash':'ext-sh',
          'json':'ext-json','md':'ext-md','sql':'ext-sql','c':'ext-c','conf':'ext-conf',
          'service':'ext-service','doc':'ext-doc'}[ext] || '';
}

// ── Load from API ──────────────────────────────────────────────────────────
async function loadTree() {
  try {
    const res  = await fetch(API);
    treeData   = await res.json();
    // Build assignment map
    assignments = {};
    (treeData.groups || []).forEach(grp => {
      (grp.children || []).forEach(f => { assignments[f.path] = grp.label; });
    });
    buildAllFiles();
    render();
    updateFooter();
  } catch(e) {
    document.getElementById('tree-inner').textContent = 'API offline — is Apache running?';
  }
}

function buildAllFiles() {
  allFiles = [];
  function walk(node) {
    if (node.type === 'file' || node.type === 'doc') { allFiles.push(node); return; }
    (node.children || []).forEach(walk);
  }
  (treeData.sectors || []).forEach(walk);
}

// ── Render ────────────────────────────────────────────────────────────────
function render(filter = '') {
  const inner = document.getElementById('tree-inner');
  inner.innerHTML = '';

  // Groups first (pinned)
  (treeData.groups || []).forEach(grp => {
    inner.appendChild(buildGroupSection(grp, filter));
  });

  // Sector folders
  (treeData.sectors || []).forEach(sec => {
    inner.appendChild(buildSectorSection(sec, filter));
  });
}

function buildGroupSection(grp, filter) {
  const wrap = document.createElement('div');
  const hdr  = makeHdr(grp.label, '📌', 'group-hdr', grp.children.length);

  // Drop target for drag-assign
  hdr.dataset.group  = grp.label;
  hdr.dataset.isGroup = '1';
  hdr.addEventListener('dragover',  onGroupDragOver);
  hdr.addEventListener('dragleave', onGroupDragLeave);
  hdr.addEventListener('drop',      onGroupDrop);
  hdr.addEventListener('contextmenu', e => showGroupCtx(e, grp.label));

  const children = document.createElement('div');
  children.className = 'section-children';

  let shown = 0;
  (grp.children || []).forEach(f => {
    if (filter && !f.label.toLowerCase().includes(filter)) return;
    children.appendChild(makeFileItem(f, 1, true));
    shown++;
  });

  hdr.querySelector('.badge').textContent = shown;
  wrap.appendChild(hdr);
  wrap.appendChild(children);
  return wrap;
}

function buildSectorSection(sec, filter) {
  const wrap     = document.createElement('div');
  const hdr      = makeHdr(sec.label, sec.icon || '📁', '', 0);
  const children = document.createElement('div');
  children.className = 'section-children';

  let count = 0;
  function renderChildren(nodes, depth, parent) {
    nodes.forEach(node => {
      if (node.type === 'dir') {
        const dirRow = document.createElement('div');
        dirRow.className = 'tree-item';
        dirRow.dataset.depth = depth;
        dirRow.innerHTML = `<span class="dir-toggle">▶</span>
          <span class="item-icon">📁</span>
          <span class="item-name">${esc(node.label)}</span>`;
        const dirChildren = document.createElement('div');
        dirChildren.className = 'dir-children';
        dirRow.querySelector('.dir-toggle').addEventListener('click', e => {
          e.stopPropagation();
          const tog = e.target;
          tog.classList.toggle('open');
          dirChildren.classList.toggle('open');
        });
        if (!filter) { parent.appendChild(dirRow); parent.appendChild(dirChildren); }
        renderChildren(node.children || [], depth + 1, filter ? parent : dirChildren);
      } else {
        if (filter && !node.label.toLowerCase().includes(filter.toLowerCase())) return;
        parent.appendChild(makeFileItem(node, depth));
        count++;
      }
    });
  }

  renderChildren(sec.children || [], 1, children);
  hdr.querySelector('.badge').textContent = count;

  wrap.appendChild(hdr);
  wrap.appendChild(children);
  return wrap;
}

function makeHdr(label, icon, extraClass, count) {
  const hdr  = document.createElement('div');
  hdr.className = `section-hdr ${extraClass}`.trim();
  hdr.innerHTML = `<span class="arrow">▶</span>
    <span style="font-size:12px">${icon}</span>
    <span>${esc(label)}</span>
    <span class="badge">${count}</span>`;
  hdr.addEventListener('click', () => hdr.classList.toggle('open'));
  return hdr;
}

function makeFileItem(node, depth = 1, inGroup = false) {
  const row = document.createElement('div');
  row.className = 'tree-item';
  row.dataset.depth = depth;
  row.dataset.path  = node.path;
  row.dataset.label = node.label;
  row.draggable     = true;

  const assignedGroup = assignments[node.path];
  const extCls        = extClass(node.ext || '');
  const assignedBadge = assignedGroup && !inGroup
    ? `<span class="assigned-badge">${esc(assignedGroup)}</span>` : '';

  row.innerHTML = `
    <span class="item-icon ${extCls}">${extIcon(node.ext || '')}</span>
    <span class="item-name" title="${esc(node.path)}">${esc(node.label)}</span>
    <span class="item-ext ${extCls}">.${esc(node.ext || '')}</span>
    ${assignedBadge}`;

  row.addEventListener('dblclick', () => openFile(node));
  row.addEventListener('contextmenu', e => showFileCtx(e, node, inGroup));
  row.addEventListener('dragstart', e => onFileDragStart(e, node));
  row.addEventListener('dragend',   () => onFileDragEnd(row));

  return row;
}

// ── Drag & drop ────────────────────────────────────────────────────────────
const ghost = document.getElementById('drag-ghost');

function onFileDragStart(e, node) {
  dragItem = node;
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', node.path);
  setTimeout(() => e.target.classList.add('dragging'), 0);
  ghost.textContent = `📌 ${node.label}`;
  ghost.style.display = 'block';
}

function onFileDragEnd(row) {
  dragItem = null;
  row.classList.remove('dragging');
  ghost.style.display = 'none';
  document.querySelectorAll('.drop-target').forEach(el => el.classList.remove('drop-target'));
}

document.addEventListener('dragover', e => {
  e.preventDefault();
  ghost.style.left = e.clientX + 'px';
  ghost.style.top  = e.clientY + 'px';
});

function onGroupDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  e.currentTarget.classList.add('drop-target');
}
function onGroupDragLeave(e) {
  e.currentTarget.classList.remove('drop-target');
}
async function onGroupDrop(e) {
  e.preventDefault();
  e.currentTarget.classList.remove('drop-target');
  if (!dragItem) return;
  const group = e.currentTarget.dataset.group;
  await assignFile(dragItem.path, group);
  toast(`Assigned to "${group}"`);
}

// ── File open ──────────────────────────────────────────────────────────────
function openFile(node) {
  // If running inside Desktop iframe, post message to parent
  if (window.parent !== window) {
    window.parent.postMessage({ type: 'open_file', path: node.path, label: node.label, ext: node.ext }, '*');
  } else {
    // Standalone — just show path
    setStatus(node.path);
  }
}

// ── Context menus ──────────────────────────────────────────────────────────
const ctxMenu = document.getElementById('ctx-menu');

function showFileCtx(e, node, inGroup) {
  e.preventDefault(); e.stopPropagation();
  ctxTarget = node;

  const groupOptions = (treeData.group_names || [])
    .map(g => `<div class="ctx-item" data-assign="${esc(g)}">→ ${esc(g)}</div>`)
    .join('');

  ctxMenu.innerHTML = `
    <div class="ctx-submenu-label">Assign to Group</div>
    ${groupOptions}
    <div class="ctx-item" data-assign="__new__">+ New group…</div>
    ${inGroup ? '<div class="ctx-sep"></div><div class="ctx-item danger" data-action="unassign">Remove from group</div>' : ''}
    <div class="ctx-sep"></div>
    <div class="ctx-item" data-action="copy-path">Copy path</div>
  `;

  positionCtx(e);
  ctxMenu.style.display = 'block';
  ctxMenu.onclick = async ev => {
    const item = ev.target.closest('[data-assign],[data-action]');
    if (!item) return;
    closeCtx();
    if (item.dataset.assign === '__new__') {
      const name = prompt('New group name:');
      if (name?.trim()) await assignFile(node.path, name.trim());
    } else if (item.dataset.assign) {
      await assignFile(node.path, item.dataset.assign);
    } else if (item.dataset.action === 'unassign') {
      await unassignFile(node.path);
    } else if (item.dataset.action === 'copy-path') {
      navigator.clipboard?.writeText(node.path);
      toast('Path copied');
    }
  };
}

function showGroupCtx(e, groupName) {
  e.preventDefault(); e.stopPropagation();
  ctxMenu.innerHTML = `
    <div class="ctx-submenu-label">${esc(groupName)}</div>
    <div class="ctx-item" data-action="rename">Rename group</div>
    <div class="ctx-sep"></div>
    <div class="ctx-item danger" data-action="delete">Delete group</div>
  `;
  positionCtx(e);
  ctxMenu.style.display = 'block';
  ctxMenu.onclick = async ev => {
    const item = ev.target.closest('[data-action]');
    if (!item) return;
    closeCtx();
    if (item.dataset.action === 'rename') {
      const name = prompt('Rename group:', groupName);
      if (name?.trim() && name.trim() !== groupName) await renameGroup(groupName, name.trim());
    } else if (item.dataset.action === 'delete') {
      if (confirm(`Delete group "${groupName}"? Files will be unassigned.`)) await deleteGroup(groupName);
    }
  };
}

function positionCtx(e) {
  ctxMenu.style.left = Math.min(e.clientX, window.innerWidth  - 170) + 'px';
  ctxMenu.style.top  = Math.min(e.clientY, window.innerHeight - 200) + 'px';
}
function closeCtx() { ctxMenu.style.display = 'none'; }
document.addEventListener('click', closeCtx);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeCtx(); });

// ── API calls ──────────────────────────────────────────────────────────────
async function assignFile(path, group) {
  const res  = await fetch(API, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ path, group }) });
  const data = await res.json();
  if (data.ok) { await loadTree(); toast(`→ ${group}`); }
}

async function unassignFile(path) {
  const res  = await fetch(API, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ path, group: null }) });
  const data = await res.json();
  if (data.ok) { await loadTree(); toast('Removed from group'); }
}

async function createGroup(name) {
  const res  = await fetch(API, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ action:'create_group', group: name }) });
  const data = await res.json();
  if (data.ok) { await loadTree(); toast(`Group created: ${name}`); }
}

async function renameGroup(from, to) {
  const res  = await fetch(API, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ action:'rename_group', from, to }) });
  const data = await res.json();
  if (data.ok) { await loadTree(); toast(`Renamed → ${to}`); }
}

async function deleteGroup(group) {
  const res  = await fetch(API, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ action:'delete_group', group }) });
  const data = await res.json();
  if (data.ok) { await loadTree(); toast(`Deleted group: ${group}`); }
}

// ── Search ─────────────────────────────────────────────────────────────────
document.getElementById('search').addEventListener('input', e => {
  render(e.target.value.trim());
});

// ── New group button ───────────────────────────────────────────────────────
document.getElementById('add-group-btn').addEventListener('click', async () => {
  const name = prompt('New group name:');
  if (name?.trim()) await createGroup(name.trim());
});

// ── Helpers ────────────────────────────────────────────────────────────────
function esc(s) { return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function setStatus(msg) { document.getElementById('ftr-status').textContent = msg; }

function updateFooter() {
  const total    = Object.keys(assignments).length;
  const groups   = treeData.group_names?.length || 0;
  document.getElementById('ftr-assigned').textContent = `${total} assigned across ${groups} group(s)`;
}

let toastEl, toastTimer;
function toast(msg) {
  if (!toastEl) {
    toastEl = document.createElement('div');
    toastEl.style.cssText = 'position:fixed;bottom:28px;left:50%;transform:translateX(-50%);'
      + 'background:#0d1117;border:1px solid var(--accent);border-radius:4px;'
      + 'padding:5px 14px;font-size:9px;color:var(--accent);letter-spacing:1px;'
      + 'pointer-events:none;z-index:9999;white-space:nowrap;';
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = msg;
  toastEl.style.opacity = '1';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.style.opacity = '0'; }, 2200);
}

// ── Init ───────────────────────────────────────────────────────────────────
loadTree();
</script>
</body>
</html>
