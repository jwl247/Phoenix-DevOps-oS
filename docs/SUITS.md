# Suits — how to make one and run it

A **suit** is one file that does one job. The Phoenix kernel holds suits in its **closet**.
When a **stage** (a piece of data, here a JSON message) arrives addressed to a suit, Frank
"wears" that suit: he runs it on the stage and sends the answer back out.

```
you ──stage──▶ Helix-I (7701) ──▶ Frank wears the suit ──▶ Helix-E (7805) ──answer──▶ you
```

`genie send` does both ends for you: it listens on Helix-E first, then sends into Helix-I.

---

## Where suits run

| Machine has | Can write a suit | Can put it in Phoenix | Can run it |
|---|---|---|---|
| **Full Genie** (`genie.ps1` + the kernel, e.g. PBMII) | yes | `genie import <file>` (does it all) | yes: same command |
| **Cloud Genie** (`genie-cloud.ps1`, e.g. a member like JW's son) | yes | `genie intake <file>` | not on that machine: no kernel there. The owner imports it on a kernel |

**Owner, before you import someone else's suit:** importing runs their code on your
machine with the kernel's rights. Read it first: `genie clone <name> -To $HOME\review`.

---

## 1. Write it

Python is the proven suit type today (see "Other languages" below). Start from the template,
`sector1/kernel/genie/suits/stage_check.py`:

```python
import json

NAME = "my_suit"                    # = the file name without .py

def run(data, ball=None, pcs=None, **_):
    try:
        msg = json.loads(data)      # data = exactly the bytes that were sent in
    except (ValueError, TypeError):
        return json.dumps({"ok": False, "suit": NAME, "error": "stage is not JSON"})
    if not isinstance(msg, dict):
        return json.dumps({"ok": False, "suit": NAME, "error": "stage must be a JSON object"})

    # ── your job goes here ──
    answer = msg.get("text", "").upper()

    return json.dumps({"ok": True, "suit": NAME, "answer": answer})

if __name__ == "__main__":          # lets you test it without the kernel
    import sys
    print(run(sys.argv[1] if len(sys.argv) > 1 else '{"text": "test"}'))
```

**The rules a suit keeps:**

1. **`run(data, ball=None, pcs=None, **_)`** is the entry point. `data` is bytes (JSON).
   `ball` and `pcs` are Frank's run records; they may be `None`, so never depend on them.
2. **Return a JSON string with `"suit": "<its name>"` in it.** That's how `genie send` and
   the phone pick its answer out of the Helix-E stream. With no `"suit"` field, the answer
   still goes out, but `genie send` won't recognize it.
3. **Never raise.** On bad input, return `{"ok": false, "suit": ..., "error": "..."}`.
4. **Be quick.** Answer in seconds, not minutes. `genie send` waits 30 s by default (`-Wait`).
   For longer jobs, return "started" and do the work in a thread, as `lifefirst_checkin`
   does with its log.
5. **Standard library only** if you can. The kernel's Python is the only Python the suit
   gets. No `pip install` inside a suit.
6. **No secrets in the file.** Read them from the environment (`os.environ.get(...)`). The
   file goes into the pool, and others with keys can read it.
7. **A unique file name.** In Phoenix the file name *is* the identity (`my_suit.py` →
   its hex address). Once someone owns a name, nobody else can intake that name. Prefix
   yours, e.g. `kyle_weather.py`.

A real, bigger example is `sector2/apps/lifefirst/suits/lifefirst_checkin.py`. It
validates input, writes a hash-chained log, stores in Helix, and replies through
Ollama-local with an honest fallback.

## 2. Test it on its own (no kernel)

Where: any machine with Python 3, in the folder holding the file.

```powershell
python my_suit.py '{"text": "hello"}'
```
You should see your JSON answer. If this fails, the kernel will fail the same way. Fix it here.

## 3. Import it — the only step

Where: PBMII (the machine running the full Genie kernel), PowerShell 7, in the folder holding the file.

```powershell
genie import .\my_suit.py '{"text": "hello"}'
```

That one command does everything, in order:

1. **Intake.** The file goes into custody (SHA3-512 in D1, bytes in R2): v1, or the next version if
   the bytes changed. Identical bytes keep the existing version. A file flagged sensitive, or a
   *different* file with a name already in the pool, is refused, and nothing is loaded.
2. **Load.** The kernel pulls the bytes from R2 **straight into RAM**, checks them against the
   custody SHA3, and wears them. They are never written to this disk (`loaded: … R2 -> RAM,
   nothing on disk`). A tampered file never runs.
3. **Run.** The stage you gave (or `{}`) is sent, and the suit's answer is printed.

The kernel is started first if it's down. Loaded suits come back when the kernel restarts.
Already in the pool? `genie import my_suit.py` (by name) loads and runs it without the intake.

Options: `-Sector 1-4` (default 2), `-Family user|ai|network|assets|physics|system` (default
`user`), `-Name <other name>`, `-Write` (records that the suit may write; default read-only),
`-Wait 60`, `-Channel 1-4`.

Members (cloud Genie, no kernel on that machine): `genie intake .\my_suit.py` puts it in Phoenix.
The owner then runs `genie import my_suit.py` on a kernel.

## 4. Run it again with a new stage

```powershell
genie send my_suit '{"text": "again"}'
```

From another machine or a program, send the same JSON (with `"suit": "my_suit"`) into Helix-I
(7701–7704) and read Helix-E (7805–7808). That's what the phone node does
(`sector3/phone-node/phoenix_phone.py`). Off the box, the kernel needs `HELIX_SOCKET_TOKEN`
set. The client's first line is then `HXT <token>`, and the doors open on the mesh address.

## 5. Change it

Edit, test (step 2), then `genie import .\my_suit.py` again: it intakes the new version, loads it and runs it. If the kernel still answers the old way, run `genie restart`.

---

## When it doesn't answer

| You see | Means | Do |
|---|---|---|
| `kernel is down — genie up first` | no kernel on this machine | `genie up` |
| `SHA3-512 MISMATCH` on import | the bytes in R2 aren't what custody recorded | don't force it; re-intake from the file you trust |
| `no answer from 'x' within 30 s` | the suit isn't imported, its answer has no `"suit"`, it's slow, or it crashed | `genie closet`; then `genie log` and look for the suit's name; test it with step 2 |
| `addressed stage for 'x' refused: not a Genie-imported suit` in `genie log` | only Genie-imported suits answer addressed stages; core suits never do | `genie import` it |
| `Helix-E closed the stream` | the gate token is wrong or missing | set `HELIX_SOCKET_TOKEN` to the kernel's token |

## Other languages

The kernel has suit types for `SHELL`, `POWER` (PowerShell), `NODE` and `BINARY`. Those run
the file as a program: the stage goes in on **stdin**, and the answer is whatever it prints
on **stdout**. Today the kernel runs the file directly. That works for a real program, but
not for a `.ps1`, `.sh` or `.js` on Windows, and Genie doesn't mark the closet copy
executable on Linux. **Use Python suits until that's fixed.**
