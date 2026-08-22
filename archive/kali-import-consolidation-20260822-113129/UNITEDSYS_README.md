# UnitedSys

**Universal file registration, versioning, and hotswap.**  
Register any file. Call it from anywhere. Swap it live. Roll it back.

GPL v3 — zero dependencies beyond `bash` and `sqlite3` — no sudo required.

---

## Install

```bash
curl -sL https://raw.githubusercontent.com/jwl247/unitedsys/main/install.sh | bash
source ~/.bashrc
```

Or clone and run locally:
```bash
git clone https://github.com/jwl247/unitedsys
cd unitedsys
./install.sh
source ~/.bashrc
```

---

## What It Does

UnitedSys gives every file on your system a **name**, a **version**, and a **callable address**.

```bash
# Register any file — script, binary, config, anything
usys register ./my_tool.sh mytool

# Call it from anywhere on the system
usys call mytool
# or just
mytool

# Swap to a new version — live, no restart
usys swap mytool ./my_tool_v2.sh

# Something broke? Roll back instantly
usys rollback mytool

# Full version history
usys info mytool
```

---

## Commands

| Command | Description |
|---|---|
| `usys init` | First time setup |
| `usys register <file> <name>` | Register a file into the index |
| `usys call <name> [args...]` | Call a registered file |
| `usys swap <name> <newfile>` | Hotswap to a new version — live |
| `usys rollback <name> [ver]` | Roll back to previous version |
| `usys list` | List all registered files |
| `usys info <name>` | Full version history and swap log |
| `usys remove <name>` | Unregister |
| `usys where <name>` | Show file location |
| `usys sync <name> <dest>` | Sync current version to destination |
| `usys clone <name> <dest>` | Clone with full version history |
| `usys search <query>` | Search registry |

---

## How It Works

Everything lives in `~/.usys/`:

```
~/.usys/
├── usys.sh          ← the engine
├── usys.db          ← SQLite index (packages + versions + swap log)
├── bin/             ← callable wrappers — add to PATH once
│   ├── usys
│   ├── mytool       ← calls current version via DB lookup
│   └── ...
└── versions/        ← every version of every file, forever
    └── mytool/
        ├── v1_my_tool.sh
        ├── v2_my_tool_v2.sh
        └── ...
```

`~/.usys/bin` goes in your `PATH` once at install. After that every registered file is a direct command. Swap versions — the wrapper updates via DB lookup, no symlink chasing, no restart.

---

## Hotswap

The core feature. Swap a running tool to a new version without stopping anything:

```bash
# You're running mytool in production
# New version is ready — swap it live
usys swap mytool ./mytool_new.sh

# Next invocation uses the new version automatically
mytool  # ← now runs v2
```

Roll back just as fast:
```bash
usys rollback mytool       # back to previous
usys rollback mytool v1    # back to specific version
```

---

## Clone & Sync

Take your tools with you:

```bash
# Sync current version to another drive
usys sync mytool /media/backup/

# Clone with full history — restore on any machine
usys clone mytool /media/backup/
```

---

## No Sudo

UnitedSys lives entirely in your home directory. No system directories touched. No root required for any normal operation.

If you accidentally run with sudo, usys warns you before doing anything.

---

## Requirements

- `bash` 4+
- `sqlite3`

That's it.

---

## License

GPL v3 — use it, fork it, build on it.

---

*Built by JW — Phoenix-DevOps-oS*
