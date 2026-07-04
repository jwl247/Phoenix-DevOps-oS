# BUDGET KEEPER AI - ONE-COMMAND INSTALL

## 🚀 QUICK START

Just like the original Life First installer, this **ONE SCRIPT** installs everything!

### What It Does:
✅ Creates all 8 database tables  
✅ Deploys PHP module  
✅ Updates API router automatically  
✅ Tests the installation  
✅ Shows you results  

---

## 📦 INSTALLATION

### Step 1: Upload to Server

**Option A: USB Drive (Easiest)**
```bash
# On Windows PC, copy to USB
# Then on server:
cp /media/usb/install_budget_keeper.sh /tmp/
```

**Option B: SCP**
```bash
# From your Windows PC:
scp install_budget_keeper.sh user@your-server:/tmp/
```

---

### Step 2: Run Installer

**SSH into your server:**
```bash
ssh your-user@your-server-ip
```

**Run the installer:**
```bash
cd /tmp
chmod +x install_budget_keeper.sh
sudo ./install_budget_keeper.sh
```

**That's it!** The script will:
1. Ask for confirmation
2. Check prerequisites (MySQL, Apache)
3. Install database schema
4. Deploy PHP module
5. Update API router
6. Restart Apache
7. Run tests
8. Show you the results

---

## ✅ VERIFICATION

After installation completes, test it:

```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{
    "action": "budget",
    "subaction": "get_settings",
    "user_id": 1
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "settings": {
    "id": 1,
    "user_id": 1,
    "permission_level": 1,
    "partner_user_id": null,
    "accountability_threshold": 100.00,
    ...
  }
}
```

---

## 🎯 NEXT STEPS

### 1. Configure Your Account (Level 5)
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{
    "action": "budget",
    "subaction": "update_settings",
    "user_id": 1,
    "permission_level": 5,
    "partner_user_id": 2,
    "accountability_threshold": 100.00,
    "require_partner_call": true,
    "cooling_off_minutes": 15,
    "enable_realtime_warnings": true
  }'
```

### 2. Add Your First Expense
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -d '{
    "action": "budget",
    "subaction": "add_expense",
    "user_id": 1,
    "category_id": 1,
    "amount": 50.00,
    "merchant": "Walmart",
    "description": "Groceries"
  }'
```

### 3. Check Your Budget Health
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -d '{
    "action": "budget",
    "subaction": "get_budget_health",
    "user_id": 1
  }'
```

### 4. Test Purchase Checking (Level 3+)
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -d '{
    "action": "budget",
    "subaction": "check_purchase",
    "user_id": 1,
    "amount": 150.00,
    "merchant": "Best Buy",
    "category_id": 7
  }'
```

---

## 🐛 TROUBLESHOOTING

### "MySQL connection failed"
**Fix:** Check database credentials in the script
```bash
DB_NAME="lifefirst_db"
DB_USER="lifefirst_user"
DB_PASS="LifeFirst_DB_2024!"
```

### "Apache not running"
**Fix:**
```bash
sudo systemctl start apache2
sudo systemctl status apache2
```

### "API router not found"
**Fix:** Make sure Life First core modules are installed first
```bash
ls -la /var/www/html/lifefirst/api.php
```

### Test failed: "Unknown action"
**Fix:** API router might not be updated. Manually add:
```bash
sudo nano /var/www/html/lifefirst/api.php

# Add this with other requires:
require_once __DIR__ . '/budget_keeper.php';

# Add this in switch statement:
case 'budget':
    $result = handleBudgetKeeperRequest($db, $CLAUDE_API_KEY, $data['subaction'], $data);
    break;
```

---

## 📊 CHECKING DATABASE

**View tables:**
```bash
mysql -u lifefirst_user -p lifefirst_db -e "SHOW TABLES LIKE '%budget%';"
```

**Check your categories:**
```bash
mysql -u lifefirst_user -p lifefirst_db -e "
SELECT category_name, monthly_limit, is_essential 
FROM budget_categories 
WHERE user_id = 1;
"
```

**View your expenses:**
```bash
mysql -u lifefirst_user -p lifefirst_db -e "
SELECT expense_date, amount, merchant, description 
FROM expenses 
WHERE user_id = 1 
ORDER BY expense_date DESC 
LIMIT 10;
"
```

---

## 🔄 UNINSTALL (If Needed)

**To remove Budget Keeper:**
```bash
# Remove PHP module
sudo rm /var/www/html/lifefirst/budget_keeper.php

# Remove from API router
sudo nano /var/www/html/lifefirst/api.php
# Delete the lines related to budget_keeper

# Drop database tables (CAREFUL!)
mysql -u lifefirst_user -p lifefirst_db -e "
DROP TABLE IF EXISTS budget_adjustments;
DROP TABLE IF EXISTS spending_patterns;
DROP TABLE IF EXISTS accountability_violations;
DROP TABLE IF EXISTS accountability_rules;
DROP TABLE IF EXISTS bill_reminders;
DROP TABLE IF EXISTS expenses;
DROP TABLE IF EXISTS budget_categories;
DROP TABLE IF EXISTS user_budget_settings;
"

# Restart Apache
sudo systemctl restart apache2
```

---

## 🎉 SUCCESS!

Once installed, you have:
- ✅ 8 database tables
- ✅ Full Budget Keeper AI module
- ✅ 5 permission levels
- ✅ Ready for Android integration

**The script is fully automated - just run it and you're done!**

Next: Set up Cloudflare tunnel so your Android app can access the API from anywhere! 🚀
