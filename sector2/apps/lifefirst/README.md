# lifefirst_modules
9 modules
# 🤖 LIFE FIRST AI SYSTEM - DEPLOYMENT PACKAGE
## Complete Bond Setup for Ubuntu Server

---

## 📦 WHAT'S IN THIS PACKAGE

```
lifefirst_deployment_package/
├── INSTALLATION_GUIDE.md          ← Step-by-step instructions
├── lifefirst_setup.sh              ← Main installer script
├── deploy_modules.sh               ← Module deployment script
├── module_1_database.sql           ← Database schema ✅
├── module_3_schedule_ai.php        ← Schedule AI ✅
├── module_4_messenger_ai.php       ← Messenger AI ✅
└── module_6_notification_ai.php    ← Notification AI ✅
```

### ✅ What You HAVE (Complete!)
- **Module 1**: Database Schema (SQL)
- **Module 2**: API Router (embedded in setup script)
- **Module 3**: Schedule AI (AI #1)
- **Module 4**: Messenger AI (AI #2)
- **Module 6**: Notification AI (AI #4)

---

## ⚠️ WHAT'S MISSING FROM YOUR BOND

### Module 5: Memory Keeper AI (AI #3)
**Status**: ❌ Not Created Yet
**File Needed**: `module_5_memory_ai.php`
**What it does**: 
- Remembers user preferences
- Learns from conversations
- Recalls past interactions
- "What does Laurie like?" queries

**Workaround**: The API router will return "Memory AI not installed" for now. System works without it.

### Module 7: Voice Commander AI (AI #5)
**Status**: ❌ Not Created Yet
**File Needed**: `module_7_voice_ai.php`
**What it does**:
- General conversation handler
- Fallback for non-specific queries
- Natural language processing
- Voice command interpretation

**Workaround**: The API router will return "Voice AI not installed" for now. Other AIs still work.

### Module 8: Android App
**Status**: ❌ Not Created Yet
**What it is**: The Android app that runs on your phones
**What it needs**:
- Voice input/output
- API communication
- Push notifications
- UI for both phones

---

## 🎯 WHAT YOU CAN DO RIGHT NOW

### Option 1: Deploy What You Have (RECOMMENDED)
You can **fully deploy** the system now with Modules 1-4 & 6. This gives you:
- ✅ Schedule checking ("Am I free at 3pm?")
- ✅ Cross-phone messaging ("Ask Laurie about pickles")
- ✅ Urgent notifications (escalating alerts)
- ✅ Calendar conflict detection

**Missing features without Modules 5 & 7**:
- ❌ Memory/preference learning
- ❌ General conversation fallback

### Option 2: Wait for Complete System
I can help you create Modules 5 & 7 before deployment.

---

## 🚀 DEPLOYMENT STEPS (Using What You Have)

### 1. Prepare Your Ubuntu Server VM
Follow the installation guide to:
- Create VM in VMware
- Install Ubuntu Server 24.04.3
- Note the server IP address

### 2. Upload All Files to Server

**Create upload directory on server:**
```bash
mkdir -p /tmp/lifefirst_upload
cd /tmp/lifefirst_upload
```

**Transfer files from Windows to server:**

Using SCP (PowerShell/Command Prompt):
```bash
scp lifefirst_setup.sh admin@SERVER_IP:/tmp/lifefirst_upload/
scp deploy_modules.sh admin@SERVER_IP:/tmp/lifefirst_upload/
scp module_1_database.sql admin@SERVER_IP:/tmp/lifefirst_upload/
scp module_3_schedule_ai.php admin@SERVER_IP:/tmp/lifefirst_upload/
scp module_4_messenger_ai.php admin@SERVER_IP:/tmp/lifefirst_upload/
scp module_6_notification_ai.php admin@SERVER_IP:/tmp/lifefirst_upload/
```

Or use **WinSCP/FileZilla** to upload all files to `/tmp/lifefirst_upload/`

### 3. Run Main Setup

SSH into your server:
```bash
ssh admin@SERVER_IP
```

Run the setup:
```bash
cd /tmp/lifefirst_upload
chmod +x lifefirst_setup.sh
sudo ./lifefirst_setup.sh
```

Wait 5-10 minutes for installation.

### 4. Deploy Your Modules

```bash
cd /tmp/lifefirst_upload
chmod +x deploy_modules.sh
sudo ./deploy_modules.sh
```

When prompted, enter MySQL root password (default: `LifeFirst2024!`)

### 5. Configure API Keys

Edit each AI module and add your Claude API key:

**Schedule AI:**
```bash
sudo nano /var/www/html/lifefirst/ai/ai_schedule.php
```
Find line 25 and replace:
```php
define('CLAUDE_API_KEY', 'sk-ant-api03-YOUR-ACTUAL-KEY-HERE');
```

**Messenger AI:**
```bash
sudo nano /var/www/html/lifefirst/ai/ai_messenger.php
```
Line 18 - same change.

**Notification AI:**
```bash
sudo nano /var/www/html/lifefirst/ai/ai_notifications.php
```
Line 19 - same change.

### 6. Test Your System

**Web Browser Test:**
```
http://YOUR_SERVER_IP/lifefirst/
```

**API Health Check:**
```bash
curl http://YOUR_SERVER_IP/lifefirst/api.php?action=health
```

**Full Test:**
```bash
curl -X POST http://YOUR_SERVER_IP/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "Authorization: your_secret_token_change_me_12345" \
  -d '{"username": "you", "message": "Am I free at 3pm today?", "action": "query"}'
```

---

## 🔑 CRITICAL: THINGS YOU MUST CHANGE

### 1. Claude API Key
**Where**: All 3 AI module files
**Get it from**: https://console.anthropic.com/
**Line to change**: Look for `CLAUDE_API_KEY`

### 2. API Secret Token
**Where**: `/var/www/html/lifefirst/api.php`
**Line ~40**: 
```php
define('API_SECRET', 'your_secret_token_change_me_12345');
```
Change to something secure like: `LifeFirst_Secret_2024_XyZ123!`

### 3. MySQL Passwords (Optional but recommended)
Default passwords in setup script:
- Root: `LifeFirst2024!`
- App User: `LifeFirst_DB_2024!`

To change, edit `lifefirst_setup.sh` before running it.

---

## 📱 CONNECTING YOUR ANDROID PHONES

Once the server is running, your Android app needs:

### Configuration Settings:
```
Server URL: http://YOUR_SERVER_IP/lifefirst/api.php
API Token: your_secret_token_change_me_12345 (whatever you set)
Username: "you" or "laurie"
```

### Test Commands to Try:
```
"Am I free at 3pm today?"           → Schedule AI
"Ask Laurie what pickles she wants" → Messenger AI
"Schedule a meeting at 4pm"         → Schedule AI
"Do I have any conflicts?"          → Schedule AI
```

---

## 🐛 TROUBLESHOOTING

### Module 5 or 7 Errors
**Error**: "Memory AI module not yet installed"
**Solution**: This is normal. Those modules aren't created yet. System works without them.

### Database Connection Failed
**Solution**:
```bash
sudo systemctl restart mysql
mysql -u root -p
# Enter password: LifeFirst2024!
SHOW DATABASES;
```

### Can't Reach Server from Phone
**Solution**: 
```bash
# Check firewall
sudo ufw status
sudo ufw allow 80/tcp

# Check Apache
sudo systemctl status apache2
sudo systemctl restart apache2
```

### Claude API Error
**Solution**: Verify your API key:
- Must start with `sk-ant-api03-`
- No extra spaces
- Same key in all 3 AI modules
- Has credits available

---

## 🎯 WHAT WORKS NOW VS. LATER

### ✅ Working NOW (with current modules):
- Schedule checking and management
- Cross-phone messaging (ask/answer questions)
- Urgent notifications with escalation
- Database storage of all interactions
- API routing and intent detection

### ⏳ Need Modules 5 & 7 for:
- Learning user preferences
- Remembering past conversations
- General conversation (non-specific queries)
- Voice command fallback handler

### 📱 Need Module 8 for:
- Android app interface
- Voice input/output
- Push notifications
- Mobile UI

---

## 💡 RECOMMENDED DEPLOYMENT PATH

### Phase 1: Deploy NOW ✅
1. Install Ubuntu Server
2. Run setup scripts
3. Deploy modules 1-4 & 6
4. Add Claude API key
5. Test with curl/browser

### Phase 2: Build Missing Modules
1. Create Module 5 (Memory AI)
2. Create Module 7 (Voice AI)
3. Deploy to server
4. Test enhanced features

### Phase 3: Android App
1. Build Module 8 (Android app)
2. Install on both phones
3. Configure server connection
4. Start using with voice!

---

## 📊 SYSTEM REQUIREMENTS

### Server (Ubuntu VM):
- **OS**: Ubuntu Server 24.04.3 LTS
- **RAM**: 4 GB minimum
- **CPU**: 2 cores
- **Disk**: 40 GB
- **Network**: Bridged or NAT with port forwarding

### Client (Android Phones):
- **OS**: Android 8.0+ 
- **Network**: Same network as server OR internet access
- **Permissions**: Microphone, notifications

---

## 🎉 YOU'RE READY TO START!

**What you have is enough to deploy and test the core functionality!**

The missing modules (5, 7, 8) can be added later. Your bond is **75% complete** and fully functional for:
- Schedule management
- Cross-phone communication  
- Urgent notifications

**Let's get it running! Follow the INSTALLATION_GUIDE.md** 🚀

---

## 📞 NEED HELP?

If you get stuck:
1. Check the INSTALLATION_GUIDE.md
2. Review server logs: `/var/log/apache2/error.log`
3. Test database: `mysql -u root -p lifefirst`
4. Verify files are in: `/var/www/html/lifefirst/`
5. Check permissions: `ls -la /var/www/html/lifefirst/`

**Remember**: Modules 5 and 7 being missing is OK for now!
