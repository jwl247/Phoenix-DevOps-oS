<?php
// glossary.php — Phoenix Glossary
// TOC and index of clonepool + D1
// Serves at /glossary/ on phoenix-ext Apache

$WORKER   = getenv('PHOENIX_WORKER_URL') ?: 'https://packages-worker.phoenix-jwl.workers.dev';
$AUTH     = getenv('PHOENIX_AUTH') ?: '';
$LIMIT    = intval($_GET['limit'] ?? 200);
$SEARCH   = trim($_GET['q'] ?? '');
$PAGE     = max(1, intval($_GET['page'] ?? 1));
$OFFSET   = ($PAGE - 1) * $LIMIT;

function worker_get(string $path, string $worker, string $auth): array {
    $ctx = stream_context_create(['http' => [
        'method'  => 'GET',
        'header'  => "Authorization: Bearer $auth\r\nContent-Type: application/json\r\n",
        'timeout' => 10,
        'ignore_errors' => true,
    ]]);
    $raw = @file_get_contents($worker . $path, false, $ctx);
    return $raw ? (json_decode($raw, true) ?? []) : [];
}

$url = "/glossary?limit={$LIMIT}&offset={$OFFSET}";
if ($SEARCH) $url .= '&search=' . urlencode($SEARCH);
$data    = worker_get($url, $WORKER, $AUTH);
$entries = $data['glossary'] ?? [];
$count   = $data['count'] ?? count($entries);

function state_led(string $state): string {
    $colors = ['white' => '#e8e8e8', 'grey' => '#666', 'black' => '#111', 'green' => '#00ff88'];
    $color  = $colors[$state] ?? '#444';
    $label  = strtoupper($state ?: 'UNK');
    return "<span class='led' style='background:{$color}' title='{$label}'></span>";
}

function fmt_size(int $bytes): string {
    if ($bytes < 1024) return "{$bytes} B";
    if ($bytes < 1048576) return round($bytes/1024, 1) . " KB";
    return round($bytes/1048576, 1) . " MB";
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phoenix Glossary</title>
<style>
  :root {
    --bg:      #0a0c0f;
    --panel:   #0f1318;
    --border:  #1a2030;
    --accent:  #00ff88;
    --dim:     #3a4a5a;
    --text:    #c8d8e8;
    --muted:   #556677;
    --red:     #ff3344;
    --amber:   #ffaa00;
    --font:    'Courier New', monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: var(--font);
         font-size: 13px; min-height: 100vh; }

  /* ── Header ── */
  .hdr {
    background: var(--panel); border-bottom: 1px solid var(--border);
    padding: 14px 20px; display: flex; align-items: center; gap: 16px;
    position: sticky; top: 0; z-index: 100;
  }
  .hdr-title { font-size: 15px; letter-spacing: 3px; color: var(--accent); font-weight: bold; }
  .hdr-sub   { color: var(--muted); font-size: 11px; letter-spacing: 1px; }
  .hdr-count { margin-left: auto; color: var(--muted); font-size: 11px; }

  /* ── Search bar ── */
  .search-bar {
    padding: 10px 20px; background: var(--panel);
    border-bottom: 1px solid var(--border);
  }
  .search-bar form { display: flex; gap: 8px; }
  .search-bar input {
    flex: 1; background: var(--bg); border: 1px solid var(--dim);
    color: var(--text); padding: 7px 12px; font-family: var(--font);
    font-size: 13px; outline: none;
  }
  .search-bar input:focus { border-color: var(--accent); }
  .btn {
    background: transparent; border: 1px solid var(--dim); color: var(--text);
    padding: 7px 16px; font-family: var(--font); font-size: 12px;
    cursor: pointer; letter-spacing: 1px; transition: border-color .15s, color .15s;
  }
  .btn:hover  { border-color: var(--accent); color: var(--accent); }
  .btn-clear  { border-color: var(--red); color: var(--red); }
  .btn-clear:hover { background: var(--red); color: #000; }

  /* ── Entry drawer ── */
  .entries { padding: 12px 20px; display: flex; flex-direction: column; gap: 4px; }
  .entry {
    background: var(--panel); border: 1px solid var(--border);
    transition: border-color .15s;
  }
  .entry:hover { border-color: var(--dim); }
  .entry.open  { border-color: var(--accent); }

  .entry-head {
    display: flex; align-items: center; gap: 10px; padding: 9px 12px;
    cursor: pointer; user-select: none;
  }
  .led {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
    box-shadow: 0 0 4px currentColor;
  }
  .entry-name  { color: var(--text); font-weight: bold; flex: 1; min-width: 0;
                 overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .entry-b58   { color: var(--accent); font-size: 11px; letter-spacing: 1px; flex-shrink: 0; }
  .entry-size  { color: var(--muted); font-size: 11px; width: 60px; text-align: right; flex-shrink: 0; }
  .entry-date  { color: var(--muted); font-size: 11px; width: 130px; text-align: right; flex-shrink: 0; }
  .drawer-icon { color: var(--dim); font-size: 10px; flex-shrink: 0; transition: transform .15s; }
  .entry.open .drawer-icon { transform: rotate(90deg); color: var(--accent); }

  /* ── Drawer body ── */
  .entry-body {
    display: none; padding: 12px 14px 14px; border-top: 1px solid var(--border);
    background: #080b0e;
  }
  .entry.open .entry-body { display: block; }

  .meta-grid {
    display: grid; grid-template-columns: 140px 1fr; gap: 4px 12px;
    margin-bottom: 12px;
  }
  .meta-key   { color: var(--muted); font-size: 11px; padding-top: 1px; }
  .meta-val   { color: var(--text); font-size: 12px; word-break: break-all; }
  .meta-val.accent { color: var(--accent); }

  .desc-block {
    background: var(--panel); border: 1px solid var(--border);
    padding: 8px 10px; color: var(--muted); font-size: 12px;
    margin-bottom: 12px; line-height: 1.5;
  }

  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .act-btn {
    background: transparent; border: 1px solid var(--dim); color: var(--muted);
    padding: 5px 12px; font-family: var(--font); font-size: 11px;
    cursor: pointer; letter-spacing: 1px; transition: all .15s;
  }
  .act-btn:hover { border-color: var(--accent); color: var(--accent); }

  /* ── Empty / status ── */
  .empty { color: var(--muted); text-align: center; padding: 60px 20px; letter-spacing: 2px; }

  /* ── Pagination ── */
  .pager {
    display: flex; justify-content: center; gap: 8px;
    padding: 20px; border-top: 1px solid var(--border);
  }
  .pager a {
    color: var(--muted); text-decoration: none; padding: 5px 12px;
    border: 1px solid var(--border); font-size: 12px; letter-spacing: 1px;
  }
  .pager a:hover { border-color: var(--accent); color: var(--accent); }
  .pager .cur   { border-color: var(--accent); color: var(--accent); }

  /* ── Copy toast ── */
  #toast {
    position: fixed; bottom: 24px; right: 24px; background: var(--accent);
    color: #000; padding: 8px 16px; font-size: 12px; letter-spacing: 1px;
    opacity: 0; transition: opacity .2s; pointer-events: none;
  }
  #toast.show { opacity: 1; }
</style>
</head>
<body>

<div class="hdr">
  <div>
    <div class="hdr-title">PHOENIX // GLOSSARY</div>
    <div class="hdr-sub">CLONEPOOL INDEX &amp; D1 REGISTRY</div>
  </div>
  <div class="hdr-count">
    <?= $SEARCH ? "SEARCH: &ldquo;{$SEARCH}&rdquo; &mdash; " : '' ?>
    <?= $count ?> ENTRIES
    <?= $AUTH ? '' : ' &mdash; <span style="color:var(--red)">NO AUTH</span>' ?>
  </div>
</div>

<div class="search-bar">
  <form method="GET" action="">
    <input type="text" name="q" placeholder="SEARCH name, hex, description..." value="<?= htmlspecialchars($SEARCH) ?>">
    <button class="btn" type="submit">SEARCH</button>
    <?php if ($SEARCH): ?>
      <a href="?" class="btn btn-clear">CLEAR</a>
    <?php endif; ?>
  </form>
</div>

<div class="entries">
<?php if (empty($entries)): ?>
  <div class="empty">NO ENTRIES<?= $SEARCH ? " MATCHING &ldquo;{$SEARCH}&rdquo;" : ' IN REGISTRY' ?></div>
<?php else: ?>
  <?php foreach ($entries as $i => $e): ?>
  <?php
    $hex  = $e['hex']  ?? '';
    $b58  = $e['b58']  ?? '';
    $name = $e['name'] ?? 'unknown';
    $desc = $e['description'] ?? '';
    $state= $e['state'] ?? 'white';
    $size = intval($e['size'] ?? 0);
    $date = $e['intaked_at'] ?? '';
    $ver  = $e['version'] ?? '';
    $plat = $e['platform'] ?? '';
    $back = $e['backend'] ?? '';
    $path = $e['pool_path'] ?? '';
    $cat  = $e['category_hex'] ?? '';
  ?>
  <div class="entry" id="e<?= $i ?>">
    <div class="entry-head" onclick="toggle(<?= $i ?>)">
      <?= state_led($state) ?>
      <span class="entry-name"><?= htmlspecialchars($name) ?></span>
      <span class="entry-b58"><?= htmlspecialchars($b58) ?></span>
      <span class="entry-size"><?= $size ? fmt_size($size) : '' ?></span>
      <span class="entry-date"><?= htmlspecialchars(substr($date, 0, 16)) ?></span>
      <span class="drawer-icon">&#9654;</span>
    </div>
    <div class="entry-body">
      <?php if ($desc): ?>
      <div class="desc-block"><?= htmlspecialchars($desc) ?></div>
      <?php endif; ?>
      <div class="meta-grid">
        <span class="meta-key">TAV HEX</span>
        <span class="meta-val accent"><?= htmlspecialchars($hex) ?></span>
        <span class="meta-key">TAV B58</span>
        <span class="meta-val accent"><?= htmlspecialchars($b58) ?></span>
        <?php if ($ver): ?>
        <span class="meta-key">VERSION</span>
        <span class="meta-val"><?= htmlspecialchars($ver) ?></span>
        <?php endif; ?>
        <?php if ($plat): ?>
        <span class="meta-key">PLATFORM</span>
        <span class="meta-val"><?= htmlspecialchars($plat) ?></span>
        <?php endif; ?>
        <?php if ($back): ?>
        <span class="meta-key">BACKEND</span>
        <span class="meta-val"><?= htmlspecialchars($back) ?></span>
        <?php endif; ?>
        <span class="meta-key">STATE</span>
        <span class="meta-val"><?= strtoupper($state) ?></span>
        <span class="meta-key">SIZE</span>
        <span class="meta-val"><?= $size ? fmt_size($size) . " ({$size} bytes)" : 'unknown' ?></span>
        <span class="meta-key">INTAKED</span>
        <span class="meta-val"><?= htmlspecialchars($date) ?></span>
        <?php if ($path): ?>
        <span class="meta-key">POOL PATH</span>
        <span class="meta-val"><?= htmlspecialchars($path) ?></span>
        <?php endif; ?>
        <?php if ($cat): ?>
        <span class="meta-key">CATEGORY</span>
        <span class="meta-val"><?= htmlspecialchars($cat) ?></span>
        <?php endif; ?>
      </div>
      <div class="actions">
        <button class="act-btn" onclick="copy('<?= htmlspecialchars($b58) ?>')">COPY B58</button>
        <button class="act-btn" onclick="copy('<?= htmlspecialchars($hex) ?>')">COPY HEX</button>
        <button class="act-btn" onclick="copy('lol <?= htmlspecialchars($name) ?>.lol')">LOL PULL CMD</button>
        <?php if ($path): ?>
        <button class="act-btn" onclick="copy('<?= htmlspecialchars($path) ?>')">COPY PATH</button>
        <?php endif; ?>
      </div>
    </div>
  </div>
  <?php endforeach; ?>
<?php endif; ?>
</div>

<?php if ($count > $LIMIT): ?>
<div class="pager">
  <?php if ($PAGE > 1): ?>
    <a href="?page=<?= $PAGE-1 ?>&limit=<?= $LIMIT ?>&q=<?= urlencode($SEARCH) ?>">&#9664; PREV</a>
  <?php endif; ?>
  <span class="cur">PAGE <?= $PAGE ?></span>
  <?php if ($OFFSET + $LIMIT < $count): ?>
    <a href="?page=<?= $PAGE+1 ?>&limit=<?= $LIMIT ?>&q=<?= urlencode($SEARCH) ?>">NEXT &#9654;</a>
  <?php endif; ?>
</div>
<?php endif; ?>

<div id="toast"></div>

<script>
function toggle(i) {
  const el = document.getElementById('e' + i);
  el.classList.toggle('open');
}
function copy(txt) {
  navigator.clipboard.writeText(txt).then(() => {
    const t = document.getElementById('toast');
    t.textContent = 'COPIED: ' + txt.substring(0, 40) + (txt.length > 40 ? '...' : '');
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 1800);
  });
}
</script>
</body>
</html>
