# Phoenix DevOps OS - Quick Start Guide

## Installation

### Windows (PowerShell)

Open PowerShell and run:

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex"
```

Or for local development:

```powershell
cd Phoenix-DevOps-oS
pwsh -ExecutionPolicy Bypass -File .\install.ps1
```

### Linux / macOS

Open terminal and run:

```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
```

Or for local development:

```bash
cd Phoenix-DevOps-oS
bash install.sh
```

---

## What Gets Installed

✅ **Phoenix DevOps OS** - Complete operating system framework  
✅ **Global Commands** - 6 commands accessible from anywhere  
✅ **Environment Setup** - Automatic PATH and environment configuration  
✅ **Package Handler** - Sector 2 clonepool intake system  
✅ **USys Integration** - United Systems command layer  

---

## Global Commands

After installation, these commands are available **globally** in any terminal:

| Command | Description | Example |
|---------|-------------|---------|
| `usys` | Main Phoenix interface | `usys status` |
| `clone` | Clone files to clonepool | `clone ./file.py` |
| `intake` | Intake files to vault | `intake ./config.json` |
| `status` | System health check | `status` |
| `align_dirs` | Directory alignment | `align_dirs` |
| `get_distros` | Distribution detection | `get_distros` |

**📖 Full documentation:** [GLOBAL_COMMANDS.md](./GLOBAL_COMMANDS.md)

---

## First Steps

### 1. Verify Installation

Open a **new terminal** and run:

```bash
usys status
```

You should see Phoenix system information.

### 2. Clone Your First File

```bash
# Clone a file to the clonepool
clone ./myfile.py scripts "my first clone"
```

### 3. Check Clonepool

```bash
# Windows
dir $HOME\Phoenix\clonepool

# Linux/macOS
ls -la ~/Phoenix/clonepool
```

### 4. Explore Commands

```bash
# Get help for any command
usys --help
clone --help
intake --help
```

---

## Configuration

### Environment Variables

Phoenix uses these environment variables (automatically set during installation):

- `PHOENIX_ROOT` - Installation directory
- `PHOENIX_AUTH` - Authentication token (optional, for D1 sync)
- `PHOENIX_WORKER_URL` - Cloudflare Worker endpoint
- `CLONEPOOL_DIR` - Clonepool storage location

### View Configuration

**Windows:**
```powershell
Get-Content $HOME\.phoenix_env.ps1
```

**Linux/macOS:**
```bash
cat ~/.phoenix_env.sh
```

### Set PHOENIX_AUTH (Optional)

For D1 database sync features:

1. Get your auth token from Cloudflare Worker settings
2. Edit environment file:
   - Windows: `~/.phoenix_env.ps1`
   - Linux/macOS: `~/.phoenix_env.sh`
3. Add: `export PHOENIX_AUTH="your-token-here"`
4. Restart terminal

---

## Common Tasks

### Clone Multiple Files

**PowerShell:**
```powershell
Get-ChildItem *.py | ForEach-Object { clone $_.FullName scripts }
```

**Bash:**
```bash
for file in *.py; do clone "$file" scripts; done
```

### Search Catalog

```bash
usys search "nginx"
```

### Check System Status

```bash
status
```

### Intake Sensitive Files

```bash
intake ./secrets.json
```

---

## Troubleshooting

### Commands Not Found

**Solution:** Open a **new terminal** (PATH updates require new session)

If still not working:

**Windows:**
```powershell
# Re-run installer
.\install.ps1 -Force
```

**Linux/macOS:**
```bash
# Source environment manually
source ~/.phoenix_env.sh
export PATH="$HOME/.usys/bin:$PATH"
```

### Permission Denied (Linux/macOS)

```bash
chmod +x ~/.usys/bin/*
```

### Git Bash Not Found (Windows)

```powershell
winget install Git.Git
```

### PowerShell 7 Not Found (Windows)

```powershell
winget install Microsoft.PowerShell
```

---

## Next Steps

- 📖 Read [GLOBAL_COMMANDS.md](./GLOBAL_COMMANDS.md) for detailed command documentation
- 🔧 Explore [Phoenix-Package_handler](https://github.com/jwl247/Phoenix-Package_handler)
- 🚀 Check out [LifeFirstApp](https://github.com/jwl247/LifeFirstApp)
- 💬 Join discussions on [GitHub](https://github.com/jwl247/Phoenix-DevOps-oS/discussions)

---

## Uninstall

### Windows

```powershell
Remove-Item -Recurse -Force "$HOME\Phoenix"
Remove-Item -Recurse -Force "$HOME\.usys"
Remove-Item "$HOME\.phoenix_env.ps1"
```

Then remove `%USERPROFILE%\.usys\bin` from user PATH in System Properties.

### Linux/macOS

```bash
rm -rf ~/Phoenix
rm -rf ~/.usys
rm ~/.phoenix_env.sh
```

Then remove Phoenix block from `~/.bashrc` and `~/.zshrc`.

---

**Need Help?** Open an issue: https://github.com/jwl247/Phoenix-DevOps-oS/issues

**Built with ❤️ by jwl247 | Phoenix DevOps LLC**