# Rotating Master Image Backup System
## User Guide for Endeavour OS

---

## 📦 Installation

### Quick Install
```bash
# Download and run installer
curl -O https://your-repo/install.sh
chmod +x install.sh
./install.sh
```

### Manual Install
```bash
# Install dependencies
sudo pacman -S python python-pyqt6 restic

# Extract files to ~/.local/share/backup-system
# Edit config: ~/.config/backup-system/config.json
```

---

## ⚙️ Configuration

Edit `~/.config/backup-system/config.json`:

```json
{
    "repo_path": "/mnt/backup/restic-repo",
    "repo_password": "YOUR_SECURE_PASSWORD_HERE",
    "total_capacity_gb": 1000,
    "backup_paths": {
        "active_work": ["/home/user/work/current-project"],
        "critical": ["/home/user/work"],
        "important": ["/home/user/documents"],
        "standard": ["/home/user"]
    }
}
```

### Important Settings:

- **repo_path**: Where to store backups (can be local, network drive, or OpenStack)
- **repo_password**: Encryption password (keep it safe!)
- **total_capacity_gb**: Your 1TB storage limit
- **backup_paths**: What to back up and how often

---

## 🚀 Getting Started

### 1. Initialize Repository
```bash
# Launch the widget
backup-widget

# Or from command line
cd ~/.local/share/backup-system
./launch-widget.sh
```

In the widget:
1. Go to **Settings** tab
2. Click **Initialize Repository**
3. Wait for confirmation

### 2. Create First Master Image
1. Go to **Dashboard** tab
2. Click **Create Master Image**
3. This creates your baseline (takes 10-30 minutes)

### 3. Enable Automatic Snapshots
```bash
# Start the background daemon
systemctl --user start backup-snapshot

# Check status
systemctl --user status backup-snapshot

# View logs
tail -f ~/.local/share/backup-system/daemon.log
```

---

## 📊 Using the Widget

### Dashboard Tab
- **Storage Overview**: See how much space you're using
- **Master Image**: Your monthly full system snapshot
- **Incremental Snapshots**: Quick versions of changes
- **Quick Snapshot**: Manually create a snapshot now

### Snapshots Tab
- View all your snapshots
- Filter by path
- Double-click to see details
- See when each snapshot was created

### Restore Tab

#### Restore from Time
Perfect for "oops, I need the version from 30 minutes ago":

1. Enter **Minutes ago**: 30
2. Enter **Path to restore**: `/home/user/work/project`
3. Enter **Restore to**: `/tmp/restored`
4. Click **Restore from Time**

#### Restore from Snapshot ID
For specific snapshots:

1. Copy snapshot ID from Snapshots tab
2. Paste into **Snapshot ID** field
3. Choose restore location
4. Click **Restore Snapshot**

### Settings Tab
- View repository info
- See backup paths and schedules
- Initialize new repository

---

## ⏰ Snapshot Schedule

| Category | Frequency | Retention | Use Case |
|----------|-----------|-----------|----------|
| **Active Work** | 15 minutes | 2 hours | Files you're editing right now |
| **Critical** | 1 hour | 2 days | Important projects |
| **Important** | 6 hours | 2 weeks | Documents, configs |
| **Standard** | Daily | 1 week | Everything else |

---

## 🔄 How It Works

```
Your Files
    ↓
Every 15min/1hr/6hr/daily (automatic)
    ↓
Incremental Snapshots (~500GB storage)
    ↓
Every 30 days (automatic rotation)
    ↓
Master Image (~450GB storage)
```

### Storage Management
- **Total**: 1TB
- **Master Image**: ~450GB (your full system baseline)
- **Incremental Versions**: ~450GB (recent changes)
- **Buffer**: ~100GB (overhead)

When storage hits 85%, old incremental snapshots are automatically pruned.

---

## 💡 Common Tasks

### "I deleted a file 1 hour ago, how do I get it back?"

**Via Widget:**
1. Open widget → **Restore** tab
2. Minutes ago: `60`
3. Path: `/home/user/work/deleted_file.txt`
4. Restore to: `/tmp/restored`
5. Click **Restore from Time**
6. Find your file in `/tmp/restored`

**Via Command Line:**
```bash
# List recent snapshots
restic snapshots --path /home/user/work

# Restore the one from 1 hour ago
restic restore a1b2c3d4 \
    --target /tmp/restored \
    --include /home/user/work/deleted_file.txt
```

### "My system crashed, restore everything"

1. Boot from USB/live system
2. Mount your backup drive
3. Open widget or use CLI:
```bash
restic restore --tag MASTER_IMAGE --target /mnt/system
```

### "Check how much space I'm using"

**Widget**: Dashboard tab shows real-time usage

**CLI**:
```bash
restic stats
```

### "Manually create a snapshot now"

**Widget**: Dashboard → **Quick Snapshot**

**CLI**:
```bash
restic backup /home/user/work --tag manual
```

### "View all versions of a specific file"

**Widget**: Snapshots tab → filter by path

**CLI**:
```bash
restic snapshots --path /home/user/work/important.txt
```

---

## 🛠️ Troubleshooting

### Widget won't start
```bash
# Check if PyQt6 is installed
python3 -c "import PyQt6"

# If error, install:
sudo pacman -S python-pyqt6
```

### "Repository not found" error
1. Check config file: `~/.config/backup-system/config.json`
2. Verify repo_path exists: `ls /mnt/backup/restic-repo`
3. Initialize if needed: Settings tab → Initialize Repository

### Storage always at 85%+
```bash
# Manually prune old snapshots
restic forget --keep-hourly 24 --keep-daily 7
restic prune
```

### Daemon not creating snapshots
```bash
# Check daemon status
systemctl --user status backup-snapshot

# View logs
tail -f ~/.local/share/backup-system/daemon.log

# Restart daemon
systemctl --user restart backup-snapshot
```

### "Password incorrect" error
Edit config file and update `repo_password`:
```bash
nano ~/.config/backup-system/config.json
```

---

## 📝 Command Line Reference

### Environment Setup
```bash
export RESTIC_REPOSITORY="/mnt/backup/restic-repo"
export RESTIC_PASSWORD="your-password"
```

### Common Commands
```bash
# Create snapshot
restic backup /path/to/files

# List snapshots
restic snapshots

# Restore snapshot
restic restore snapshot_id --target /tmp/restore

# Check repository
restic check

# View stats
restic stats

# Remove old snapshots
restic forget --keep-daily 7 --keep-weekly 4

# Clean up unused data
restic prune

# Mount as filesystem
restic mount /mnt/restic
```

---

## 🔐 Security Notes

- Your backups are **encrypted** with your password
- Keep your password safe - lost password = lost backups
- Store password in password manager
- Consider backing up to **multiple locations**:
  - Local drive (fast recovery)
  - Network storage (safety)
  - Cloud/OpenStack (off-site)

---

## 📈 Best Practices

### Daily
- Check widget dashboard for storage levels
- Ensure daemon is running: `systemctl --user status backup-snapshot`

### Weekly
- Review snapshot list
- Test a restore (make sure it works!)

### Monthly
- Master image rotates automatically
- Verify backups are complete

### When Storage > 85%
- Widget will auto-prune old incrementals
- Or manually prune: Dashboard → **Prune Old Versions**

---

## 🎯 Recovery Scenarios

### Scenario 1: Accidental Delete (Recent)
→ Use **Restore from Time** (15min-2hrs ago)

### Scenario 2: Bad Edit (Today/Yesterday)
→ Use **Snapshots** tab, find hourly/daily snapshot

### Scenario 3: System Corruption
→ Restore **Master Image** (last known good state)

### Scenario 4: Ransomware
→ Restore from Master Image (encrypted, safe from malware)

---

## 🚨 Emergency Recovery

If your system is completely broken:

1. **Boot from live USB** (Endeavour OS live environment)
2. **Install restic**: `sudo pacman -S restic`
3. **Mount your backup drive**
4. **Set environment**:
   ```bash
   export RESTIC_REPOSITORY="/mnt/backup-drive/restic-repo"
   export RESTIC_PASSWORD="your-password"
   ```
5. **Restore master**:
   ```bash
   restic restore --tag MASTER_IMAGE --target /mnt/system
   ```
6. **Reboot into restored system**

---

## 💾 Storage Capacity Planning

### With 1TB Storage:

| Your Data Size | History Duration |
|----------------|------------------|
| 100GB active | 6-12 months detailed |
| 250GB active | 3-6 months detailed |
| 500GB active | 2-3 months detailed |

"Detailed" = hourly/daily snapshots
After that, you have monthly snapshots going back further.

---

## 🔗 Integration with Syncthing

The system works seamlessly with Syncthing:

1. Syncthing syncs files to backup location
2. Backup daemon detects changes
3. Creates snapshots automatically
4. Both systems work together for maximum protection

---

## 📞 Support

- **Logs**: `~/.local/share/backup-system/daemon.log`
- **Config**: `~/.config/backup-system/config.json`
- **Restic docs**: https://restic.readthedocs.io

---

## ⚡ Quick Tips

- **Green storage bar** = healthy (0-75%)
- **Orange storage bar** = watch it (75-85%)
- **Red storage bar** = prune soon (85%+)
- **Master rotates monthly** = your safety net
- **Incrementals prune automatically** = no maintenance needed
- **15min snapshots only for active work** = saves space
- **Test restores regularly** = ensure backups work

---

**Remember**: This system is designed to protect you from:
- Accidental deletes ✓
- Bad edits ✓
- System corruption ✓
- Ransomware ✓
- Hardware failure ✓ (if backing up to external drive)

Your data is safe! 🛡️
