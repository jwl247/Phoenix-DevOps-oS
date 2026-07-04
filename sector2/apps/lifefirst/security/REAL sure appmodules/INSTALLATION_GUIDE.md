# LIFE FIRST AI SYSTEM - INSTALLATION GUIDE
## Ubuntu Server 24.04.3 LTS on VMware Workstation 17 Pro

---

## 📋 WHAT YOU NEED

1. ✅ VMware Workstation 17 Pro (you have this)
2. ✅ Ubuntu Server 24.04.3 LTS ISO (you have this)
3. ✅ Your 6 module files (you have these)
4. ⚠️ Claude API key (get from: https://console.anthropic.com/)

---

## 🚀 PART 1: CREATE UBUNTU SERVER VM

### Step 1: Create New VM in VMware

1. Open VMware Workstation 17 Pro
2. Click **"Create a New Virtual Machine"**
3. Select **"Typical"** configuration
4. Choose **"Installer disc image file (iso)"**
5. Browse to your **Ubuntu Server 24.04.3** ISO
6. VM Settings:
   - **Name**: LifeFirst-Server
   - **Disk Size**: 40 GB
   - **Memory**: 4 GB (4096 MB)
   - **Processors**: 2 cores
   - **Network**: Bridged (so phones can access)

### Step 2: Install Ubuntu Server

1. Power on the VM
2. Follow installer:
   - Language: English
   - Keyboard: Your layout
   - Network: DHCP (automatic)
   - Storage: Use entire disk
   - Profile:
     - Name: Your name
     - Server name: `lifefirst-server`
     - Username: `admin`
     - Password: (create strong password)
   - **IMPORTANT**: Check ✅ "Install OpenSSH server"
   - Snaps: Skip all
3. Wait for installation (5-10 minutes)
4. Reboot when prompted
5. Login with your credentials

### Step 3: Get Server IP Address

After login, run:
```bash
ip addr show
```

Look for the IP address (e.g., 192.168.1.100) - **WRITE THIS DOWN!**

---

## 🛠️ PART 2: INSTALL LIFE FIRST SYSTEM

### Step 1: Transfer Setup Script to Server

**Option A: Using SCP (from your Windows machine)**
```bash
# Open PowerShell/Command Prompt
scp lifefirst_setup.sh admin@SERVER_IP:/home/admin/
```

**Option B: Using WinSCP or FileZilla**
- Connect to your server IP
- Upload `lifefirst_setup.sh` to `/home/admin/`

**Option C: Copy/Paste Method**
1. SSH into server: `ssh admin@SERVER_IP`
2. Create file: `nano lifefirst_setup.sh`
3. Copy entire script content
4. Paste in nano (right-click)
5. Save: Ctrl+O, Enter, Ctrl+X

### Step 2: Run Setup Script

```bash
# Make executable
chmod +x lifefirst_setup.sh

# Run as root
sudo ./lifefirst_setup.sh
```

The script will:
- ✅ Install Apache, MySQL, PHP
- ✅ Create database and user
- ✅ Deploy API router
- ✅ Configure firewall
- ✅ Create test page

This takes **5-10 minutes**.

### Step 3: Upload Your Module Files

Create upload directory:
```bash
sudo mkdir -p /tmp/lifefirst_modules
cd /tmp/lifefirst_modules
```

Transfer your files here:
- module_1_database.sql
- module_3_schedule_ai.php
- module_4_messenger_ai.php
- module_6_notification_ai.php

### Step 4: Deploy Modules

```bash
# Upload deploy script
sudo chmod +x deploy_modules.sh
sudo ./deploy_modules.sh
```

Follow the prompts to import database and deploy AI modules.

---

## ⚙️ PART 3: CONFIGURATION

### Step 1: Add Claude API Key

Edit each AI module and add your Claude API key:

```bash
sudo nano /var/www/html/lifefirst/ai/ai_schedule.php
```

Find line 25:
```php
define('CLAUDE_API_KEY', 'YOUR_CLAUDE_API_KEY_HERE');
```

Replace with your actual key:
```php
define('CLAUDE_API_KEY', 'sk-ant-api03-...');
```

Repeat for:
- `/var/www/html/lifefirst/ai/ai_messenger.php` (line 18)
- `/var/www/html/lifefirst/ai/ai_notifications.php` (line 19)

### Step 2: Change Default Passwords (IMPORTANT!)

Edit API router:
```bash
sudo nano /var/www/html/lifefirst/api.php
```

Change these values:
- **API_SECRET** (line ~40): Change to your own secret token
- **DB_PASS** (line ~38): Should match what setup script used

### Step 3: Import Database Schema

```bash
mysql -u root -p lifefirst < /tmp/lifefirst_modules/module_1_database.sql
```

Enter the root password when prompted (default: `LifeFirst2024!`)

---

## ✅ PART 4: TESTING

### Test 1: Web Interface

Open browser and visit:
```
http://YOUR_SERVER_IP/lifefirst/
```

You should see the Life First welcome page.

### Test 2: API Health Check

```bash
curl http://YOUR_SERVER_IP/lifefirst/api.php?action=health
```

Should return JSON with status information.

### Test 3: API Test Endpoint

```bash
curl http://YOUR_SERVER_IP/lifefirst/api.php?action=test
```

Should show all modules and their status.

### Test 4: Database Connection

```bash
mysql -u lifefirst_user -p lifefirst
```

Password: `LifeFirst_DB_2024!`

Run:
```sql
SHOW TABLES;
SELECT * FROM users;
```

You should see "you" and "laurie" users.

---

## 📱 PART 5: CONNECT YOUR PHONES

### Android App Configuration

In your Android app, set:
- **Server URL**: `http://YOUR_SERVER_IP/lifefirst/api.php`
- **API Token**: (the API_SECRET you set)
- **Username**: `you` or `laurie`

### Test from Phone

Try voice command:
> "Am I free at 3pm today?"

The API should:
1. Receive request
2. Detect "schedule" intent
3. Route to Schedule AI
4. Check your calendar
5. Respond with answer

---

## 🔧 TROUBLESHOOTING

### Problem: Can't reach server from phone

**Solution**: Check firewall
```bash
sudo ufw status
sudo ufw allow 80/tcp
```

### Problem: Database connection failed

**Solution**: Check MySQL service
```bash
sudo systemctl status mysql
sudo systemctl restart mysql
```

### Problem: PHP errors

**Solution**: Check Apache error log
```bash
sudo tail -f /var/log/apache2/error.log
```

### Problem: Can't import database

**Solution**: Reset and retry
```bash
mysql -u root -p
DROP DATABASE lifefirst;
CREATE DATABASE lifefirst;
EXIT;

mysql -u root -p lifefirst < module_1_database.sql
```

---

## 📊 SYSTEM INFO

### Default Credentials

**MySQL Root**
- Username: `root`
- Password: `LifeFirst2024!`

**MySQL App User**
- Username: `lifefirst_user`
- Password: `LifeFirst_DB_2024!`
- Database: `lifefirst`

**API Authentication**
- Token: `your_secret_token_change_me_12345` (CHANGE THIS!)

### File Locations

- **Web Root**: `/var/www/html/lifefirst/`
- **API File**: `/var/www/html/lifefirst/api.php`
- **AI Modules**: `/var/www/html/lifefirst/ai/`
- **Logs**: `/var/log/apache2/`

### Important Commands

**Restart Services**
```bash
sudo systemctl restart apache2
sudo systemctl restart mysql
```

**View Logs**
```bash
# Apache access log
sudo tail -f /var/log/apache2/access.log

# Apache error log
sudo tail -f /var/log/apache2/error.log

# MySQL log
sudo tail -f /var/log/mysql/error.log
```

**Check Service Status**
```bash
sudo systemctl status apache2
sudo systemctl status mysql
```

---

## 🎯 NEXT STEPS

Once everything is working:

1. ✅ Test all API endpoints from browser
2. ✅ Test from Android app
3. ✅ Add more schedule events
4. ✅ Test cross-phone messaging
5. ✅ Build Module 5 (Memory AI)
6. ✅ Build Module 7 (Voice AI)
7. ✅ Build Module 8 (Android app enhancements)

---

## 📞 SUPPORT

If you need help:
1. Check `/root/lifefirst_info.txt` for system info
2. Review logs in `/var/log/apache2/`
3. Test with `curl` commands first
4. Verify database tables exist
5. Check API key is correct in AI modules

---

## ✨ YOU'RE READY!

Your Life First AI system should now be running on:
```
http://YOUR_SERVER_IP/lifefirst/
```

Test it from your phones and start asking questions! 🎉
