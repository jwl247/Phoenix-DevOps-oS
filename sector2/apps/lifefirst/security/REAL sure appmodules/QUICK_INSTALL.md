# 🚀 LIFE FIRST AI - QUICK TRANSFER & INSTALL GUIDE

## 📦 ONE FILE TO RULE THEM ALL!

**lifefirst_complete_package.tar.gz** - Everything you need in one compressed file!

---

## 📥 STEP 1: TRANSFER TO YOUR SERVER

### Method A: SCP (From Windows PowerShell/Command Prompt)

```bash
# Replace SERVER_IP with your Ubuntu Server's IP address
scp lifefirst_complete_package.tar.gz admin@SERVER_IP:~/
```

**Example:**
```bash
scp lifefirst_complete_package.tar.gz admin@192.168.1.100:~/
```

### Method B: WinSCP (GUI Method)

1. Download WinSCP: https://winscp.net/
2. Connect to your server:
   - Host: YOUR_SERVER_IP
   - Username: admin (or whatever you created)
   - Password: (your server password)
3. Drag and drop `lifefirst_complete_package.tar.gz` to the home directory

### Method C: FileZilla (GUI Method)

1. Download FileZilla: https://filezilla-project.org/
2. File → Site Manager → New Site
   - Protocol: SFTP
   - Host: YOUR_SERVER_IP
   - Username: admin
   - Password: (your password)
3. Upload `lifefirst_complete_package.tar.gz`

---

## 📂 STEP 2: EXTRACT ON SERVER

SSH into your server:
```bash
ssh admin@YOUR_SERVER_IP
```

Extract the package:
```bash
# Create working directory
mkdir -p ~/lifefirst_install
cd ~/lifefirst_install

# Extract everything
tar -xzf ~/lifefirst_complete_package.tar.gz

# Verify files extracted
ls -lh
```

You should see all 11 files!

---

## ⚡ STEP 3: RUN INSTALLATION (3 COMMANDS)

```bash
# 1. Make scripts executable
chmod +x *.sh

# 2. Run main installer (takes 5-10 minutes)
sudo ./lifefirst_setup.sh

# 3. Deploy your modules (takes 2-3 minutes)
sudo ./deploy_modules.sh
```

When `deploy_modules.sh` asks for MySQL password, enter: **LifeFirst2024!**

---

## 🔑 STEP 4: ADD YOUR CLAUDE API KEY

Edit each AI module file:

```bash
# Schedule AI
sudo nano /var/www/html/lifefirst/ai/ai_schedule.php
# Go to line 25, replace YOUR_CLAUDE_API_KEY_HERE with your actual key
# Save: Ctrl+O, Enter, Ctrl+X

# Messenger AI
sudo nano /var/www/html/lifefirst/ai/ai_messenger.php
# Go to line 18, same replacement
# Save: Ctrl+O, Enter, Ctrl+X

# Notification AI
sudo nano /var/www/html/lifefirst/ai/ai_notifications.php
# Go to line 19, same replacement
# Save: Ctrl+O, Enter, Ctrl+X
```

Your API key format: `sk-ant-api03-...`

---

## ✅ STEP 5: TEST IT!

### Test 1: Web Browser
Open: `http://YOUR_SERVER_IP/lifefirst/`

Should see welcome page!

### Test 2: API Health Check
```bash
curl http://YOUR_SERVER_IP/lifefirst/api.php?action=health
```

Should return JSON with database: true

### Test 3: Full API Test
```bash
curl -X POST http://YOUR_SERVER_IP/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "Authorization: your_secret_token_change_me_12345" \
  -d '{"username": "you", "message": "Am I free at 3pm today?", "action": "query"}'
```

Should get schedule check response!

---

## 🎯 ULTRA-QUICK VERSION (Copy/Paste)

Once file is on server, run these commands:

```bash
mkdir -p ~/lifefirst_install && cd ~/lifefirst_install
tar -xzf ~/lifefirst_complete_package.tar.gz
chmod +x *.sh
sudo ./lifefirst_setup.sh
sudo ./deploy_modules.sh
```

Then add Claude API key to the 3 AI module files. DONE! ✅

---

## 📊 WHAT'S IN THE PACKAGE

```
lifefirst_complete_package.tar.gz (29 KB compressed)
│
└── Contains:
    ├── lifefirst_setup.sh              (Main installer)
    ├── deploy_modules.sh               (Module deployer)
    ├── module_1_database.sql           (Database schema)
    ├── module_3_schedule_ai.php        (Schedule AI)
    ├── module_4_messenger_ai.php       (Messenger AI)
    ├── module_6_notification_ai.php    (Notification AI)
    ├── START_HERE.md                   (Quick start)
    ├── README.md                       (Full docs)
    ├── INSTALLATION_GUIDE.md           (Detailed guide)
    ├── DEPLOYMENT_CHECKLIST.md         (Checklist)
    └── FILE_STRUCTURE.txt              (System layout)
```

---

## 🐛 TROUBLESHOOTING

### Can't Connect via SCP
```bash
# Make sure SSH is running on server
sudo systemctl status ssh
sudo systemctl start ssh
```

### Extract Error
```bash
# Make sure you're in the right directory
cd ~
tar -xzf lifefirst_complete_package.tar.gz -C ~/lifefirst_install/
```

### Permission Denied
```bash
# Add sudo before commands
sudo chmod +x *.sh
```

---

## 📝 SAVE THESE CREDENTIALS

After installation completes, write down:

- **Server IP**: ________________
- **MySQL Root Password**: LifeFirst2024!
- **Database User**: lifefirst_user
- **Database Password**: LifeFirst_DB_2024!
- **API Secret**: your_secret_token_change_me_12345 (change this!)
- **Claude API Key**: sk-ant-api03-_______________

---

## 🎉 INSTALLATION TIMELINE

1. **Transfer file** (1-2 min)
2. **Extract** (10 seconds)
3. **Run lifefirst_setup.sh** (7-10 min)
4. **Run deploy_modules.sh** (2-3 min)
5. **Add API key** (5 min)
6. **Test** (3 min)

**Total: ~20-25 minutes from transfer to working system!**

---

## 🚀 READY TO GO!

Transfer `lifefirst_complete_package.tar.gz` to your server and follow the 5 steps above.

Your Life First AI bond will be live in under 30 minutes! 🤖🤝🤖
