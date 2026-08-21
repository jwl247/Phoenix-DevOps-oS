# ✅ LIFE FIRST AI - DEPLOYMENT CHECKLIST

## PRE-DEPLOYMENT

### What You Need
- [ ] VMware Workstation 17 Pro (installed)
- [ ] Ubuntu Server 24.04.3 LTS ISO file
- [ ] All files from this deployment package
- [ ] Claude API key from https://console.anthropic.com/
- [ ] 30-60 minutes of time

---

## PHASE 1: CREATE UBUNTU SERVER VM

- [ ] Open VMware Workstation 17 Pro
- [ ] Create new VM:
  - [ ] Select "Typical" configuration
  - [ ] Choose Ubuntu Server ISO
  - [ ] Set name: "LifeFirst-Server"
  - [ ] Set disk: 40 GB
  - [ ] Set RAM: 4 GB (4096 MB)
  - [ ] Set CPU: 2 cores
  - [ ] Set network: Bridged
- [ ] Power on VM
- [ ] Install Ubuntu Server:
  - [ ] Language: English
  - [ ] Network: DHCP (automatic)
  - [ ] Storage: Use entire disk
  - [ ] Create user account
  - [ ] ✅ Check "Install OpenSSH server"
  - [ ] Skip featured snaps
- [ ] Wait for installation (5-10 min)
- [ ] Reboot when prompted
- [ ] Login successfully

---

## PHASE 2: SERVER PREPARATION

- [ ] Get server IP address: `ip addr show`
- [ ] Write down IP: ________________
- [ ] Test SSH from Windows: `ssh admin@YOUR_IP`
- [ ] Can connect successfully

---

## PHASE 3: FILE UPLOAD

Upload these files to `/tmp/lifefirst_upload/` on server:

- [ ] lifefirst_setup.sh
- [ ] deploy_modules.sh
- [ ] module_1_database.sql
- [ ] module_3_schedule_ai.php
- [ ] module_4_messenger_ai.php
- [ ] module_6_notification_ai.php

**How to upload:**
```bash
# Create directory on server first
ssh admin@YOUR_IP
mkdir -p /tmp/lifefirst_upload
exit

# Then upload (from Windows)
scp lifefirst_setup.sh admin@YOUR_IP:/tmp/lifefirst_upload/
scp deploy_modules.sh admin@YOUR_IP:/tmp/lifefirst_upload/
scp module_*.* admin@YOUR_IP:/tmp/lifefirst_upload/
```

- [ ] All files uploaded successfully

---

## PHASE 4: RUN MAIN SETUP

SSH into server:
```bash
ssh admin@YOUR_IP
cd /tmp/lifefirst_upload
```

- [ ] Make script executable: `chmod +x lifefirst_setup.sh`
- [ ] Run setup: `sudo ./lifefirst_setup.sh`
- [ ] Setup completes without errors (5-10 min)
- [ ] Write down MySQL root password: ________________
- [ ] Write down database password: ________________
- [ ] Write down server info displayed

---

## PHASE 5: DEPLOY MODULES

- [ ] Make deploy script executable: `chmod +x deploy_modules.sh`
- [ ] Run deploy script: `sudo ./deploy_modules.sh`
- [ ] Enter MySQL root password when prompted
- [ ] Module 1 (Database) imports successfully
- [ ] Module 3 (Schedule AI) deploys
- [ ] Module 4 (Messenger AI) deploys
- [ ] Module 6 (Notification AI) deploys

---

## PHASE 6: CONFIGURATION

### Add Claude API Key

**File 1: Schedule AI**
- [ ] Open: `sudo nano /var/www/html/lifefirst/ai/ai_schedule.php`
- [ ] Go to line 25
- [ ] Replace: `YOUR_CLAUDE_API_KEY_HERE` with your actual key
- [ ] Save: Ctrl+O, Enter, Ctrl+X

**File 2: Messenger AI**
- [ ] Open: `sudo nano /var/www/html/lifefirst/ai/ai_messenger.php`
- [ ] Go to line 18
- [ ] Replace: `YOUR_CLAUDE_API_KEY_HERE` with your actual key
- [ ] Save: Ctrl+O, Enter, Ctrl+X

**File 3: Notification AI**
- [ ] Open: `sudo nano /var/www/html/lifefirst/ai/ai_notifications.php`
- [ ] Go to line 19
- [ ] Replace: `YOUR_CLAUDE_API_KEY_HERE` with your actual key
- [ ] Save: Ctrl+O, Enter, Ctrl+X

### Change API Secret

- [ ] Open: `sudo nano /var/www/html/lifefirst/api.php`
- [ ] Find line with: `define('API_SECRET'...`
- [ ] Change to your own secret token
- [ ] Write down your API secret: ________________
- [ ] Save: Ctrl+O, Enter, Ctrl+X

---

## PHASE 7: TESTING

### Test 1: Web Interface
- [ ] Open browser
- [ ] Go to: `http://YOUR_IP/lifefirst/`
- [ ] See "Life First AI System" welcome page
- [ ] Click "Test API Connection" button
- [ ] Get JSON response

### Test 2: Health Check
```bash
curl http://YOUR_IP/lifefirst/api.php?action=health
```
- [ ] Returns JSON with database: true
- [ ] Shows modules installed

### Test 3: Test Endpoint
```bash
curl http://YOUR_IP/lifefirst/api.php?action=test
```
- [ ] Returns success message
- [ ] Lists all modules

### Test 4: Database
```bash
mysql -u root -p lifefirst
```
- [ ] Can login with root password
- [ ] Run: `SHOW TABLES;`
- [ ] See multiple tables (users, schedule_events, etc.)
- [ ] Run: `SELECT * FROM users;`
- [ ] See "you" and "laurie" users

### Test 5: Full API Test
```bash
curl -X POST http://YOUR_IP/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "Authorization: YOUR_API_SECRET" \
  -d '{"username": "you", "message": "Am I free at 3pm today?", "action": "query"}'
```
- [ ] Returns JSON response
- [ ] Shows intent detected
- [ ] Gets response from Schedule AI

---

## PHASE 8: VERIFICATION

- [ ] Apache is running: `sudo systemctl status apache2`
- [ ] MySQL is running: `sudo systemctl status mysql`
- [ ] Firewall allows port 80: `sudo ufw status`
- [ ] All AI modules exist in `/var/www/html/lifefirst/ai/`
- [ ] API file exists: `/var/www/html/lifefirst/api.php`
- [ ] Permissions correct: `ls -la /var/www/html/lifefirst/`

---

## PHASE 9: DOCUMENTATION

### Save This Information

**Server Details:**
- IP Address: ________________
- MySQL Root Password: ________________
- Database Password: ________________
- API Secret Token: ________________
- Claude API Key: ________________

**URLs:**
- Web Interface: http://_______________/lifefirst/
- API Endpoint: http://_______________/lifefirst/api.php
- Health Check: http://_______________/lifefirst/api.php?action=health

**File Locations:**
- Web Root: /var/www/html/lifefirst/
- API File: /var/www/html/lifefirst/api.php
- AI Modules: /var/www/html/lifefirst/ai/
- Database Name: lifefirst

---

## PHASE 10: NEXT STEPS

### Working Features
- [x] Schedule checking
- [x] Cross-phone messaging
- [x] Notification system
- [x] Database storage

### To Add Later
- [ ] Module 5: Memory AI
- [ ] Module 7: Voice AI
- [ ] Module 8: Android App

### Android App Setup (When Ready)
- [ ] Install app on your phone
- [ ] Configure server URL
- [ ] Set API token
- [ ] Set username to "you"
- [ ] Test voice command

- [ ] Install app on Laurie's phone
- [ ] Configure server URL
- [ ] Set API token
- [ ] Set username to "laurie"
- [ ] Test voice command

---

## 🎉 DEPLOYMENT COMPLETE!

When all checkboxes are checked, your Life First AI system is live!

**Test Commands to Try:**
- "Am I free at 3pm today?"
- "Schedule a meeting at 4pm tomorrow"
- "Ask Laurie what pickles she wants"
- "Do I have any conflicts?"

---

## 🐛 TROUBLESHOOTING CHECKLIST

If something doesn't work:

- [ ] Check Apache logs: `sudo tail -f /var/log/apache2/error.log`
- [ ] Check MySQL is running: `sudo systemctl status mysql`
- [ ] Verify database exists: `mysql -u root -p` then `SHOW DATABASES;`
- [ ] Check file permissions: `ls -la /var/www/html/lifefirst/`
- [ ] Test connectivity: `ping YOUR_SERVER_IP`
- [ ] Verify firewall: `sudo ufw status`
- [ ] Check Claude API key is correct (no spaces)
- [ ] Verify API secret matches in app and server

---

**Keep this checklist for reference and troubleshooting!**
