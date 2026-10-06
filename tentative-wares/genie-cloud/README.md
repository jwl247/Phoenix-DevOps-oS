# Genie: cloud edition (R2 + D1 only)

One file, `genie-cloud.ps1`. It needs PowerShell 7 and your own Phoenix key. You don't
need the Phoenix kernel, Python, or a copy of the repo. It works from anywhere: it talks to
Phoenix's storage (R2) and records (D1) through packages-worker.

To put files **in** (intake), it runs the package handler's `intake.sh`. On Windows that
needs Git for Windows, for bash.

## Set up (once)

1. **Get PowerShell 7 and Git** (Git gives you bash, which `genie intake` uses):

   - Windows, in any terminal: `winget install Microsoft.PowerShell` then `winget install Git.Git`
   - macOS: `brew install powershell` (bash is already there)
   - Debian/Ubuntu: see https://learn.microsoft.com/powershell/scripting/install/install-debian

2. **Unzip this folder anywhere,** open **PowerShell 7** (`pwsh`, not the old blue Windows
   PowerShell), go into the folder and run the installer:

   ```powershell
   cd <the unzipped folder>
   pwsh -File ./install-genie-cloud.ps1
   ```

   It asks for your key. JW gives you a key that starts with `phx_`, by Signal or in person.
   Paste it when asked. It's hidden while you type and never shown again. The installer
   saves it for you only, adds Genie to every PowerShell 7 window, and checks the connection.
   You should see `signed in as: <you>`.

3. **Open a new PowerShell 7 window, then fetch intake once:**

   ```powershell
   genie intake setup    # fetches intake.sh from Phoenix, checked against its fingerprint
   ```

Your key can read the pool and put in **your own** files. It can't change or delete anyone
else's. If your laptop is ever lost, tell JW. He turns that key off in one step and gives
you a new one.

## Start here

```powershell
genie tour
```

The tour walks through real files step by step (find, info, cat, clone, verify) and
explains each one as it goes. It writes nothing to Phoenix.

Then put something of your own in:

```powershell
genie intake C:\path\to\my_script.py
genie info my_script.py
```

## Commands

| Command | Does |
|---|---|
| `genie tour` | Guided walk-through on real files |
| `genie doctor` | Checks your keys, the worker, D1 and SHA3, and shows who you're signed in as |
| `genie find <word>` | Searches every record (and the glossary) |
| `genie info <name or hex>` | Record, fingerprint, version history and receipts |
| `genie cat <name or hex>` | Shows the code, only if its fingerprint matches |
| `genie clone <name or hex> [-To folder]` | Downloads it, checking the fingerprint before writing |
| `genie verify <file>` | Is my file the genuine one? |
| `genie intake <file or folder> [...]` | Puts it into Phoenix: a D1 record plus R2 bytes, as a new version if the name is yours |
| `genie custody [-Root folder]` | Lists records with no fingerprint and writes a re-intake script for review |
| `genie key list / new / revoke` | Owner only: one key per person |

## Rules you'll run into

- **Names are first come, first served.** If a name already belongs to someone else, intake
  refuses it: `[intake:REFUSED] 'main.py': "main.py" already belongs to ...`. Rename your
  file and intake it again.
- **Private records stay hidden.** Records JW marked sensitive don't show up for you at all.
- **Intake re-checks itself every run.** Before each run, Genie checks your `intake.sh`
  against Phoenix's copy. If they differ, run `genie intake setup` again.

## Tested

Tested against packages-worker 3.9.0 running locally on wrangler, with the real D1/R2
behaviour and the real `intake.sh`:

- **Clone:**
  - Verified clone works.
  - Tampered bytes are refused.
  - A file with no fingerprint is refused unless you add `-Force`.
  - A duplicate name is refused, with the hex_ids to choose from.
  - Old versions that were replaced are skipped.
- **Reading:**
  - `cat` refuses binary files.
  - All records are seen, past the worker's 100-row default.
- **SHA3:** matched against Python's hashlib at the edges of each 72-byte block, using the
  built-in Keccak for machines whose OS has no SHA3.
- **Intake:**
  - Member intake of a file and of a folder works.
  - Someone else's name is refused with the reason.
  - A changed local `intake.sh` is refused.
  - The tour leaves no scratch files behind.
