# BUDGET KEEPER AI (MODULE 8) - INSTALLATION GUIDE
# Life First AI System

## 📋 OVERVIEW

Budget Keeper AI is Module 8 of the Life First AI system. It provides comprehensive expense tracking and budget management with 5 adjustable permission levels:

**Level 1: Manual Only** - User enters everything, no AI involvement
**Level 2: Basic AI Assistant** - AI categorizes expenses and suggests budgets  
**Level 3: Active Budget Manager** - Real-time warnings before purchases
**Level 4: Full Partnership** - AI actively manages budget with user
**Level 5: Total Accountability** - Maximum friction & partner notifications

---

## 🚀 INSTALLATION STEPS

### Step 1: Upload Files to Server

Upload these files to your Ubuntu Server VM:
- `budget_keeper_schema.sql` (database tables)
- `budget_keeper.php` (PHP module)

**On your Windows PC:**
```bash
# Copy files to USB or use SCP
scp budget_keeper_schema.sql your-user@server-ip:/tmp/
scp budget_keeper.php your-user@server-ip:/tmp/
```

---

### Step 2: Import Database Schema

**SSH into your server:**
```bash
ssh your-user@server-ip
```

**Import the schema:**
```bash
mysql -u lifefirst_user -p lifefirst_db < /tmp/budget_keeper_schema.sql
```

Enter password: `LifeFirst_DB_2024!`

**Verify tables were created:**
```bash
mysql -u lifefirst_user -p lifefirst_db -e "SHOW TABLES;"
```

You should see 8 new tables:
- user_budget_settings
- budget_categories
- expenses
- bill_reminders
- accountability_rules
- accountability_violations
- spending_patterns
- budget_adjustments

---

### Step 3: Deploy PHP Module

**Move the PHP file to your Life First directory:**
```bash
sudo cp /tmp/budget_keeper.php /var/www/html/lifefirst/
sudo chown www-data:www-data /var/www/html/lifefirst/budget_keeper.php
sudo chmod 644 /var/www/html/lifefirst/budget_keeper.php
```

---

### Step 4: Update API Router

**Edit your main API router to include Budget Keeper:**
```bash
sudo nano /var/www/html/lifefirst/api.php
```

**Add this line near the top with other module includes:**
```php
require_once __DIR__ . '/budget_keeper.php';
```

**Add this case to your switch statement (around line 80-100):**
```php
case 'budget':
    $result = handleBudgetKeeperRequest($db, $CLAUDE_API_KEY, $data['subaction'], $data);
    break;
```

**Save and exit:** Ctrl+O, Enter, Ctrl+X

---

### Step 5: Initialize User Settings

**For each user, run this to set up their Budget Keeper:**
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

This will:
- Create default budget settings (Level 1)
- Add 10 default categories (Groceries, Gas, etc.)
- Return the user's settings

---

## 🧪 TESTING

### Test 1: Get User Settings
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

### Test 2: Get Categories
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{
    "action": "budget",
    "subaction": "get_categories",
    "user_id": 1
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "categories": [
    {
      "id": 1,
      "category_name": "Groceries",
      "monthly_limit": 600.00,
      "spent_this_month": 0.00,
      "remaining": 600.00,
      "percent_used": 0
    },
    ...
  ]
}
```

### Test 3: Add an Expense (Manual Entry)
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{
    "action": "budget",
    "subaction": "add_expense",
    "user_id": 1,
    "category_id": 1,
    "amount": 45.67,
    "merchant": "Walmart",
    "description": "Weekly groceries",
    "expense_date": "2025-10-28"
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "expense_id": 1,
  "category_id": 1
}
```

### Test 4: Check Purchase (Level 3+ Feature)

**First, upgrade to Level 3:**
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{
    "action": "budget",
    "subaction": "update_settings",
    "user_id": 1,
    "permission_level": 3,
    "enable_realtime_warnings": true
  }'
```

**Then test purchase checking:**
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{
    "action": "budget",
    "subaction": "check_purchase",
    "user_id": 1,
    "amount": 150.00,
    "merchant": "Best Buy",
    "category_id": 6
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "allowed": true,
  "warnings": [
    {
      "type": "over_budget",
      "message": "This purchase will put you $50.00 over budget in Shopping",
      "severity": "high"
    }
  ],
  "requires_action": false
}
```

### Test 5: Add a Bill Reminder
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{
    "action": "budget",
    "subaction": "add_bill",
    "user_id": 1,
    "bill_name": "Electric Bill",
    "amount": 150.00,
    "due_day": 15,
    "frequency": "monthly",
    "next_due_date": "2025-11-15",
    "remind_days_before": 3
  }'
```

### Test 6: Get AI Insights (Level 2+ Feature)

**Upgrade to Level 2:**
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{
    "action": "budget",
    "subaction": "update_settings",
    "user_id": 1,
    "permission_level": 2
  }'
```

**Get insights:**
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{
    "action": "budget",
    "subaction": "get_ai_insights",
    "user_id": 1
  }'
```

---

## 🎯 CONFIGURING PERMISSION LEVELS

### Setting Up Level 5 (Total Accountability)

**Requirements:**
- Partner user must exist in database
- Accountability rules must be defined

**Step 1: Link Partner**
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

**Step 2: Add Accountability Rules**
```bash
# Directly insert into database
mysql -u lifefirst_user -p lifefirst_db -e "
INSERT INTO accountability_rules (user_id, rule_name, rule_type, threshold_amount, action_type) 
VALUES 
(1, 'Large Purchase Approval', 'spending_limit', 100.00, 'require_call'),
(1, 'Entertainment Limit', 'category_restriction', 0, 'notify_partner'),
(1, 'Late Night Spending', 'time_restriction', 0, 'delay');
"
```

---

## 📱 ANDROID INTEGRATION

### Required API Calls from Android App

**1. Initialize Budget on App Launch:**
```kotlin
// Get user settings and categories
budgetApi.getSettings(userId)
budgetApi.getCategories(userId)
```

**2. Before Checkout (Levels 3-5):**
```kotlin
// Check if purchase is allowed
val response = budgetApi.checkPurchase(
    userId = userId,
    amount = totalAmount,
    merchant = merchantName,
    categoryId = categoryId
)

if (response.requiresAction) {
    when (response.actionType) {
        "call_partner" -> showCallPartnerDialog()
        "cooling_off" -> startCoolingOffTimer(response.delayMinutes)
    }
}
```

**3. After Purchase:**
```kotlin
// Log expense
budgetApi.addExpense(
    userId = userId,
    amount = amount,
    merchant = merchant,
    categoryId = categoryId,
    wasWarned = wasWarned,
    warningOverridden = userOverrode
)
```

**4. Bill Reminders:**
```kotlin
// Check daily for upcoming bills
val bills = budgetApi.getBills(userId)
bills.filter { it.daysUntilDue <= 3 }.forEach { bill ->
    showBillReminderNotification(bill)
}
```

---

## 🔧 CUSTOMIZATION

### Adjusting Default Categories

**Edit the schema file before importing:**
```sql
-- Modify these values in budget_keeper_schema.sql
INSERT INTO budget_categories (user_id, category_name, monthly_limit, is_essential) VALUES
(1, 'Custom Category', 500.00, FALSE);
```

### Changing Permission Level Behaviors

**Edit budget_keeper.php, function checkPurchase():**
```php
// Line ~600 - Adjust threshold for warnings
if ($new_total > ($category['monthly_limit'] * 0.8)) {
    // Warning at 80% instead of 100%
}
```

---

## 🐛 TROUBLESHOOTING

### Issue: "AI insights require permission level 2 or higher"
**Solution:** Upgrade user's permission level:
```bash
curl -X POST http://localhost:8888/lifefirst/api.php \
  -d '{"action":"budget","subaction":"update_settings","user_id":1,"permission_level":2}'
```

### Issue: Categories not auto-created
**Solution:** Manually trigger initialization:
```bash
mysql -u lifefirst_user -p lifefirst_db < budget_keeper_schema.sql
```

### Issue: Partner notifications not sending
**Solution:** Verify partner_user_id exists and Notification AI is running:
```bash
mysql -u lifefirst_user -p lifefirst_db -e "SELECT id, name FROM users;"
```

### Issue: Claude API calls failing
**Solution:** Check API key in api.php:
```bash
grep "CLAUDE_API_KEY" /var/www/html/lifefirst/api.php
```

---

## 📊 DATABASE MAINTENANCE

### View All Expenses for a User
```bash
mysql -u lifefirst_user -p lifefirst_db -e "
SELECT e.expense_date, e.amount, e.merchant, c.category_name 
FROM expenses e 
LEFT JOIN budget_categories c ON e.category_id = c.id 
WHERE e.user_id = 1 
ORDER BY e.expense_date DESC 
LIMIT 20;
"
```

### Check Budget Health
```bash
mysql -u lifefirst_user -p lifefirst_db -e "
SELECT 
    c.category_name,
    c.monthly_limit,
    COALESCE(SUM(e.amount), 0) as spent,
    (c.monthly_limit - COALESCE(SUM(e.amount), 0)) as remaining
FROM budget_categories c
LEFT JOIN expenses e ON c.id = e.category_id 
    AND DATE_FORMAT(e.expense_date, '%Y-%m') = DATE_FORMAT(NOW(), '%Y-%m')
WHERE c.user_id = 1
GROUP BY c.id;
"
```

### Reset Monthly Budgets
```bash
# Run this at the start of each month (or set up a cron job)
mysql -u lifefirst_user -p lifefirst_db -e "
UPDATE spending_patterns 
SET month_year = DATE_FORMAT(NOW(), '%Y-%m'),
    total_spent = 0,
    transaction_count = 0
WHERE user_id = 1;
"
```

---

## ✅ VERIFICATION CHECKLIST

- [ ] Database schema imported successfully
- [ ] PHP module deployed to /var/www/html/lifefirst/
- [ ] API router updated to include Budget Keeper
- [ ] User settings initialized
- [ ] Default categories created
- [ ] Test expense added successfully
- [ ] Purchase checking works (Level 3)
- [ ] Bill reminders configured
- [ ] AI insights working (Level 2+)
- [ ] Partner linking configured (Level 4-5)
- [ ] Accountability rules created (Level 5)

---

## 🎉 YOU'RE DONE!

Budget Keeper AI (Module 8) is now installed and ready to use!

**Next Steps:**
1. Test all 5 permission levels
2. Configure Jerry's account to Level 5 (Total Accountability with Laurie)
3. Set up your neighbor's account at Level 1 (Manual Only)
4. Integrate with Android app
5. Set up Cloudflare tunnel for external access

**Need Help?**
- Check the troubleshooting section above
- Review API logs: `sudo tail -f /var/log/apache2/error.log`
- Test with curl commands before Android integration

---

**Module 8 Complete! 💰✅**
