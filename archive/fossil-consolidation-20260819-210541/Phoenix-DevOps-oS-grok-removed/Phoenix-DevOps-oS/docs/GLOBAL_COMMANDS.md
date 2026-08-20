# Phoenix DevOps OS - Global Commands

## Overview

Phoenix DevOps OS provides a suite of globally accessible commands that work seamlessly across Windows (CMD, PowerShell), Linux, and macOS (bash, zsh). All commands are automatically installed and configured during the installation process.

---

## Installation

### Automatic Installation

Global commands are automatically installed when you run:

**Windows:**
```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex"
```

**Linux/macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
```

### Verification

After installation, open a **new terminal** and verify commands are accessible:

```bash
# Check if commands are in PATH
usys --help
clone --help
intake --help
status
```

---

## Available Commands

### 1. `run` - Suite Execution (NEW!)

Execute suites directly from the clonepool without installation.

**Usage:**
```bash
run <suite-name> [args...]
run <suite-name>@<version> [args...]
```

**Examples:**
```bash
# Run latest version of a suite
run data-processor

# Run specific version
run data-processor@1.2.3

# Run with arguments
run backup-script --source /data --dest /backup

# Dry run (validate without executing)
run my-suite --dry-run
```

**Features:**
- Execute suites without installation
- Version selection support
- Argument passthrough
- Environment variable injection
- Multi-runtime support (Python, Node.js, bash, PowerShell)
- Permission-based security model

**Platform Support:**
- ✅ Windows CMD
- ✅ Windows PowerShell 7
- ✅ Linux bash
- ✅ macOS zsh

**See Also:** [SUITE_MANIFEST.md](./SUITE_MANIFEST.md) for suite format specification

---

### 2. `usys` - United Systems Command Interface

The main Phoenix command interface providing access to all Phoenix operations.

**Usage:**
```bash
usys <command> [options]
```

**Commands:**
- `usys status` - System health check
- `usys clone <file>` - Clone file to clonepool (Sector 2)
- `usys intake <file>` - Intake file to vault (Sector 4)
- `usys search <query>` - Search catalog
- `usys open <file>` - Open magic files (.lol, .phx)
- `usys init` - Initialize USys environment

**Examples:**
```bash
# Check system status
usys status

# Clone a file
usys clone ./myfile.py

# Search catalog
usys search "nginx config"
```

**Platform Support:**
- ✅ Windows CMD
- ✅ Windows PowerShell 7
- ✅ Linux bash
- ✅ macOS zsh

---

### 3. `clone` - Clonepool Intake (Sector 2)

Clone files into the Phoenix clonepool with versioning and metadata tracking.

**Usage:**
```bash
clone <file> [category] ["tag"]
```

**Parameters:**
- `file` - Path to file to clone (required)
- `category` - Optional category (e.g., configs, scripts, docs)
- `tag` - Optional descriptive tag (use quotes for multi-word tags)

**Examples:**
```bash
# Basic clone
clone ./franken.py

# Clone with category
clone ./nginx.conf configs

# Clone with category and tag
clone ./deploy.sh scripts "production deployment"

# Dry run (test without executing)
clone --dry-run ./myfile.sh
```

**Features:**
- Automatic versioning (v1, v2, v3...)
- JSON sidecar metadata
- D1 database sync (if PHOENIX_AUTH set)
- Hex-encoded filenames for safety
- Category organization

**Platform Support:**
- ✅ Windows CMD
- ✅ Windows PowerShell 7
- ✅ Linux bash
- ✅ macOS zsh

---

### 4. `intake` - Vault Intake (Sector 4)

Intake files into the Phoenix vault for secure storage and processing.

**Usage:**
```bash
intake <file> [options]
```

**Examples:**
```bash
# Basic intake
intake ./sensitive-config.json

# Intake with specific destination
intake ./data.csv T2
```

**Features:**
- Secure vault storage
- Encryption support
- Audit logging
- Integration with Sector 4 processing

**Platform Support:**
- ✅ Windows CMD (via Git Bash)
- ✅ Windows PowerShell 7 (via Git Bash)
- ✅ Linux bash
- ✅ macOS zsh

---

### 5. `status` - System Health Check

Display Phoenix system status and health information.

**Usage:**
```bash
status
```

**Output Includes:**
- Sector file counts
- Mount status
- Systemd service status (Linux)
- Catalog statistics
- Git repository status

**Examples:**
```bash
# Check system status
status

# Redirect to file
status > phoenix-status.txt
```

**Platform Support:**
- ✅ Windows CMD (via Git Bash)
- ✅ Windows PowerShell 7 (via Git Bash)
- ✅ Linux bash
- ✅ macOS zsh

---

### 6. `align_dirs` - Directory Alignment Utility

Align and synchronize directory structures across Phoenix installations.

**Usage:**
```bash
align_dirs [source] [target]
```

**Examples:**
```bash
# Align current directory
align_dirs

# Align specific directories
align_dirs ./source ./target
```

**Features:**
- Directory structure comparison
- Selective synchronization
- Dry-run mode
- Conflict resolution

**Platform Support:**
- ✅ Windows CMD (via Git Bash)
- ✅ Windows PowerShell 7 (via Git Bash)
- ✅ Linux bash
- ✅ macOS zsh

---

### 7. `get_distros` - Distribution Detection

Detect and report Linux distributions and WSL environments.

**Usage:**
```bash
get_distros
```

**Output:**
- Detected distributions
- WSL version (if applicable)
- Distribution versions
- Package manager information

**Examples:**
```bash
# Detect distributions
get_distros

# Use in scripts
DISTRO=$(get_distros | grep "ID=" | cut -d= -f2)
```

**Platform Support:**
- ✅ Windows CMD (via Git Bash)
- ✅ Windows PowerShell 7 (via Git Bash)
- ✅ Linux bash
- ✅ macOS zsh

---

## Environment Variables

Phoenix commands use the following environment variables:

| Variable | Description | Set By |
|----------|-------------|--------|
| `PHOENIX_ROOT` | Phoenix installation directory | install.ps1/sh |
| `PHOENIX_AUTH` | Authentication token for D1 sync | User (optional) |
| `PHOENIX_WORKER_URL` | Cloudflare Worker URL | install.ps1/sh |
| `CLONEPOOL_DIR` | Clonepool storage directory | install.ps1/sh |
| `PHOENIX_INTAKE` | Path to intake.sh (Sector 2) | install.ps1/sh |
| `PHOENIX_INTAKE_SECTOR4` | Path to Sector 4 intake | install.ps1/sh |

**View Environment:**
```bash
# Windows PowerShell
Get-ChildItem Env: | Where-Object Name -like "PHOENIX*"

# Linux/macOS
env | grep PHOENIX
```

---

## Troubleshooting

### Commands Not Found

**Windows:**
1. Open a **new** terminal (PATH updates require new session)
2. Verify `~/.usys/bin` is in PATH:
   ```powershell
   $env:PATH -split ';' | Select-String "usys"
   ```
3. If missing, re-run `install.ps1`

**Linux/macOS:**
1. Open a **new** terminal
2. Verify `~/.usys/bin` is in PATH:
   ```bash
   echo $PATH | grep -o "[^:]*usys[^:]*"
   ```
3. Source environment manually:
   ```bash
   source ~/.phoenix_env.sh
   export PATH="$HOME/.usys/bin:$PATH"
   ```
4. If still missing, re-run `install.sh`

### Permission Denied (Linux/macOS)

```bash
# Make commands executable
chmod +x ~/.usys/bin/*
```

### Git Bash Not Found (Windows)

Commands that use bash (intake, status, align_dirs, get_distros) require Git Bash:

```powershell
# Install Git for Windows
winget install Git.Git
```

### PowerShell 7 Not Found (Windows)

The `usys` and `clone` commands require PowerShell 7:

```powershell
# Install PowerShell 7
winget install Microsoft.PowerShell
```

### PHOENIX_AUTH Not Set

D1 sync features require `PHOENIX_AUTH`:

1. Get token from Cloudflare Worker settings
2. Set in environment file:
   - Windows: Edit `~/.phoenix_env.ps1`
   - Linux/macOS: Edit `~/.phoenix_env.sh`
3. Restart terminal

---

## Uninstallation

### Remove Global Commands

**Windows:**
```powershell
Remove-Item -Recurse -Force "$HOME\.usys"
```

**Linux/macOS:**
```bash
rm -rf ~/.usys
```

### Remove from PATH

**Windows:**
1. Open System Properties → Environment Variables
2. Edit user PATH
3. Remove `%USERPROFILE%\.usys\bin`

**Linux/macOS:**
1. Edit `~/.bashrc` and/or `~/.zshrc`
2. Remove Phoenix DevOps OS block
3. Restart terminal

---

## Advanced Usage

### Custom Installation Location

**Windows:**
```powershell
# Install to custom directory
$env:PHOENIX_ROOT = "D:\MyPhoenix"
.\install.ps1 -LocalRepo "D:\MyPhoenix\Phoenix-DevOps-oS"
```

**Linux/macOS:**
```bash
# Install to custom directory
export PHOENIX_ROOT="/opt/phoenix"
bash install.sh
```

### Scripting with Phoenix Commands

**PowerShell:**
```powershell
# Batch clone files
Get-ChildItem *.py | ForEach-Object {
    clone $_.FullName scripts "python scripts"
}
```

**Bash:**
```bash
# Batch clone files
for file in *.py; do
    clone "$file" scripts "python scripts"
done
```

### Integration with CI/CD

```yaml
# GitHub Actions example
- name: Install Phoenix
  run: |
    curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
    
- name: Clone artifacts
  run: |
    clone ./build-output.tar.gz artifacts "CI build ${{ github.run_number }}"
```

---

## Support

- **Issues:** https://github.com/jwl247/Phoenix-DevOps-oS/issues
- **Discussions:** https://github.com/jwl247/Phoenix-DevOps-oS/discussions
- **Documentation:** https://github.com/jwl247/Phoenix-DevOps-oS/tree/main/docs

---

**Built with ❤️ by jwl247 | Phoenix DevOps LLC**