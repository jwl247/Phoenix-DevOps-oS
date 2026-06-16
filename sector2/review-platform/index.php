<?php
// Phoenix Review Platform — peer review for anything
// Submissions: Phoenix additions, projects, advice, ideas, questions, problems
// Immutable: nothing is edited or deleted. D1 is the permanent record.
// Reviewers earn their seat. Auth required to vote.

$WORKER  = getenv('PHOENIX_WORKER_URL') ?: 'https://packages-worker.phoenix-jwl.workers.dev';
$AUTH    = getenv('PHOENIX_AUTH') ?: '';

$ACTION  = $_GET['action'] ?? 'list';
$FILTER  = $_GET['status'] ?? 'pending';
$VIEW    = $_GET['hex'] ?? '';

function worker($method, $path, $auth, $body = null): array {
    $opts = ['http' => [
        'method'  => $method,
        'header'  => "Authorization: Bearer $auth\r\nContent-Type: application/json\r\n",
        'timeout' => 10,
        'ignore_errors' => true,
    ]];
    if ($body !== null) $opts['http']['content'] = json_encode($body);
    $raw = @file_get_contents('https://packages-worker.phoenix-jwl.workers.dev' . $path,
        false, stream_context_create($opts));
    return $raw ? (json_decode($raw, true) ?? []) : [];
}

// Handle POST form submissions
$msg = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $type = $_POST['action'] ?? '';

    if ($type === 'submit') {
        $sub_type = $_POST['submission_type'] ?? 'general';
        $name     = trim($_POST['name'] ?? '');
        $content  = trim($_POST['content'] ?? '');
        $tags     = trim($_POST['tags'] ?? '');
        $submitter= trim($_POST['submitter'] ?? 'anonymous');
        if ($name && $content) {
            $r = worker('POST', '/review', $AUTH, [
                'name'            => $name,
                'description'     => substr($content, 0, 200),
                'content'         => $content,
                'submission_type' => $sub_type,
                'tags'            => $tags ?: null,
                'submitter'       => $submitter ?: 'anonymous',
            ]);
            $msg = isset($r['ok']) ? "SUBMITTED — #{$r['hex']}" : ('ERROR: ' . ($r['error'] ?? 'unknown'));
        } else {
            $msg = 'ERROR: title and content required';
        }
    }

    if ($type === 'vote') {
        $hex      = $_POST['hex'] ?? '';
        $vote     = $_POST['vote'] ?? '';
        $reviewer = trim($_POST['reviewer'] ?? 'anonymous');
        $notes    = trim($_POST['notes'] ?? '');
        if ($hex && in_array($vote, ['approve','reject','abstain'])) {
            $r = worker('POST', "/review/{$hex}/vote", $AUTH, [
                'vote' => $vote, 'reviewer' => $reviewer ?: 'anonymous', 'notes' => $notes,
            ]);
            $msg = isset($r['status']) ? "VOTE CAST — " . strtoupper($vote) . " — status: " . strtoupper($r['status']) : ('ERROR: ' . ($r['error'] ?? 'unknown'));
        }
    }
}

// Fetch data
$submissions = [];
$single      = null;

if ($VIEW) {
    $single = worker('GET', "/review/" . urlencode($VIEW), $AUTH);
} else {
    $data        = worker('GET', "/review?limit=100&status={$FILTER}", $AUTH);
    $submissions = $data['submissions'] ?? [];
}

$TYPE_LABELS = [
    'phoenix_addition' => 'Phoenix Addition',
    'project'          => 'Project',
    'question'         => 'Question / Advice',
    'idea'             => 'Idea',
    'problem'          => 'Problem',
    'artifact'         => 'Artifact',
    'general'          => 'General',
];
$TYPE_COLORS = [
    'phoenix_addition' => '#00ff88',
    'project'          => '#79c0ff',
    'question'         => '#ffaa00',
    'idea'             => '#bc8cff',
    'problem'          => '#ff6644',
    'artifact'         => '#56d364',
    'general'          => '#8899aa',
];

function type_badge(string $t, array $labels, array $colors): string {
    $label = $labels[$t] ?? strtoupper($t);
    $color = $colors[$t] ?? '#8899aa';
    return "<span class='tbadge' style='border-color:{$color};color:{$color}'>{$label}</span>";
}
function status_badge(string $s): string {
    $map = ['pending'=>'#ffaa00','approved'=>'#00ff88','rejected'=>'#ff3344','revoked'=>'#666'];
    $c = $map[$s] ?? '#888';
    return "<span class='sbadge' style='color:{$c}'>".strtoupper($s)."</span>";
}
function esc(string $s): string { return htmlspecialchars($s, ENT_QUOTES); }
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phoenix // Review Platform</title>
<style>
:root {
  --bg:     #080b0e;
  --panel:  #0d1117;
  --border: #1a2535;
  --accent: #00ff88;
  --text:   #c8d8e8;
  --muted:  #4a5a6a;
  --dim:    #2a3a4a;
  --font:   'Courier New', monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: var(--font);
       font-size: 13px; min-height: 100vh; }

/* Header */
.hdr { background: var(--panel); border-bottom: 2px solid var(--border);
       padding: 14px 24px; display: flex; align-items: center; gap: 20px;
       position: sticky; top: 0; z-index: 100; }
.hdr-title { font-size: 15px; letter-spacing: 3px; color: var(--accent); font-weight: bold; }
.hdr-sub   { color: var(--muted); font-size: 11px; letter-spacing: 1px; }
.hdr-nav   { margin-left: auto; display: flex; gap: 8px; }
.nav-btn   { background: none; border: 1px solid var(--dim); color: var(--muted);
             padding: 5px 14px; font-family: var(--font); font-size: 11px;
             cursor: pointer; letter-spacing: 1px; text-decoration: none; display: inline-block; }
.nav-btn:hover, .nav-btn.active { border-color: var(--accent); color: var(--accent); }

/* Layout */
.layout { display: grid; grid-template-columns: 260px 1fr; min-height: calc(100vh - 57px); }
.sidebar { background: var(--panel); border-right: 1px solid var(--border);
           padding: 20px 16px; }
.main { padding: 20px 24px; }

/* Sidebar */
.sidebar h3 { color: var(--muted); font-size: 10px; letter-spacing: 2px;
              margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.filter-link { display: block; padding: 7px 10px; color: var(--muted); text-decoration: none;
               font-size: 12px; letter-spacing: 1px; border: 1px solid transparent;
               margin-bottom: 3px; }
.filter-link:hover { color: var(--text); border-color: var(--dim); }
.filter-link.active { color: var(--accent); border-color: var(--accent); background: #001a0a; }

.sidebar .divider { border: none; border-top: 1px solid var(--border); margin: 16px 0; }

/* Submit form */
.submit-form { background: var(--panel); border: 1px solid var(--border); padding: 18px; }
.submit-form h3 { color: var(--accent); font-size: 11px; letter-spacing: 2px; margin-bottom: 14px; }
.field { margin-bottom: 10px; }
.field label { display: block; color: var(--muted); font-size: 10px; letter-spacing: 1px;
               margin-bottom: 4px; }
.field input, .field select, .field textarea {
  width: 100%; background: var(--bg); border: 1px solid var(--dim);
  color: var(--text); padding: 7px 10px; font-family: var(--font); font-size: 12px; outline: none; }
.field input:focus, .field select:focus, .field textarea:focus { border-color: var(--accent); }
.field textarea { resize: vertical; min-height: 70px; }
.field select option { background: var(--bg); }
.submit-btn { width: 100%; background: #001a0a; border: 1px solid var(--accent);
              color: var(--accent); padding: 9px; font-family: var(--font);
              font-size: 12px; letter-spacing: 2px; cursor: pointer; }
.submit-btn:hover { background: var(--accent); color: #000; }

/* Message banner */
.msg { padding: 10px 14px; margin-bottom: 16px; font-size: 12px; letter-spacing: 1px;
       border: 1px solid; }
.msg.ok  { border-color: var(--accent); color: var(--accent); background: #001a0a; }
.msg.err { border-color: #ff3344; color: #ff3344; background: #1a0008; }

/* Submissions list */
.section-hdr { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.section-hdr h2 { font-size: 12px; letter-spacing: 2px; color: var(--muted); }
.count-badge { background: var(--dim); color: var(--text); padding: 2px 8px;
               font-size: 11px; letter-spacing: 1px; }

.submission { background: var(--panel); border: 1px solid var(--border);
              margin-bottom: 6px; transition: border-color .15s; }
.submission:hover { border-color: var(--dim); }
.submission.open  { border-color: var(--accent); }

.sub-head { display: flex; align-items: center; gap: 10px; padding: 10px 14px;
            cursor: pointer; }
.sub-title { flex: 1; font-weight: bold; font-size: 13px; color: var(--text);
             overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sub-meta  { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.tbadge    { font-size: 10px; letter-spacing: 1px; padding: 2px 7px; border: 1px solid; }
.sbadge    { font-size: 10px; letter-spacing: 1px; font-weight: bold; }
.sub-by    { color: var(--muted); font-size: 11px; }
.sub-date  { color: var(--muted); font-size: 11px; }
.arrow     { color: var(--muted); font-size: 10px; transition: transform .15s; }
.submission.open .arrow { transform: rotate(90deg); color: var(--accent); }

/* Drawer */
.sub-body  { display: none; padding: 14px 16px; border-top: 1px solid var(--border);
             background: #060809; }
.submission.open .sub-body { display: block; }
.content-block { background: var(--panel); border: 1px solid var(--border);
                 padding: 12px 14px; margin-bottom: 14px; line-height: 1.7;
                 color: var(--text); white-space: pre-wrap; word-break: break-word; }
.tags-line { margin-bottom: 12px; }
.tag { display: inline-block; background: var(--dim); color: var(--muted);
       padding: 2px 8px; font-size: 10px; letter-spacing: 1px; margin-right: 4px; }
.hex-line  { color: var(--muted); font-size: 11px; margin-bottom: 14px; }
.hex-val   { color: var(--accent); }

/* Reviews */
.reviews-hdr { font-size: 10px; letter-spacing: 2px; color: var(--muted);
               margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.review-item { display: flex; gap: 10px; align-items: flex-start; padding: 7px 0;
               border-bottom: 1px solid var(--border); }
.review-item:last-child { border-bottom: none; }
.vote-pill { font-size: 10px; letter-spacing: 1px; padding: 2px 8px; font-weight: bold;
             flex-shrink: 0; }
.vote-approve  { color: #00ff88; border: 1px solid #00ff88; }
.vote-reject   { color: #ff3344; border: 1px solid #ff3344; }
.vote-abstain  { color: #888;    border: 1px solid #444; }
.review-by     { color: var(--muted); font-size: 11px; }
.review-notes  { color: var(--text); font-size: 12px; flex: 1; }

/* Vote form */
.vote-form { background: var(--bg); border: 1px solid var(--border);
             padding: 12px 14px; margin-top: 12px; }
.vote-form h4 { color: var(--muted); font-size: 10px; letter-spacing: 2px; margin-bottom: 10px; }
.vote-row  { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-start; }
.vote-row input { background: var(--panel); border: 1px solid var(--dim);
                  color: var(--text); padding: 6px 10px; font-family: var(--font);
                  font-size: 12px; flex: 1; min-width: 120px; outline: none; }
.vote-row input:focus { border-color: var(--accent); }
.vote-btn { background: transparent; border: 1px solid var(--dim); color: var(--muted);
            padding: 6px 14px; font-family: var(--font); font-size: 11px;
            letter-spacing: 1px; cursor: pointer; }
.vote-btn.approve:hover { border-color: #00ff88; color: #00ff88; }
.vote-btn.reject:hover  { border-color: #ff3344; color: #ff3344; }
.vote-btn.abstain:hover { border-color: #888; color: #888; }

.empty { color: var(--muted); text-align: center; padding: 48px; letter-spacing: 2px; }

#toast { position: fixed; bottom: 20px; right: 20px; background: var(--accent);
         color: #000; padding: 8px 16px; font-size: 12px; letter-spacing: 1px;
         opacity: 0; transition: opacity .2s; pointer-events: none; }
#toast.show { opacity: 1; }
</style>
</head>
<body>

<div class="hdr">
  <div>
    <div class="hdr-title">PHOENIX // REVIEW PLATFORM</div>
    <div class="hdr-sub">PEER REVIEW — IMMUTABLE — EARN YOUR SEAT</div>
  </div>
  <nav class="hdr-nav">
    <a class="nav-btn <?= !$VIEW ? 'active' : '' ?>" href="?status=pending">QUEUE</a>
    <a class="nav-btn" href="?status=approved">APPROVED</a>
    <a class="nav-btn" href="?action=submit">+ SUBMIT</a>
  </nav>
</div>

<div class="layout">

<!-- Sidebar -->
<aside class="sidebar">
  <h3>FILTER</h3>
  <a class="filter-link <?= $FILTER==='pending'&&!$VIEW ? 'active' : '' ?>" href="?status=pending">PENDING</a>
  <a class="filter-link <?= $FILTER==='approved'&&!$VIEW ? 'active' : '' ?>" href="?status=approved">APPROVED</a>
  <a class="filter-link <?= $FILTER==='rejected'&&!$VIEW ? 'active' : '' ?>" href="?status=rejected">REJECTED</a>
  <a class="filter-link <?= $FILTER==='all'&&!$VIEW ? 'active' : '' ?>" href="?status=all">ALL</a>

  <hr class="divider">
  <h3>SUBMIT ANYTHING</h3>

  <form class="submit-form" method="POST" action="">
    <input type="hidden" name="action" value="submit">
    <div class="field">
      <label>TYPE</label>
      <select name="submission_type">
        <option value="phoenix_addition">Phoenix Addition</option>
        <option value="project">Project</option>
        <option value="question" selected>Question / Advice</option>
        <option value="idea">Idea</option>
        <option value="problem">Problem</option>
        <option value="general">General</option>
      </select>
    </div>
    <div class="field">
      <label>TITLE</label>
      <input type="text" name="name" placeholder="What are you submitting?" required>
    </div>
    <div class="field">
      <label>CONTENT</label>
      <textarea name="content" placeholder="Describe it fully. This is permanent." required></textarea>
    </div>
    <div class="field">
      <label>TAGS (comma separated)</label>
      <input type="text" name="tags" placeholder="phoenix, kernel, advice...">
    </div>
    <div class="field">
      <label>YOUR HANDLE</label>
      <input type="text" name="submitter" placeholder="anonymous">
    </div>
    <button class="submit-btn" type="submit">SUBMIT FOR REVIEW</button>
  </form>
</aside>

<!-- Main -->
<main class="main">

<?php if ($msg): ?>
  <div class="msg <?= str_starts_with($msg,'ERROR') ? 'err' : 'ok' ?>"><?= esc($msg) ?></div>
<?php endif; ?>

<?php if ($single): ?>
  <!-- Single submission view -->
  <?php $s = $single['submission'] ?? []; $reviews = $single['reviews'] ?? []; ?>
  <div class="section-hdr">
    <h2>SUBMISSION</h2>
    <a href="?status=<?= $FILTER ?>" class="nav-btn">← BACK</a>
  </div>
  <div class="submission open">
    <div class="sub-head">
      <span class="sub-title"><?= esc($s['name'] ?? '') ?></span>
      <span class="sub-meta">
        <?= type_badge($s['submission_type'] ?? 'general', $TYPE_LABELS, $TYPE_COLORS) ?>
        <?= status_badge($s['status'] ?? 'pending') ?>
        <span class="sub-by"><?= esc($s['submitter'] ?? 'anonymous') ?></span>
      </span>
    </div>
    <div class="sub-body" style="display:block">
      <?php if ($s['tags']): ?>
      <div class="tags-line">
        <?php foreach (explode(',', $s['tags']) as $tag): ?>
          <span class="tag"><?= esc(trim($tag)) ?></span>
        <?php endforeach; ?>
      </div>
      <?php endif; ?>
      <div class="content-block"><?= esc($s['content'] ?: $s['description'] ?? '') ?></div>
      <div class="hex-line">TAV: <span class="hex-val"><?= esc($s['hex'] ?? '') ?></span>
        &nbsp;·&nbsp; <?= esc(substr($s['submitted_at'] ?? '', 0, 16)) ?></div>

      <!-- Reviews -->
      <?php if ($reviews): ?>
      <div class="reviews-hdr">REVIEWS (<?= count($reviews) ?>)</div>
      <?php foreach ($reviews as $r): ?>
      <div class="review-item">
        <span class="vote-pill vote-<?= esc($r['vote']) ?>"><?= strtoupper(esc($r['vote'])) ?></span>
        <span class="review-by"><?= esc($r['reviewer'] ?? 'anonymous') ?></span>
        <span class="review-notes"><?= esc($r['notes'] ?? '') ?></span>
      </div>
      <?php endforeach; ?>
      <?php else: ?>
      <div style="color:var(--muted);font-size:12px;margin-bottom:12px">No reviews yet.</div>
      <?php endif; ?>

      <!-- Vote form -->
      <?php if (($s['status'] ?? '') === 'pending'): ?>
      <form class="vote-form" method="POST" action="">
        <input type="hidden" name="action" value="vote">
        <input type="hidden" name="hex" value="<?= esc($s['hex'] ?? '') ?>">
        <h4>CAST YOUR REVIEW</h4>
        <div class="vote-row">
          <input type="text" name="reviewer" placeholder="your handle">
          <input type="text" name="notes" placeholder="notes (optional)" style="flex:2">
          <button class="vote-btn approve" name="vote" value="approve" type="submit">APPROVE</button>
          <button class="vote-btn reject"  name="vote" value="reject"  type="submit">REJECT</button>
          <button class="vote-btn abstain" name="vote" value="abstain" type="submit">ABSTAIN</button>
        </div>
      </form>
      <?php endif; ?>
    </div>
  </div>

<?php else: ?>
  <!-- Submission list -->
  <div class="section-hdr">
    <h2><?= strtoupper($FILTER) ?> SUBMISSIONS</h2>
    <span class="count-badge"><?= count($submissions) ?></span>
  </div>

  <?php if (empty($submissions)): ?>
    <div class="empty">NO <?= strtoupper($FILTER) ?> SUBMISSIONS</div>
  <?php else: ?>
    <?php foreach ($submissions as $i => $s): ?>
    <div class="submission" id="s<?= $i ?>">
      <div class="sub-head" onclick="open_sub(<?= $i ?>, '<?= esc($s['hex'] ?? '') ?>')">
        <span class="sub-title"><?= esc($s['name'] ?? '') ?></span>
        <span class="sub-meta">
          <?= type_badge($s['submission_type'] ?? 'general', $TYPE_LABELS, $TYPE_COLORS) ?>
          <?= status_badge($s['status'] ?? 'pending') ?>
          <span class="sub-by"><?= esc($s['submitter'] ?? '') ?></span>
          <span class="sub-date"><?= esc(substr($s['submitted_at'] ?? '', 0, 10)) ?></span>
        </span>
        <span class="arrow">&#9654;</span>
      </div>
      <div class="sub-body" id="sb<?= $i ?>">
        <div style="color:var(--muted);font-size:12px">Loading...</div>
      </div>
    </div>
    <?php endforeach; ?>
  <?php endif; ?>
<?php endif; ?>

</main>
</div>

<div id="toast"></div>

<script>
function open_sub(i, hex) {
  const el = document.getElementById('s' + i);
  const body = document.getElementById('sb' + i);
  if (el.classList.contains('open')) { el.classList.remove('open'); return; }
  el.classList.add('open');
  window.location.href = '?hex=' + encodeURIComponent(hex) + '&status=<?= $FILTER ?>';
}
</script>
</body>
</html>
