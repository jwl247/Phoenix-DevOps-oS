# BUDGET KEEPER AI - ANDROID INTEGRATION GUIDE

## 🎯 QUICK REFERENCE

This guide shows how to integrate Budget Keeper AI into your Android app.

---

## 📱 API ENDPOINTS

Base URL: `http://your-server:8888/lifefirst/api.php`

All requests require:
- Header: `X-API-Secret: YOUR_API_SECRET`
- Method: `POST`
- Content-Type: `application/json`

---

## 🔌 CORE ENDPOINTS

### 1. Get User Settings
```json
{
  "action": "budget",
  "subaction": "get_settings",
  "user_id": 1
}
```
**Returns:** Permission level, thresholds, partner info

---

### 2. Get Categories
```json
{
  "action": "budget",
  "subaction": "get_categories",
  "user_id": 1
}
```
**Returns:** All budget categories with spent/remaining amounts

---

### 3. Add Expense
```json
{
  "action": "budget",
  "subaction": "add_expense",
  "user_id": 1,
  "category_id": 3,
  "amount": 45.99,
  "merchant": "Walmart",
  "description": "Groceries",
  "expense_date": "2025-10-28"
}
```
**Returns:** `expense_id`, auto-categorized if Level 2+

---

### 4. Check Purchase (CRITICAL - Levels 3-5)
```json
{
  "action": "budget",
  "subaction": "check_purchase",
  "user_id": 1,
  "amount": 150.00,
  "merchant": "Best Buy",
  "category_id": 6
}
```

**Returns:**
```json
{
  "success": true,
  "allowed": true,
  "warnings": [
    {
      "type": "over_budget",
      "message": "This will exceed your Shopping budget by $50",
      "severity": "high"
    }
  ],
  "requires_action": false,
  "action_type": null
}
```

**If Level 5 violation:**
```json
{
  "requires_action": true,
  "action_type": "call_partner",
  "action_message": "You must call Laurie before this purchase"
}
```

---

### 5. Get Bills
```json
{
  "action": "budget",
  "subaction": "get_bills",
  "user_id": 1
}
```
**Returns:** All bills with due dates, overdue flags

---

### 6. Mark Bill Paid
```json
{
  "action": "budget",
  "subaction": "mark_bill_paid",
  "user_id": 1,
  "bill_id": 5
}
```
**Auto-adds expense and updates next due date**

---

### 7. Get Spending Summary
```json
{
  "action": "budget",
  "subaction": "get_spending_summary",
  "user_id": 1,
  "month_year": "2025-10"
}
```
**Returns:** Total spent, budget remaining, per-category breakdown

---

### 8. Get Budget Health
```json
{
  "action": "budget",
  "subaction": "get_budget_health",
  "user_id": 1
}
```
**Returns:** Health score (0-100), grade (A-F), issues

---

### 9. Get AI Insights (Level 2+)
```json
{
  "action": "budget",
  "subaction": "get_ai_insights",
  "user_id": 1
}
```
**Returns:** Claude's analysis and recommendations

---

## 🎬 INTEGRATION WORKFLOWS

### Workflow 1: App Launch
```kotlin
suspend fun initializeBudget(userId: Int) {
    // Get user's permission level
    val settings = api.getSettings(userId)
    permissionLevel = settings.permissionLevel
    
    // Load categories for UI
    val categories = api.getCategories(userId)
    updateCategoriesUI(categories)
    
    // Check for upcoming bills
    val bills = api.getBills(userId)
    val dueSoon = bills.filter { it.daysUntilDue <= 3 }
    if (dueSoon.isNotEmpty()) {
        showBillReminders(dueSoon)
    }
}
```

---

### Workflow 2: Manual Expense Entry
```kotlin
fun addExpense(
    userId: Int,
    amount: Double,
    merchant: String,
    categoryId: Int?
) {
    val response = api.addExpense(
        userId = userId,
        amount = amount,
        merchant = merchant,
        categoryId = categoryId, // null if Level 2+ (AI auto-categorizes)
        expenseDate = LocalDate.now().toString()
    )
    
    // Update UI
    showSuccessMessage("Expense added!")
    refreshCategories()
}
```

---

### Workflow 3: Pre-Purchase Check (CRITICAL)
```kotlin
suspend fun beforeCheckout(
    userId: Int,
    totalAmount: Double,
    merchant: String
): PurchaseDecision {
    // Skip if Level 1-2
    if (permissionLevel < 3) {
        return PurchaseDecision.Allowed
    }
    
    // Check with server
    val response = api.checkPurchase(
        userId = userId,
        amount = totalAmount,
        merchant = merchant
    )
    
    // Show warnings
    if (response.warnings.isNotEmpty()) {
        showWarningsDialog(response.warnings)
    }
    
    // Level 5: Enforce actions
    if (response.requiresAction) {
        when (response.actionType) {
            "call_partner" -> {
                return PurchaseDecision.RequiresCall(
                    message = response.actionMessage,
                    partnerPhone = getPartnerPhone()
                )
            }
            "cooling_off" -> {
                return PurchaseDecision.Delayed(
                    minutes = response.delayMinutes,
                    message = response.actionMessage
                )
            }
        }
    }
    
    return PurchaseDecision.AllowedWithWarnings(response.warnings)
}

sealed class PurchaseDecision {
    object Allowed : PurchaseDecision()
    data class AllowedWithWarnings(val warnings: List<Warning>) : PurchaseDecision()
    data class RequiresCall(val message: String, val partnerPhone: String) : PurchaseDecision()
    data class Delayed(val minutes: Int, val message: String) : PurchaseDecision()
}
```

---

### Workflow 4: Level 5 Call Partner Flow
```kotlin
fun handleCallPartnerRequired(partnerPhone: String, purchaseDetails: PurchaseDetails) {
    AlertDialog.Builder(context)
        .setTitle("⚠️ Partner Approval Required")
        .setMessage("You need to call Laurie before this $${purchaseDetails.amount} purchase at ${purchaseDetails.merchant}")
        .setPositiveButton("Call Now") { _, _ ->
            // Make phone call
            val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:$partnerPhone"))
            startActivity(intent)
            
            // Track that call was made
            trackCallMade(purchaseDetails)
        }
        .setNegativeButton("Cancel Purchase") { dialog, _ ->
            dialog.dismiss()
            cancelPurchase()
        }
        .setNeutralButton("Override (Will Log)") { _, _ ->
            showOverrideConfirmation(purchaseDetails)
        }
        .setCancelable(false)
        .show()
}

fun trackCallMade(details: PurchaseDetails) {
    // Log to violations table that user made the call
    api.resolveViolation(
        violationId = details.violationId,
        response = "called_partner",
        notes = "User called partner before purchase"
    )
}
```

---

### Workflow 5: Cooling-Off Period (Level 5)
```kotlin
fun startCoolingOffTimer(minutes: Int, purchaseDetails: PurchaseDetails) {
    val endTime = System.currentTimeMillis() + (minutes * 60 * 1000)
    
    // Show blocking dialog
    val dialog = AlertDialog.Builder(context)
        .setTitle("⏱️ Cooling-Off Period")
        .setMessage("Please wait $minutes minutes before completing this purchase.\n\nThis gives you time to reconsider.")
        .setCancelable(false)
        .create()
    
    dialog.show()
    
    // Update timer every second
    object : CountDownTimer(minutes * 60 * 1000L, 1000) {
        override fun onTick(millisUntilFinished: Long) {
            val secondsLeft = millisUntilFinished / 1000
            val minutesLeft = secondsLeft / 60
            val seconds = secondsLeft % 60
            
            dialog.setMessage(
                "Time remaining: ${minutesLeft}m ${seconds}s\n\n" +
                "Use this time to reconsider if you really need this."
            )
        }
        
        override fun onFinish() {
            dialog.dismiss()
            showPurchaseAllowedDialog(purchaseDetails)
        }
    }.start()
}
```

---

## 🎨 UI COMPONENTS

### Budget Overview Card
```kotlin
@Composable
fun BudgetHealthCard(health: BudgetHealth) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = when (health.grade) {
                "A" -> Color(0xFF4CAF50) // Green
                "B" -> Color(0xFF8BC34A) // Light Green
                "C" -> Color(0xFFFFC107) // Yellow
                "D" -> Color(0xFFFF9800) // Orange
                else -> Color(0xFFF44336) // Red
            }
        )
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("Budget Health: ${health.grade}", style = MaterialTheme.typography.headlineMedium)
            Text("Score: ${health.score}/100")
            
            LinearProgressIndicator(
                progress = health.percentUsed / 100f,
                modifier = Modifier.fillMaxWidth()
            )
            
            Text("${health.percentUsed}% of budget used")
            Text("$${health.totalSpent} / $${health.totalBudget}")
            
            if (health.issues.isNotEmpty()) {
                Spacer(modifier = Modifier.height(8.dp))
                Text("⚠️ Issues:", fontWeight = FontWeight.Bold)
                health.issues.forEach { issue ->
                    Text("• $issue", fontSize = 14.sp)
                }
            }
        }
    }
}
```

---

### Category List Item
```kotlin
@Composable
fun CategoryItem(category: BudgetCategory) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = category.categoryName,
                    style = MaterialTheme.typography.titleMedium
                )
                LinearProgressIndicator(
                    progress = category.percentUsed / 100f,
                    modifier = Modifier.fillMaxWidth()
                )
                Text(
                    text = "${category.percentUsed}% used",
                    style = MaterialTheme.typography.bodySmall
                )
            }
            
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = "$${category.spentThisMonth}",
                    style = MaterialTheme.typography.titleLarge,
                    color = if (category.percentUsed > 100) Color.Red else Color.Black
                )
                Text(
                    text = "of $${category.monthlyLimit}",
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
    }
}
```

---

### Bill Reminder Notification
```kotlin
fun showBillReminder(bill: Bill) {
    val notification = NotificationCompat.Builder(context, BUDGET_CHANNEL_ID)
        .setSmallIcon(R.drawable.ic_bill)
        .setContentTitle("💸 Bill Due Soon")
        .setContentText("${bill.billName} - $${bill.amount} due in ${bill.daysUntilDue} days")
        .setPriority(NotificationCompat.PRIORITY_HIGH)
        .setAutoCancel(true)
        .setContentIntent(
            PendingIntent.getActivity(
                context,
                0,
                Intent(context, BillsActivity::class.java),
                PendingIntent.FLAG_IMMUTABLE
            )
        )
        .build()
    
    notificationManager.notify(bill.id, notification)
}
```

---

## 🔔 BACKGROUND TASKS

### Daily Bill Check (WorkManager)
```kotlin
class BillCheckWorker(context: Context, params: WorkerParameters) 
    : CoroutineWorker(context, params) {
    
    override suspend fun doWork(): Result {
        val userId = inputData.getInt("user_id", 0)
        
        val bills = api.getBills(userId)
        val dueSoon = bills.filter { it.daysUntilDue <= 3 && it.daysUntilDue >= 0 }
        
        dueSoon.forEach { bill ->
            showBillReminder(bill)
        }
        
        return Result.success()
    }
}

// Schedule daily check
fun scheduleDailyBillCheck(userId: Int) {
    val workRequest = PeriodicWorkRequestBuilder<BillCheckWorker>(1, TimeUnit.DAYS)
        .setInputData(workDataOf("user_id" to userId))
        .build()
    
    WorkManager.getInstance(context).enqueueUniquePeriodicWork(
        "bill_check_$userId",
        ExistingPeriodicWorkPolicy.KEEP,
        workRequest
    )
}
```

---

## 🔐 PERMISSION LEVEL UI

### Settings Screen
```kotlin
@Composable
fun BudgetPermissionSettings(
    currentLevel: Int,
    onLevelChange: (Int) -> Unit
) {
    Column {
        Text("Budget Management Level", style = MaterialTheme.typography.headlineSmall)
        
        RadioGroup(
            options = listOf(
                1 to "Manual Only - I enter everything",
                2 to "Basic AI - Help categorize",
                3 to "Active Manager - Warn me before purchases",
                4 to "Full Partnership - AI manages with me",
                5 to "Total Accountability - Maximum oversight"
            ),
            selected = currentLevel,
            onSelect = onLevelChange
        )
        
        if (currentLevel >= 4) {
            Spacer(modifier = Modifier.height(16.dp))
            Text("Partner Settings", fontWeight = FontWeight.Bold)
            PartnerSelector()
            
            if (currentLevel == 5) {
                Text("Level 5: Requires partner approval for purchases over threshold")
                ThresholdSlider()
            }
        }
    }
}
```

---

## ⚡ IMPORTANT NOTES

1. **ALWAYS call `check_purchase` before checkout (Levels 3-5)**
   - This is NOT optional for Level 5
   - User cannot proceed if `requires_action` is true

2. **Handle partner notifications properly**
   - Use Notification AI module to send to partner
   - Track when notifications are sent

3. **Log ALL overrides**
   - If user bypasses warnings, log it
   - Required for accountability reports

4. **Update spending patterns**
   - API handles this automatically on `add_expense`

5. **Cache categories locally**
   - They don't change often
   - Refresh once per day or after edits

---

## 🐛 ERROR HANDLING

```kotlin
try {
    val response = api.checkPurchase(userId, amount, merchant)
    // Handle response
} catch (e: NetworkException) {
    // No internet - allow purchase but log locally
    // Sync when connection returns
    logOfflineExpense(amount, merchant)
} catch (e: ApiException) {
    // Server error - show error but don't block user
    showError("Budget check failed. Purchase allowed.")
}
```

---

## 📊 TESTING CHECKLIST

- [ ] Level 1: Manual entry works
- [ ] Level 2: AI categorization works
- [ ] Level 3: Warnings show before checkout
- [ ] Level 4: Partner integration works
- [ ] Level 5: Call requirement enforced
- [ ] Level 5: Cooling-off timer works
- [ ] Bill reminders show on time
- [ ] Spending summary displays correctly
- [ ] Health score calculates properly
- [ ] Offline mode syncs when online

---

## 🎉 YOU'RE READY!

Integrate these endpoints and workflows into your Android app and Budget Keeper will be fully functional!

**Next:** Set up Cloudflare tunnel so the app works outside your network.
