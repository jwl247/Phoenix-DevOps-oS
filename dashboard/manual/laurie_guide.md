# Phoenix — Laurie's Guide

Welcome! This guide explains how to use Phoenix. No technical knowledge needed.

---

## What is Phoenix?

Phoenix is Jerry's operating system for managing files, tools, and projects. Think of it as a very organised filing cabinet with a control panel on top.

You have a protected share inside Phoenix. Your files live in the **clonepool** — a safe, versioned storage area where nothing ever gets deleted or overwritten.

---

## The Control Panel (Dashboard)

When you open the dashboard, you will see:

- **Left side** — Sector switches (big toggle buttons). Leave these alone unless Jerry has asked you to flip one.
- **Centre** — The main display where you do things. Use the buttons at the bottom to switch between views.
- **Right side** — System gauges showing CPU, memory, and disk. These are just for monitoring — you don't need to touch them.

---

## The Tabs at the Bottom

Click any tab to switch to that view:

| Tab | What it does |
|-----|-------------|
| **AI CHAT** | Ask Phoenix anything. Type your question and press the arrow button (or Enter). |
| **HELP CHAT** | The full technical manual for operators. Has a search box. |
| **MAP** | Browse files and folders on this computer. Click a folder to open it. |
| **SECTOR MAP** | Shows which parts of Phoenix are active. Read-only for you. |
| **CODES** | Command line for Jerry. You can type commands here if Jerry shows you how. |
| **GUIDE** | This guide — you're reading it right now! |

---

## Asking the AI a Question

1. Click the **AI CHAT** tab.
2. Type your question in the box at the bottom.
3. Press **Enter** or click the arrow button.
4. The AI will reply above. It uses Ollama (local) first, then Claude if Ollama is unavailable.

If it says "OLLAMA OFFLINE" at the top right, the AI is still working — it will switch to Claude automatically.

---

## Finding a File

1. Click the **MAP** tab.
2. Use the buttons along the top (HOME, DOCUMENTS, DESKTOP, etc.) to jump to a location.
3. Click any folder to expand it.
4. Your files are usually in **DOCUMENTS** or under the path Jerry gave you.

---

## Running a Script (CODES tab)

Jerry may ask you to run a command. Here's how:

1. Click the **CODES** tab.
2. Make sure **PHOENIX CLI** is selected at the top of the panel.
3. Type the command Jerry gave you in the input box.
4. Press **Enter** or click **RUN**.
5. The output appears above. Green = good. Yellow = warning. Red = error.

**Do not type anything in the command box unless Jerry has asked you to.**

---

## The Sector Switches

The switches on the left side of the dashboard control which parts of Phoenix are active:

- **Sector 1** — Boot and kernel tools
- **Sector 2** — File intake and clone pool (this is where your files go)
- **Sector 3** — Network and communications
- **Sector 4** — Helix engine and Frank (the import system)
- **HELIX ENGINE** — The core memory engine (always on)

You generally don't need to touch these. If a command says "switch is OFF", tell Jerry.

---

## Your Protected Share

Your files in Phoenix are stored in the **clonepool**. Every file has a unique fingerprint (called a hex ID) so it can never be confused with another file, even if two files have the same name.

When Jerry runs `intake` on a file, Phoenix:

1. Computes the file's fingerprint (SHA3-512)
2. Writes a sidecar record next to the file
3. Copies the file into the clonepool
4. Logs it in the catalog

Nothing is ever deleted from the clonepool.

---

## If Something Looks Wrong

- **AI CHAT not responding** — wait 30 seconds and try again. The AI chain will retry.
- **Sector switch won't turn on** — don't force it. Tell Jerry.
- **"Manual not found" in HELP CHAT** — the manual file may need to be reloaded. Click the ↻ button.
- **Red error in CODES** — stop and tell Jerry what the red text says.

---

## Keyboard Shortcuts

| Key | What it does |
|-----|-------------|
| Enter | Send AI chat message / run CLI command |
| Escape | Close the auth settings panel |

---

*Phoenix DevOps OS — Laurie's Guide v1.0*
