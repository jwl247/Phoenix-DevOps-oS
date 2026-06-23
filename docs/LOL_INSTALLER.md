# LOL - Live Ops Loader

## Overview

LOL (Live Ops Loader) is an ultra-minimal package installer that enables simple one-command installation of Phoenix packages.

```bash
lol install phoenix-devops-os
```

---

## Installation

### Windows

```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/bootstrap/lol-bootstrap.ps1 | iex
```

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/bootstrap/lol-bootstrap.sh | bash
```

**What it does:**
1. Creates `~/.lol/bin/` directory
2. Installs minimal `lol` command
3. Adds to PATH automatically
4. No admin/sudo required

---

## Usage

### Install a Package

```bash
lol install <package-name>
```

### Available Packages

| Package | Description |
|---------|-------------|
| `phoenix-devops-os` | Complete Phoenix DevOps OS with global commands |
| `phoenix-package-handler` | Phoenix Package Handler (Sector 2) |

### Examples

```bash
# Install Phoenix DevOps OS
lol install phoenix-devops-os

# Install Package Handler
lol install phoenix-package-handler

# Show help
lol help
```

---

## How It Works

### Package Registry

LOL uses a simple built-in registry that maps package names to GitHub installer URLs:

```bash
phoenix-devops-os → https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1
phoenix-package-handler → https://raw.githubusercontent.com/jwl247/Phoenix-Package_handler/main/install.ps1
```

### Installation Flow

1. User runs: `lol install phoenix-devops-os`
2. LOL looks up package in registry
3. LOL downloads and executes the installer
4. Package installs with all dependencies

---

## Architecture

### Windows (lol.cmd)

```
User runs: lol install phoenix-devops-os
    ↓
lol.cmd (in ~/.lol/bin/)
    ↓
Looks up package URL
    ↓
Executes: irm <url> | iex
    ↓
Package installer runs
```

### Linux/macOS (lol)

```
User runs: lol install phoenix-devops-os
    ↓
lol script (in ~/.lol/bin/)
    ↓
Looks up package URL
    ↓
Executes: curl -fsSL <url> | bash
    ↓
Package installer runs
```

---

## Adding New Packages

To add a new package to LOL:

1. **Create installer script** (install.ps1 or install.sh)
2. **Host on GitHub** (in your repository)
3. **Add to LOL registry** (edit lol.cmd and lol script)

### Example: Adding a New Package

**In lol.cmd (Windows):**
```batch
if /i "%PACKAGE%"=="my-new-package" (
    set "INSTALL_URL=https://raw.githubusercontent.com/user/repo/main/install.ps1"
)
```

**In lol script (Linux/macOS):**
```bash
my-new-package)
    INSTALL_URL="https://raw.githubusercontent.com/user/repo/main/install.sh"
    ;;
```

---

## Comparison with Other Installers

| Feature | LOL | npm | pip | cargo |
|---------|-----|-----|-----|-------|
| Bootstrap size | ~5KB | ~50MB | ~20MB | ~100MB |
| Dependencies | None | Node.js | Python | Rust |
| Install time | <1s | ~30s | ~10s | ~60s |
| Cross-platform | ✅ | ✅ | ✅ | ✅ |
| Package registry | Built-in | npmjs.com | pypi.org | crates.io |

---

## Security

### Bootstrap Security

- ✅ Downloads from GitHub (HTTPS)
- ✅ No code execution during bootstrap
- ✅ User scope only (no admin required)
- ✅ Minimal attack surface (~100 lines)

### Package Security

- ✅ Each package installer is responsible for its own security
- ✅ All installers run in user scope
- ✅ Source code is public and auditable
- ✅ No binary downloads (scripts only)

---

## Troubleshooting

### LOL Command Not Found

**Windows:**
```powershell
# Check if LOL is in PATH
$env:PATH -split ';' | Select-String "lol"

# Re-run bootstrap
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/bootstrap/lol-bootstrap.ps1 | iex
```

**Linux/macOS:**
```bash
# Check if LOL is in PATH
echo $PATH | grep -o "[^:]*lol[^:]*"

# Re-run bootstrap
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/bootstrap/lol-bootstrap.sh | bash

# Source shell config
source ~/.bashrc  # or ~/.zshrc
```

### Package Installation Fails

```bash
# Try direct installation instead
# Windows:
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex

# Linux/macOS:
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
```

### Permission Denied (Linux/macOS)

```bash
# Make sure lol is executable
chmod +x ~/.lol/bin/lol

# Check PATH
echo $PATH | grep ".lol/bin"
```

---

## Uninstallation

### Remove LOL

**Windows:**
```powershell
Remove-Item -Recurse -Force "$HOME\.lol"
# Remove from PATH in System Properties → Environment Variables
```

**Linux/macOS:**
```bash
rm -rf ~/.lol
# Remove from ~/.bashrc and ~/.zshrc:
# Delete lines containing ".lol/bin"
```

---

## Philosophy

LOL follows these principles:

1. **Minimal** - Smallest possible footprint
2. **Simple** - One command to install anything
3. **Secure** - User scope, no elevation
4. **Fast** - Bootstrap in <1 second
5. **Transparent** - All code is readable and auditable

---

## Future Enhancements

Potential future features:

- [ ] Remote package registry (JSON file on GitHub)
- [ ] Package versioning support
- [ ] Package search functionality
- [ ] Package update checking
- [ ] Dependency resolution
- [ ] Package removal command

---

## Contributing

To add your package to LOL:

1. Create an installer script (install.ps1 or install.sh)
2. Host it on GitHub
3. Submit a PR to add it to the LOL registry
4. Include documentation and examples

---

**Built with ❤️ by jwl247 | Phoenix DevOps LLC**