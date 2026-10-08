"""jarvis_tools.py — Jarvis's hands. They run HERE (PBMII, the caller), never on pbmIII.
Phoenix DevOps OS | jwl247 | GPL v3

Jerry 2026-10-08: "you are the system and y'all are my helpers, but Jarvis brings you shit to
authenticate and get your permission". pbmIII stays network-locked (openjarvis IPAddressDeny=any):
Jarvis asks for a tool with ONE line, `TOOL: name {json}`, and bin/jarvis runs it on this machine.

Tiers (CLAUDE.md "the interaction model"):
  base     read-only - runs without asking (Atlas, the pool's catalog, Phoenix status, commands, time)
  request  anything that would change the world - NEVER run here. Written to the request queue
           (~/.phoenix/jarvis/requests.jsonl) for Claude to review; extreme ones go on to Jerry.
"""
import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

WORKER = os.environ.get("PHOENIX_WORKER_URL", "https://packages-worker.phoenix-jwl.workers.dev").rstrip("/")
QUEUE = Path.home() / ".phoenix" / "jarvis" / "requests.jsonl"
MAX_OUT = 1500          # characters of tool output handed back to him (his ask is capped at 4000)
TOOL_RE = re.compile(r"^\s*TOOL:\s*([a-z_]+)\s*(\{.*\})?\s*$", re.M)


def _headers() -> dict:
    h = {"User-Agent": "phoenix-jarvis-hands"}
    if os.environ.get("PHOENIX_AUTH"):
        h["Authorization"] = f"Bearer {os.environ['PHOENIX_AUTH']}"
    if os.environ.get("CF_ACCESS_CLIENT_ID") and os.environ.get("CF_ACCESS_CLIENT_SECRET"):
        h["CF-Access-Client-Id"] = os.environ["CF_ACCESS_CLIENT_ID"]
        h["CF-Access-Client-Secret"] = os.environ["CF_ACCESS_CLIENT_SECRET"]
    return h


def _get(path: str, timeout: float = 20) -> dict:
    req = urllib.request.Request(WORKER + path, headers=_headers())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if "json" not in (r.headers.get("Content-Type") or ""):
            raise ValueError("Phoenix answered with a login page - the Cloudflare Access keys are missing here")
        return json.loads(r.read())


def _short(text: str, n: int = 160) -> str:
    """Shorten at a word boundary, never inside a word or path: cutting 'rotate-phoenix-auth.sh' to
    '...auth.s…' made him invent 'rotate-phoenix-auth.scm' (2026-10-08)."""
    text = " ".join(str(text or "").split())
    if len(text) <= n:
        return text
    cut = text.rfind(" ", 0, n)
    return (text[:cut] if cut > n // 2 else text[:n]).rstrip(" ,;:") + " ..."


# ── base tier: read-only ──────────────────────────────────────────────────────

def atlas_find(term: str = "") -> str:
    """Where is something in Phoenix? Searches Atlas (the map of every component) by words."""
    if not term:
        return "atlas_find needs {\"term\": \"words\"}"
    hits = _get(f"/connections?q={urllib.parse.quote(term[:48])}").get("connections") or []
    if not hits:
        return f"Atlas has nothing for '{term}'."
    return "\n".join(f"- {h.get('path')}: {_short(h.get('description'), 260)}" for h in hits[:5])


def atlas_near(term: str = "") -> str:
    """What does a component connect to? Atlas's documented connections around it."""
    if not term:
        return "atlas_near needs {\"term\": \"component\"}"
    r = _get(f"/connections/{urllib.parse.quote(term[:48], safe='')}/related")
    c = r.get("center") or {}
    lines = [f"{c.get('path')}: {_short(c.get('description'), 220)}"]
    for n in (r.get("related") or [])[:8]:
        if n.get("via") in ("edge", "near", "area"):
            lines.append(f"  [{n.get('via')}] {n.get('path')}: {_short(n.get('description'), 120)}")
    return "\n".join(lines)


def pool_find(name: str = "") -> str:
    """Is a file in Phoenix's clone pool? Searches the pool's catalog by name (no file bytes)."""
    if not name:
        return "pool_find needs {\"name\": \"file name\"}"
    if len(name.encode()) > 48:
        return "name too long to search; use a shorter part of it"
    rows = _get(f"/search?q={urllib.parse.quote(name)}").get("clonepool") or []
    if not rows:
        return f"Nothing named like '{name}' in the pool."
    return "\n".join(f"- {r.get('name')} {('v' + str(r.get('version')).lstrip('v')) if r.get('version') else '(version not listed)'} (tier {r.get('tier')})" for r in rows[:8])


def phoenix_status() -> str:
    """Is Phoenix's kernel up on Jerry's PC, and how many suits are in the closet?"""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=4) as r:
            ok = json.loads(r.read()).get("ok")
    except Exception:
        return "The Phoenix kernel on Jerry's PC is DOWN (no answer on 8765). Fix: usys start"
    out = ["The Phoenix kernel on Jerry's PC is up."]
    try:
        tok = (Path.home() / ".phoenix" / "genie" / "control.token").read_text().strip()
        req = urllib.request.Request("http://127.0.0.1:8766/kernel", headers={"X-Genie-Token": tok})
        with urllib.request.urlopen(req, timeout=4) as r:
            k = json.loads(r.read())
        lib = k.get("library") or {}
        out.append(f"Closet: {lib.get('suit_count')} suits; imported: {', '.join(lib.get('imported') or []) or 'none'}.")
    except Exception:
        pass
    return " ".join(out) if ok else "The kernel answered but says it is not OK."


def commands() -> str:
    """The easy Phoenix commands (one word after usys) and what each does."""
    return ("TO RUN A SUIT: usys import <suit>.\n"
            "TO RUN AN APP, A GAME OR A VM: usys run <name>.\n"
            "TO PUT A SUIT INTO PHOENIX: usys intakeS <file>. ANY OTHER FILE OR FOLDER: usys intakeC <file|folder>.\n"
            "TO GET A COPY OUT: usys get <name>. TO OPEN A FILE: usys open <file>.\n"
            "THE SUITS IN THE CLOSET: usys closet. HEALTH: usys status. KERNEL ON/OFF: usys start / usys stop. ITS LOG: usys log.\n"
            "GO TO A HIGHLIGHTED PATH: usys jump (or g). ALL OF THEM: usys help.\n"
            "Each is also a button on the Phoenix Console (the bird in the tray), plus ROTATE, DOCKS, GLOSSARY, SUITS.")


def time_now() -> str:
    """The date and time on Jerry's PC."""
    return dt.datetime.now().strftime("%A %B %d, %Y, %I:%M %p")


# ── his learning program (Jerry 10/8: "arts and crafts and pink ... we are remodeling, paint schemes") ──
LESSONS = Path(__file__).resolve().parent / "lessons"
_STOP = {"the", "and", "for", "with", "what", "how", "a", "an", "of", "to", "in", "on", "is", "are", "my", "me", "do", "can", "you", "i",
         "it", "its", "this", "that", "be", "was", "were", "there", "where", "when", "who", "why", "which", "give", "tell",
         "suggest", "about", "some", "any", "your", "our", "we", "us", "should", "would", "could", "will", "get", "make",
         "please", "one", "two", "sentence", "sentences", "short", "briefly", "right", "now", "today"}


def _sections():
    for f in sorted(LESSONS.glob("*.md")):
        title, head, body = f.stem, "", []
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                if head:
                    yield title, head, " ".join(body)
                head, body = line[3:].strip(), []
            elif line.startswith("# "):
                title = line[2:].strip()
            elif line.strip():
                body.append(line.strip())
        if head:
            yield title, head, " ".join(body)


def lesson_hint(question: str, min_score: float = 2.5) -> str:
    """The best lesson section for a question, only when it clearly matches (bin/jarvis hands it to him
    up front, because even the 8B skipped looking things up - 'bounding overwatch', 2026-10-08)."""
    ranked = _rank_lessons(question)
    if not ranked:
        return ""
    s, t, h, b, cover, matched = ranked[0]
    # Only when most of the question is about that section, and more than one word agrees: one rare
    # word ("rotate-KEY" -> key terrain, "what DAY" -> times of day) is not a match.
    if s < min_score or cover < 0.40 or matched < 2:
        return ""
    # The one sentence that answers best goes first: given the whole Finishes section, the 8B still
    # answered "Eggshell" for a bathroom when the lesson says satin (2026-10-08).
    qwords = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if w not in _STOP and len(w) > 2}
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", b) if x.strip()]
    def hits(x):
        xl = x.lower()
        return sum(1 for w in qwords if re.search(r"\b" + re.escape(w[:-1] if w.endswith("s") and len(w) > 3 else w), xl))
    best = max(sentences, key=hits) if sentences else ""
    lead = f"MOST RELEVANT: {best}\n" if best and hits(best) >= 1 else ""
    return f"{lead}[{t} - {h}] {b}"


def lesson_find(topic: str = "") -> str:
    """Search Jarvis's lessons (crafts, paint schemes, remodeling, color theory, design, game art, tactics)."""
    ranked = _rank_lessons(topic)
    if ranked is None:
        return "lesson_find needs {\"topic\": \"words\"}. Lessons: " + ", ".join(f.stem for f in sorted(LESSONS.glob("*.md")))
    if not ranked:
        return f"No lesson covers '{topic}'. Lessons: " + ", ".join(f.stem for f in sorted(LESSONS.glob("*.md")))
    return "\n\n".join(f"[{r[1]} - {r[2]}] {r[3]}" for r in ranked[:2])


def _rank_lessons(topic: str):
    """[(score, title, heading, body)] best first; None when the topic has no usable words."""
    words = [w for w in re.findall(r"[a-z0-9]+", (topic or "").lower()) if w not in _STOP and len(w) > 1]
    if not words:
        return None
    # Rank by how many DIFFERENT question words a section covers (heading counts double), not by how
    # often one word repeats - "pink paint scheme" got the undertones section (pink x12) over the
    # "Scheme: ..." sections, and "easy craft" got techniques over "Easy projects" (2026-10-08 eval).
    # Rare words count more than common ones (IDF): "bathroom", "sand", "lead" decide; "paint" is everywhere.
    import math
    stems = [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words]
    secs = list(_sections())
    def has(text, w):
        return re.search(r"\b" + re.escape(w), text) is not None
    idf = {w: math.log((len(secs) + 1) / (1 + sum(1 for _, h, b in secs if has((h + " " + b).lower(), w)))) + 0.1
           for w in set(stems)}
    total = sum(idf[w] * 2.0 for w in set(stems)) or 1.0
    scored = []
    for title, head, body in secs:
        h, b = head.lower(), body.lower()
        s = sum(idf[w] * (2.0 if has(h, w) else 1.0 if has(b, w) else 0.0) for w in set(stems))
        if s > 0:
            matched = sum(1 for w in set(stems) if has(h, w) or has(b, w))
            scored.append((s, title, head, body, s / total, matched))
    scored.sort(key=lambda x: -x[0])
    return scored


def _num(v, default: float) -> float:
    m = re.search(r"\d+(?:\.\d+)?", str(v or ""))
    return float(m.group()) if m else default


def paint_calc(length: str = "", width: str = "", height: str = "8", doors: str = "1", windows: str = "1", coats: str = "2") -> str:
    """How many gallons of wall paint a room needs (feet). Exact math so he never guesses numbers."""
    L, W = _num(length, 0), _num(width, 0)
    if not L or not W:
        return "paint_calc needs the room size in feet: {\"length\": \"12\", \"width\": \"14\", \"height\": \"8\", \"doors\": \"1\", \"windows\": \"2\", \"coats\": \"2\"}"
    H, D, Wn, C = _num(height, 8), _num(doors, 1), _num(windows, 1), _num(coats, 2)
    wall = 2 * (L + W) * H - 20 * D - 15 * Wn
    total = max(wall, 0) * C
    gallons = total / 350
    ceiling = L * W / 350
    import math
    return (f"Room {L:g} x {W:g} ft, {H:g} ft walls, {D:g} door(s), {Wn:g} window(s): {wall:.0f} sq ft of wall. "
            f"{C:g} coats = {total:.0f} sq ft = {gallons:.2f} gallons -> buy {math.ceil(gallons)} gallon(s) of wall paint. "
            f"The ceiling ({L * W:.0f} sq ft) needs {ceiling * C:.2f} gallons for {C:g} coats -> {math.ceil(ceiling * C)} gallon(s) of ceiling paint. "
            "(1 gallon covers about 350 sq ft per coat; add primer if going dark to light.)")


# ── request tier: never run here ──────────────────────────────────────────────

def request(action: str = "", why: str = "") -> str:
    """Ask Claude to do something that changes the world (run, install, send, delete, change a file...)."""
    if not action:
        return "request needs {\"action\": \"what to do\", \"why\": \"reason\"}"
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    rec = {"at": dt.datetime.now().isoformat(timespec="seconds"), "action": _short(action, 300), "why": _short(why, 300),
           "status": "waiting for Claude"}
    with QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return "Written to Claude's request queue. Nothing was done; Claude reviews it, and anything extreme goes to Jerry."


BASE = {"atlas_find": atlas_find, "atlas_near": atlas_near, "pool_find": pool_find,
        "phoenix_status": phoenix_status, "commands": commands, "time_now": time_now,
        "lesson_find": lesson_find, "paint_calc": paint_calc}
REQUEST = {"request": request}


def catalog() -> str:
    """The tool list Jarvis sees with every ask."""
    lines = ["TOOLS you can use (Jerry's PC runs them for you). To use one, reply with ONLY one line:",
             'TOOL: name {"arg": "value"}',
             "then wait - the result comes back to you. Use a tool when the answer depends on Phoenix facts.",
             "- atlas_find {\"term\": \"words\"}: where something is in Phoenix",
             "- atlas_near {\"term\": \"component\"}: what a component connects to",
             "- pool_find {\"name\": \"file\"}: is a Phoenix file in the clone pool (only Phoenix files, not stores or products)",
             "- phoenix_status {}: is the Phoenix kernel up",
             "- commands {}: the usys commands and Console buttons",
             "- time_now {}: today's date and time",
             "- lesson_find {\"topic\": \"words\"}: your lessons - arts and crafts, paint schemes for the remodel (pink!), painting and remodel how-to, color theory, graphic design, game art and game UI, military tactics (for the game, Sacrifice)",
             "- paint_calc {\"length\": \"12\", \"width\": \"14\", \"height\": \"8\", \"doors\": \"1\", \"windows\": \"2\"}: exactly how much paint a room needs",
             "- request {\"action\": \"...\", \"why\": \"...\"}: ask Claude to DO something (run, change, send, install, delete). You never do those yourself.",
             "Examples:",
             "QUESTION: Where is the Console code?  ->  you reply: TOOL: atlas_find {\"term\": \"Console\"}",
             "QUESTION: Delete my old files.  ->  you reply: TOOL: request {\"action\": \"delete the old files\", \"why\": \"Jerry asked\"}",
             "QUESTION: Say hi to Laurie.  ->  you reply: Hi Laurie! (no tool - just talking needs no tool)"]
    return "\n".join(lines)


def _first_param(name: str) -> str:
    fn = BASE.get(name) or REQUEST.get(name)
    names = fn.__code__.co_varnames[:fn.__code__.co_argcount] if fn else ()
    return names[0] if names else ""


def _call_spans(answer: str):
    """Every tool call in his answer, the ways a 3B model actually writes them (2026-10-08 eval):
    `TOOL: atlas_find {"term": "x"}`, `request {"action": ...}` inside a sentence, `COMMANDS: rotate-key`,
    `TOOL: engine "llama.cpp"`. Yields (start, end, name, args)."""
    names = "|".join(sorted(list(BASE) + list(REQUEST), key=len, reverse=True))
    pat = re.compile(r"(?:\bTOOL:\s*)?\b(" + names + r")\b\s*:?\s*(\{[^{}]*\})?", re.I)
    for m in pat.finditer(answer or ""):
        name = m.group(1).lower()
        start = m.start()
        line_start = answer.rfind("\n", 0, start) + 1
        prefix = answer[line_start:start]
        explicit = bool(re.match(r"\s*TOOL:", answer[start:start + 8], re.I)) or m.group(2) is not None
        own_line = prefix.strip() == ""
        if not (explicit or own_line):
            continue                       # just the word in a sentence ("the commands tool"), not a call
        args = {}
        if m.group(2):
            try:
                args = json.loads(m.group(2))
            except ValueError:
                args = {}
        else:                              # `COMMANDS: rotate-key` - free text after the name = first argument
            rest = answer[m.end():].split("\n", 1)[0].strip().strip('"\'')
            if rest and _first_param(name):
                args = {_first_param(name): rest}
        yield start, m.end() + (0 if m.group(2) else len(answer[m.end():].split("\n", 1)[0])), name, (args if isinstance(args, dict) else {})


def find_call(answer: str):
    """(name, args) for the first tool he asked for, else None."""
    for _, _, name, args in _call_spans(answer):
        return name, args
    return None


def strip_calls(answer: str) -> str:
    """His answer with any leftover tool-call text taken out."""
    out, last = [], 0
    for s, e, _, _ in _call_spans(answer):
        out.append(answer[last:s]); last = e
    out.append(answer[last:])
    return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()


def run(name: str, args: dict, question: str = "") -> str:
    fn = BASE.get(name) or REQUEST.get(name)
    if name == "lesson_find" and question:
        # his own search words can be lazy ("craft" for "an easy Sunday craft"); add the real question
        args = {**args, "topic": f"{args.get('topic', '')} {question}".strip()}
    if fn is None:
        return f"There is no tool called {name}. The tools are: {', '.join(list(BASE) + list(REQUEST))}."
    try:
        out = fn(**{k: str(v) for k, v in args.items() if k in fn.__code__.co_varnames})
    except Exception as e:
        out = f"{name} failed: {e}"
    return out[:MAX_OUT]
