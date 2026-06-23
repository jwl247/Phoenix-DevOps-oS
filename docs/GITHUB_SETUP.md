# Publishing Phoenix-DevOps-oS to GitHub

## Quick Guide: Push to New GitHub Repository

### Step 1: Create Repository on GitHub

1. Go to https://github.com/new
2. Repository name: `Phoenix-DevOps-oS`
3. Description: `Phoenix DevOps OS - Agnostic, deterministic, self-healing operating system`
4. Choose: **Public** (for open source)
5. **DO NOT** initialize with README (we already have one)
6. Click "Create repository"

### Step 2: Push Your Code

Open terminal in `Phoenix-DevOps-oS` directory and run:

```bash
# Initialize git (if not already done)
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: Phoenix DevOps OS with global commands and suite execution"

# Add GitHub as remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/Phoenix-DevOps-oS.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### Step 3: Verify Installation URLs

After pushing, verify these URLs work:

**Windows Bootstrap:**
```
https://raw.githubusercontent.com/YOUR_USERNAME/Phoenix-DevOps-oS/main/bootstrap/lol-bootstrap.ps1
```

**Linux/macOS Bootstrap:**
```
https://raw.githubusercontent.com/YOUR_USERNAME/Phoenix-DevOps-oS/main/bootstrap/lol-bootstrap.sh
```

**Windows Installer:**
```
https://raw.githubusercontent.com/YOUR_USERNAME/Phoenix-DevOps-oS/main/install.ps1
```

**Linux/macOS Installer:**
```
https://raw.githubusercontent.com/YOUR_USERNAME/Phoenix-DevOps-oS/main/install.sh
```

---

## Detailed Steps

### If You Already Have a Git Repository

```bash
cd Phoenix-DevOps-oS

# Check current status
git status

# Add new files
git add bin/
git add bootstrap/
git add docs/
git add scripts/usys.ps1
git add install.ps1
git add install.sh
git add README.md

# Commit changes
git commit -m "Add global commands, suite execution, and LOL installer"

# Push to GitHub
git push origin main
```

### If Starting Fresh

```bash
cd Phoenix-DevOps-oS

# Initialize git
git init

# Add all files
git add .

# Create .gitignore
cat > .gitignore << 'EOF'
# Node
node_modules/
npm-debug.log

# Python
__pycache__/
*.py[cod]
*.so
.Python
env/
venv/

# OS
.DS_Store
Thumbs.db
desktop.ini

# IDE
.vscode/
.idea/
*.swp
*.swo

# Phoenix
clonepool/
.usys/
.lol/
.phoenix/
EOF

# Commit
git commit -m "Initial commit: Phoenix DevOps OS"

# Add remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/Phoenix-DevOps-oS.git

# Push
git branch -M main
git push -u origin main
```

---

## Update README URLs

After pushing to YOUR GitHub account, update these URLs in README.md:

### Find and Replace

**Old:**
```
https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/
```

**New:**
```
https://raw.githubusercontent.com/YOUR_USERNAME/Phoenix-DevOps-oS/main/
```

**Files to update:**
- `README.md`
- `docs/QUICK_START.md`
- `docs/LOL_INSTALLER.md`
- `docs/GLOBAL_COMMANDS.md`

### Quick Replace Command

**PowerShell:**
```powershell
$files = @(
    "README.md",
    "docs/QUICK_START.md",
    "docs/LOL_INSTALLER.md",
    "docs/GLOBAL_COMMANDS.md"
)

foreach ($file in $files) {
    if (Test-Path $file) {
        (Get-Content $file) -replace 'jwl247', 'YOUR_USERNAME' | Set-Content $file
    }
}
```

**Bash:**
```bash
find . -type f \( -name "*.md" \) -exec sed -i 's/jwl247/YOUR_USERNAME/g' {} +
```

---

## Test Installation

After pushing to GitHub, test the installation:

### Test LOL Bootstrap

**Windows:**
```powershell
irm https://raw.githubusercontent.com/YOUR_USERNAME/Phoenix-DevOps-oS/main/bootstrap/lol-bootstrap.ps1 | iex
```

**Linux/macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/Phoenix-DevOps-oS/main/bootstrap/lol-bootstrap.sh | bash
```

### Test Direct Install

**Windows:**
```powershell
irm https://raw.githubusercontent.com/YOUR_USERNAME/Phoenix-DevOps-oS/main/install.ps1 | iex
```

**Linux/macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/Phoenix-DevOps-oS/main/install.sh | bash
```

---

## GitHub Repository Settings

### Recommended Settings

1. **About Section:**
   - Description: "Phoenix DevOps OS - Agnostic, deterministic, self-healing operating system"
   - Website: Your project website (if any)
   - Topics: `devops`, `automation`, `package-manager`, `cross-platform`, `powershell`, `bash`

2. **README:**
   - Should display automatically
   - Verify badges work
   - Check all links

3. **License:**
   - Add `LICENSE` file with GPL-3.0 text
   - GitHub will auto-detect it

4. **Releases:**
   - Create v1.0.0 release after testing
   - Include changelog
   - Tag the commit

---

## Create First Release

```bash
# Tag the current commit
git tag -a v1.0.0 -m "Release v1.0.0: Global commands + Suite execution + LOL installer"

# Push tag to GitHub
git push origin v1.0.0
```

Then on GitHub:
1. Go to "Releases"
2. Click "Draft a new release"
3. Select tag: v1.0.0
4. Title: "Phoenix DevOps OS v1.0.0"
5. Description: List features
6. Click "Publish release"

---

## Troubleshooting

### Permission Denied

```bash
# Use HTTPS with token
git remote set-url origin https://YOUR_TOKEN@github.com/YOUR_USERNAME/Phoenix-DevOps-oS.git

# Or use SSH
git remote set-url origin git@github.com:YOUR_USERNAME/Phoenix-DevOps-oS.git
```

### Large Files

If you have large files:

```bash
# Check file sizes
find . -type f -size +50M

# Remove from git if needed
git rm --cached large-file.bin
echo "large-file.bin" >> .gitignore
git commit -m "Remove large file"
```

### Already Exists Error

```bash
# Force push (CAUTION: overwrites remote)
git push -f origin main
```

---

## Maintenance

### Keep Repository Updated

```bash
# Regular workflow
git add .
git commit -m "Description of changes"
git push origin main
```

### Create Branches for Features

```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes, commit
git add .
git commit -m "Add new feature"

# Push branch
git push origin feature/new-feature

# Create Pull Request on GitHub
```

---

## Summary

**Quick Commands:**

```bash
# 1. Create repo on GitHub
# 2. Push code
cd Phoenix-DevOps-oS
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/Phoenix-DevOps-oS.git
git branch -M main
git push -u origin main

# 3. Update URLs in docs (replace jwl247 with YOUR_USERNAME)
# 4. Test installation
# 5. Create release
```

Your Phoenix-DevOps-oS is now live on GitHub! 🚀