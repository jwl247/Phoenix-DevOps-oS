<?php
/**
 * BUDGET KEEPER AI (MODULE 8)
 * Life First AI System
 * 
 * Handles expense tracking, budget management, and financial accountability
 * with 5 adjustable permission levels.
 * 
 * Permission Levels:
 * 1 - Manual Only: User enters everything, no AI
 * 2 - Basic AI Assistant: AI categorizes and suggests
 * 3 - Active Budget Manager: Real-time warnings and adjustments
 * 4 - Full Partnership: AI actively manages budget with user
 * 5 - Total Accountability: Maximum friction and partner notifications
 */

// Prevent direct access
if (!defined('API_ACCESS')) {
    die('Direct access not permitted');
}

class BudgetKeeperAI {
    
    private $db;
    private $claude_api_key;
    private $claude_api_url = 'https://api.anthropic.com/v1/messages';
    
    public function __construct($db_connection, $api_key) {
        $this->db = $db_connection;
        $this->claude_api_key = $api_key;
    }
    
    /**
     * Main handler for Budget Keeper requests
     */
    public function handleRequest($action, $data) {
        switch ($action) {
            // Configuration & Settings
            case 'get_settings':
                return $this->getSettings($data['user_id']);
            case 'update_settings':
                return $this->updateSettings($data);
            
            // Budget Categories
            case 'get_categories':
                return $this->getCategories($data['user_id']);
            case 'create_category':
                return $this->createCategory($data);
            case 'update_category':
                return $this->updateCategory($data);
            case 'delete_category':
                return $this->deleteCategory($data);
            
            // Expenses
            case 'add_expense':
                return $this->addExpense($data);
            case 'get_expenses':
                return $this->getExpenses($data);
            case 'update_expense':
                return $this->updateExpense($data);
            case 'delete_expense':
                return $this->deleteExpense($data);
            
            // Purchase Check (Real-time validation)
            case 'check_purchase':
                return $this->checkPurchase($data);
            
            // Bill Reminders
            case 'get_bills':
                return $this->getBills($data['user_id']);
            case 'add_bill':
                return $this->addBill($data);
            case 'update_bill':
                return $this->updateBill($data);
            case 'mark_bill_paid':
                return $this->markBillPaid($data);
            
            // Reports & Analysis
            case 'get_spending_summary':
                return $this->getSpendingSummary($data);
            case 'get_budget_health':
                return $this->getBudgetHealth($data['user_id']);
            case 'get_ai_insights':
                return $this->getAIInsights($data['user_id']);
            
            // Accountability (Level 4-5)
            case 'get_violations':
                return $this->getViolations($data['user_id']);
            case 'resolve_violation':
                return $this->resolveViolation($data);
            case 'notify_partner':
                return $this->notifyPartner($data);
            
            default:
                return ['success' => false, 'message' => 'Unknown action'];
        }
    }
    
    // =============================================
    // SETTINGS & CONFIGURATION
    // =============================================
    
    private function getSettings($user_id) {
        $stmt = $this->db->prepare("
            SELECT * FROM user_budget_settings 
            WHERE user_id = ?
        ");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        if ($result->num_rows === 0) {
            // Create default settings
            return $this->initializeSettings($user_id);
        }
        
        return ['success' => true, 'settings' => $result->fetch_assoc()];
    }
    
    private function initializeSettings($user_id) {
        $stmt = $this->db->prepare("
            INSERT INTO user_budget_settings (user_id, permission_level) 
            VALUES (?, 1)
        ");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        
        // Create default categories
        $this->createDefaultCategories($user_id);
        
        return $this->getSettings($user_id);
    }
    
    private function createDefaultCategories($user_id) {
        $categories = [
            ['Groceries', 600.00, true, '#27ae60'],
            ['Gas/Transportation', 300.00, true, '#3498db'],
            ['Utilities', 200.00, true, '#f39c12'],
            ['Dining Out', 200.00, false, '#e67e22'],
            ['Entertainment', 100.00, false, '#1abc9c'],
            ['Shopping', 150.00, false, '#34495e'],
            ['Miscellaneous', 100.00, false, '#7f8c8d']
        ];
        
        $stmt = $this->db->prepare("
            INSERT INTO budget_categories 
            (user_id, category_name, monthly_limit, is_essential, color_code) 
            VALUES (?, ?, ?, ?, ?)
        ");
        
        foreach ($categories as $cat) {
            $stmt->bind_param("isdis", $user_id, $cat[0], $cat[1], $cat[2], $cat[3]);
            $stmt->execute();
        }
    }
    
    private function updateSettings($data) {
        $user_id = $data['user_id'];
        $updates = [];
        $types = "";
        $params = [];
        
        $allowed_fields = [
            'permission_level', 'partner_user_id', 'accountability_threshold',
            'require_partner_call', 'cooling_off_minutes', 'enable_email_parsing',
            'enable_realtime_warnings', 'budget_start_day'
        ];
        
        foreach ($allowed_fields as $field) {
            if (isset($data[$field])) {
                $updates[] = "$field = ?";
                $params[] = $data[$field];
                $types .= is_bool($data[$field]) ? "i" : (is_numeric($data[$field]) ? "d" : "s");
            }
        }
        
        if (empty($updates)) {
            return ['success' => false, 'message' => 'No valid fields to update'];
        }
        
        $params[] = $user_id;
        $types .= "i";
        
        $sql = "UPDATE user_budget_settings SET " . implode(", ", $updates) . " WHERE user_id = ?";
        $stmt = $this->db->prepare($sql);
        $stmt->bind_param($types, ...$params);
        $stmt->execute();
        
        return ['success' => true, 'message' => 'Settings updated'];
    }
    
    // =============================================
    // BUDGET CATEGORIES
    // =============================================
    
    private function getCategories($user_id) {
        $stmt = $this->db->prepare("
            SELECT c.*, 
                COALESCE(SUM(e.amount), 0) as spent_this_month
            FROM budget_categories c
            LEFT JOIN expenses e ON c.id = e.category_id 
                AND e.user_id = c.user_id
                AND DATE_FORMAT(e.expense_date, '%Y-%m') = DATE_FORMAT(NOW(), '%Y-%m')
            WHERE c.user_id = ?
            GROUP BY c.id
            ORDER BY c.is_essential DESC, c.category_name
        ");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        $categories = [];
        while ($row = $result->fetch_assoc()) {
            $row['remaining'] = $row['monthly_limit'] - $row['spent_this_month'];
            $row['percent_used'] = $row['monthly_limit'] > 0 
                ? round(($row['spent_this_month'] / $row['monthly_limit']) * 100, 1)
                : 0;
            $categories[] = $row;
        }
        
        return ['success' => true, 'categories' => $categories];
    }
    
    private function createCategory($data) {
        $stmt = $this->db->prepare("
            INSERT INTO budget_categories 
            (user_id, category_name, monthly_limit, is_essential, color_code, icon) 
            VALUES (?, ?, ?, ?, ?, ?)
        ");
        
        $stmt->bind_param(
            "isdiis",
            $data['user_id'],
            $data['category_name'],
            $data['monthly_limit'] ?? 0.00,
            $data['is_essential'] ?? 0,
            $data['color_code'] ?? '#3498db',
            $data['icon'] ?? 'category'
        );
        
        $stmt->execute();
        
        return ['success' => true, 'category_id' => $stmt->insert_id];
    }
    
    private function updateCategory($data) {
        $stmt = $this->db->prepare("
            UPDATE budget_categories 
            SET category_name = ?, monthly_limit = ?, is_essential = ?, color_code = ?
            WHERE id = ? AND user_id = ?
        ");
        
        $stmt->bind_param(
            "sdisii",
            $data['category_name'],
            $data['monthly_limit'],
            $data['is_essential'],
            $data['color_code'],
            $data['category_id'],
            $data['user_id']
        );
        
        $stmt->execute();
        
        return ['success' => true, 'message' => 'Category updated'];
    }
    
    private function deleteCategory($data) {
        // Move expenses to "Miscellaneous" before deleting
        $stmt = $this->db->prepare("
            UPDATE expenses 
            SET category_id = (
                SELECT id FROM budget_categories 
                WHERE user_id = ? AND category_name = 'Miscellaneous' 
                LIMIT 1
            )
            WHERE category_id = ? AND user_id = ?
        ");
        $stmt->bind_param("iii", $data['user_id'], $data['category_id'], $data['user_id']);
        $stmt->execute();
        
        // Now delete the category
        $stmt = $this->db->prepare("
            DELETE FROM budget_categories 
            WHERE id = ? AND user_id = ?
        ");
        $stmt->bind_param("ii", $data['category_id'], $data['user_id']);
        $stmt->execute();
        
        return ['success' => true, 'message' => 'Category deleted'];
    }
    
    // =============================================
    // EXPENSES
    // =============================================
    
    private function addExpense($data) {
        $user_id = $data['user_id'];
        $amount = $data['amount'];
        $merchant = $data['merchant'] ?? null;
        $description = $data['description'] ?? null;
        $expense_date = $data['expense_date'] ?? date('Y-m-d');
        
        // Get user's permission level
        $settings = $this->getSettings($user_id);
        $permission_level = $settings['settings']['permission_level'];
        
        // Auto-categorize if Level 2+
        $category_id = $data['category_id'] ?? null;
        if ($category_id === null && $permission_level >= 2) {
            $category_id = $this->aiCategorizeExpense($user_id, $merchant, $description, $amount);
        }
        
        $stmt = $this->db->prepare("
            INSERT INTO expenses 
            (user_id, category_id, amount, merchant, description, expense_date, entry_method) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ");
        
        $entry_method = $data['entry_method'] ?? 'manual';
        $stmt->bind_param(
            "iidssss",
            $user_id,
            $category_id,
            $amount,
            $merchant,
            $description,
            $expense_date,
            $entry_method
        );
        
        $stmt->execute();
        $expense_id = $stmt->insert_id;
        
        // Update spending patterns
        $this->updateSpendingPatterns($user_id, $category_id, $amount);
        
        return [
            'success' => true,
            'expense_id' => $expense_id,
            'category_id' => $category_id
        ];
    }
    
    private function getExpenses($data) {
        $user_id = $data['user_id'];
        $start_date = $data['start_date'] ?? date('Y-m-01'); // First day of current month
        $end_date = $data['end_date'] ?? date('Y-m-d'); // Today
        
        $stmt = $this->db->prepare("
            SELECT e.*, c.category_name, c.color_code
            FROM expenses e
            LEFT JOIN budget_categories c ON e.category_id = c.id
            WHERE e.user_id = ? 
            AND e.expense_date BETWEEN ? AND ?
            ORDER BY e.expense_date DESC, e.created_at DESC
        ");
        
        $stmt->bind_param("iss", $user_id, $start_date, $end_date);
        $stmt->execute();
        $result = $stmt->get_result();
        
        $expenses = [];
        while ($row = $result->fetch_assoc()) {
            $expenses[] = $row;
        }
        
        return ['success' => true, 'expenses' => $expenses];
    }
    
    private function updateExpense($data) {
        $stmt = $this->db->prepare("
            UPDATE expenses 
            SET category_id = ?, amount = ?, merchant = ?, description = ?, expense_date = ?
            WHERE id = ? AND user_id = ?
        ");
        
        $stmt->bind_param(
            "idsssii",
            $data['category_id'],
            $data['amount'],
            $data['merchant'],
            $data['description'],
            $data['expense_date'],
            $data['expense_id'],
            $data['user_id']
        );
        
        $stmt->execute();
        
        return ['success' => true, 'message' => 'Expense updated'];
    }
    
    private function deleteExpense($data) {
        $stmt = $this->db->prepare("
            DELETE FROM expenses 
            WHERE id = ? AND user_id = ?
        ");
        $stmt->bind_param("ii", $data['expense_id'], $data['user_id']);
        $stmt->execute();
        
        return ['success' => true, 'message' => 'Expense deleted'];
    }
    
    // =============================================
    // PURCHASE CHECKING (Levels 3-5)
    // =============================================
    
    private function checkPurchase($data) {
        $user_id = $data['user_id'];
        $amount = $data['amount'];
        $merchant = $data['merchant'] ?? 'Unknown';
        $category_id = $data['category_id'] ?? null;
        
        // Get user settings
        $settings = $this->getSettings($user_id);
        $permission_level = $settings['settings']['permission_level'];
        $partner_id = $settings['settings']['partner_user_id'];
        $threshold = $settings['settings']['accountability_threshold'];
        $require_call = $settings['settings']['require_partner_call'];
        $cooling_off = $settings['settings']['cooling_off_minutes'];
        
        $response = [
            'success' => true,
            'allowed' => true,
            'warnings' => [],
            'requires_action' => false,
            'action_type' => null
        ];
        
        // Level 1: No checks
        if ($permission_level < 3) {
            return $response;
        }
        
        // Auto-categorize if not provided
        if ($category_id === null) {
            $category_id = $this->aiCategorizeExpense($user_id, $merchant, null, $amount);
        }
        
        // Check if category is over budget
        if ($category_id) {
            $stmt = $this->db->prepare("
                SELECT c.category_name, c.monthly_limit, c.is_essential,
                    COALESCE(SUM(e.amount), 0) as spent_this_month
                FROM budget_categories c
                LEFT JOIN expenses e ON c.id = e.category_id 
                    AND DATE_FORMAT(e.expense_date, '%Y-%m') = DATE_FORMAT(NOW(), '%Y-%m')
                WHERE c.id = ? AND c.user_id = ?
                GROUP BY c.id
            ");
            $stmt->bind_param("ii", $category_id, $user_id);
            $stmt->execute();
            $result = $stmt->get_result();
            $category = $result->fetch_assoc();
            
            if ($category) {
                $new_total = $category['spent_this_month'] + $amount;
                $remaining = $category['monthly_limit'] - $category['spent_this_month'];
                
                // Warning: Over budget
                if ($new_total > $category['monthly_limit']) {
                    $overage = $new_total - $category['monthly_limit'];
                    $response['warnings'][] = [
                        'type' => 'over_budget',
                        'message' => "This purchase will put you $" . number_format($overage, 2) . 
                                   " over budget in {$category['category_name']}",
                        'severity' => $category['is_essential'] ? 'medium' : 'high'
                    ];
                }
                
                // Warning: Low budget remaining
                elseif ($amount > ($remaining * 0.5) && $remaining > 0) {
                    $response['warnings'][] = [
                        'type' => 'low_budget',
                        'message' => "Only $" . number_format($remaining, 2) . 
                                   " remaining in {$category['category_name']} this month",
                        'severity' => 'low'
                    ];
                }
            }
        }
        
        // Check upcoming bills (all levels 3+)
        $upcoming_bills = $this->checkUpcomingBills($user_id);
        if (!empty($upcoming_bills)) {
            $response['warnings'][] = [
                'type' => 'upcoming_bills',
                'message' => "You have bills due soon: " . implode(', ', array_column($upcoming_bills, 'bill_name')),
                'severity' => 'medium',
                'bills' => $upcoming_bills
            ];
        }
        
        // Level 4-5: Check accountability rules
        if ($permission_level >= 4) {
            $violations = $this->checkAccountabilityRules($user_id, $amount, $merchant, $category_id);
            
            foreach ($violations as $violation) {
                $response['warnings'][] = $violation;
                
                // Level 5: Enforce actions
                if ($permission_level === 5) {
                    switch ($violation['action']) {
                        case 'require_call':
                            $response['requires_action'] = true;
                            $response['action_type'] = 'call_partner';
                            $response['action_message'] = "You must call your partner before completing this purchase.";
                            break;
                            
                        case 'delay':
                            $response['requires_action'] = true;
                            $response['action_type'] = 'cooling_off';
                            $response['action_message'] = "Please wait {$cooling_off} minutes before completing this purchase.";
                            $response['delay_minutes'] = $cooling_off;
                            break;
                            
                        case 'notify_partner':
                            // Send notification immediately
                            $this->notifyPartnerAboutPurchase($user_id, $partner_id, $amount, $merchant);
                            $response['warnings'][] = [
                                'type' => 'partner_notified',
                                'message' => "Your partner has been notified of this purchase.",
                                'severity' => 'high'
                            ];
                            break;
                    }
                }
            }
            
            // Log violation if any rules were triggered
            if (!empty($violations) && $permission_level === 5) {
                $this->logViolation($user_id, $violations, $amount, $merchant);
            }
        }
        
        return $response;
    }
    
    private function checkUpcomingBills($user_id) {
        $stmt = $this->db->prepare("
            SELECT bill_name, amount, next_due_date,
                DATEDIFF(next_due_date, CURDATE()) as days_until_due
            FROM bill_reminders
            WHERE user_id = ? 
            AND is_active = 1
            AND next_due_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
            ORDER BY next_due_date
        ");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        $bills = [];
        while ($row = $result->fetch_assoc()) {
            $bills[] = $row;
        }
        
        return $bills;
    }
    
    private function checkAccountabilityRules($user_id, $amount, $merchant, $category_id) {
        $violations = [];
        
        $stmt = $this->db->prepare("
            SELECT * FROM accountability_rules
            WHERE user_id = ? AND is_active = 1
            AND (
                (rule_type = 'spending_limit' AND ? >= threshold_amount)
                OR (rule_type = 'category_restriction' AND category_id = ?)
                OR (rule_type = 'merchant_block' AND ? LIKE CONCAT('%', merchant_pattern, '%'))
            )
        ");
        $stmt->bind_param("idis", $user_id, $amount, $category_id, $merchant);
        $stmt->execute();
        $result = $stmt->get_result();
        
        while ($rule = $result->fetch_assoc()) {
            $violations[] = [
                'type' => 'rule_violation',
                'rule_id' => $rule['id'],
                'rule_name' => $rule['rule_name'],
                'message' => "This purchase violates your '{$rule['rule_name']}' rule",
                'severity' => 'critical',
                'action' => $rule['action_type']
            ];
        }
        
        return $violations;
    }
    
    private function notifyPartnerAboutPurchase($user_id, $partner_id, $amount, $merchant) {
        if (!$partner_id) return;
        
        // Get user name
        $stmt = $this->db->prepare("SELECT name FROM users WHERE id = ?");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $user = $stmt->get_result()->fetch_assoc();
        
        // Create notification using Notification AI
        $message = "{$user['name']} is about to spend $" . number_format($amount, 2) . " at {$merchant}";
        
        $stmt = $this->db->prepare("
            INSERT INTO pending_notifications 
            (user_id, notification_type, message, priority, requires_response)
            VALUES (?, 'budget_alert', ?, 'high', 1)
        ");
        $stmt->bind_param("is", $partner_id, $message);
        $stmt->execute();
    }
    
    private function logViolation($user_id, $violations, $amount, $merchant) {
        foreach ($violations as $violation) {
            $stmt = $this->db->prepare("
                INSERT INTO accountability_violations 
                (user_id, rule_id, violation_type, amount, merchant, partner_notified)
                VALUES (?, ?, ?, ?, ?, 0)
            ");
            $stmt->bind_param(
                "iisds",
                $user_id,
                $violation['rule_id'],
                $violation['type'],
                $amount,
                $merchant
            );
            $stmt->execute();
        }
    }
    
    // =============================================
    // BILL REMINDERS
    // =============================================
    
    private function getBills($user_id) {
        $stmt = $this->db->prepare("
            SELECT b.*, c.category_name, c.color_code,
                DATEDIFF(b.next_due_date, CURDATE()) as days_until_due
            FROM bill_reminders b
            LEFT JOIN budget_categories c ON b.category_id = c.id
            WHERE b.user_id = ? AND b.is_active = 1
            ORDER BY b.next_due_date
        ");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        $bills = [];
        while ($row = $result->fetch_assoc()) {
            $row['is_overdue'] = $row['days_until_due'] < 0;
            $row['is_due_soon'] = $row['days_until_due'] <= 3 && $row['days_until_due'] >= 0;
            $bills[] = $row;
        }
        
        return ['success' => true, 'bills' => $bills];
    }
    
    private function addBill($data) {
        $stmt = $this->db->prepare("
            INSERT INTO bill_reminders 
            (user_id, bill_name, amount, due_day, frequency, category_id, next_due_date, remind_days_before)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ");
        
        $stmt->bind_param(
            "isdisisi",
            $data['user_id'],
            $data['bill_name'],
            $data['amount'],
            $data['due_day'],
            $data['frequency'] ?? 'monthly',
            $data['category_id'] ?? null,
            $data['next_due_date'],
            $data['remind_days_before'] ?? 3
        );
        
        $stmt->execute();
        
        return ['success' => true, 'bill_id' => $stmt->insert_id];
    }
    
    private function updateBill($data) {
        $stmt = $this->db->prepare("
            UPDATE bill_reminders 
            SET bill_name = ?, amount = ?, due_day = ?, frequency = ?, 
                category_id = ?, next_due_date = ?, remind_days_before = ?
            WHERE id = ? AND user_id = ?
        ");
        
        $stmt->bind_param(
            "sdisisiii",
            $data['bill_name'],
            $data['amount'],
            $data['due_day'],
            $data['frequency'],
            $data['category_id'],
            $data['next_due_date'],
            $data['remind_days_before'],
            $data['bill_id'],
            $data['user_id']
        );
        
        $stmt->execute();
        
        return ['success' => true, 'message' => 'Bill updated'];
    }
    
    private function markBillPaid($data) {
        $user_id = $data['user_id'];
        $bill_id = $data['bill_id'];
        
        // Get bill details
        $stmt = $this->db->prepare("SELECT * FROM bill_reminders WHERE id = ? AND user_id = ?");
        $stmt->bind_param("ii", $bill_id, $user_id);
        $stmt->execute();
        $bill = $stmt->get_result()->fetch_assoc();
        
        if (!$bill) {
            return ['success' => false, 'message' => 'Bill not found'];
        }
        
        // Add as expense
        $this->addExpense([
            'user_id' => $user_id,
            'category_id' => $bill['category_id'],
            'amount' => $bill['amount'],
            'merchant' => $bill['bill_name'],
            'description' => 'Bill payment',
            'expense_date' => date('Y-m-d'),
            'entry_method' => 'bill_payment'
        ]);
        
        // Calculate next due date
        $next_due = $this->calculateNextDueDate($bill['next_due_date'], $bill['frequency']);
        
        // Update bill
        $stmt = $this->db->prepare("
            UPDATE bill_reminders 
            SET last_paid_date = CURDATE(), next_due_date = ?
            WHERE id = ?
        ");
        $stmt->bind_param("si", $next_due, $bill_id);
        $stmt->execute();
        
        return ['success' => true, 'next_due_date' => $next_due];
    }
    
    private function calculateNextDueDate($current_due, $frequency) {
        $date = new DateTime($current_due);
        
        switch ($frequency) {
            case 'weekly':
                $date->modify('+1 week');
                break;
            case 'monthly':
                $date->modify('+1 month');
                break;
            case 'quarterly':
                $date->modify('+3 months');
                break;
            case 'yearly':
                $date->modify('+1 year');
                break;
            case 'once':
                return null; // One-time bill
        }
        
        return $date->format('Y-m-d');
    }
    
    // =============================================
    // REPORTS & ANALYSIS
    // =============================================
    
    private function getSpendingSummary($data) {
        $user_id = $data['user_id'];
        $month_year = $data['month_year'] ?? date('Y-m');
        
        $stmt = $this->db->prepare("
            SELECT 
                c.category_name,
                c.monthly_limit,
                c.color_code,
                c.is_essential,
                COALESCE(SUM(e.amount), 0) as total_spent,
                COUNT(e.id) as transaction_count
            FROM budget_categories c
            LEFT JOIN expenses e ON c.id = e.category_id 
                AND DATE_FORMAT(e.expense_date, '%Y-%m') = ?
            WHERE c.user_id = ?
            GROUP BY c.id
            ORDER BY c.is_essential DESC, total_spent DESC
        ");
        
        $stmt->bind_param("si", $month_year, $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        $summary = [
            'total_budget' => 0,
            'total_spent' => 0,
            'categories' => []
        ];
        
        while ($row = $result->fetch_assoc()) {
            $row['remaining'] = $row['monthly_limit'] - $row['total_spent'];
            $row['percent_used'] = $row['monthly_limit'] > 0 
                ? round(($row['total_spent'] / $row['monthly_limit']) * 100, 1)
                : 0;
            
            $summary['total_budget'] += $row['monthly_limit'];
            $summary['total_spent'] += $row['total_spent'];
            $summary['categories'][] = $row;
        }
        
        $summary['total_remaining'] = $summary['total_budget'] - $summary['total_spent'];
        $summary['percent_used'] = $summary['total_budget'] > 0
            ? round(($summary['total_spent'] / $summary['total_budget']) * 100, 1)
            : 0;
        
        return ['success' => true, 'summary' => $summary];
    }
    
    private function getBudgetHealth($user_id) {
        $current_month = date('Y-m');
        
        // Get spending summary
        $summary = $this->getSpendingSummary(['user_id' => $user_id, 'month_year' => $current_month]);
        
        // Calculate health score (0-100)
        $score = 100;
        $issues = [];
        
        $percent_used = $summary['summary']['percent_used'];
        
        if ($percent_used > 100) {
            $score -= 50;
            $issues[] = "You've exceeded your total budget by " . ($percent_used - 100) . "%";
        } elseif ($percent_used > 90) {
            $score -= 30;
            $issues[] = "You've used " . $percent_used . "% of your budget";
        } elseif ($percent_used > 75) {
            $score -= 15;
            $issues[] = "You're at " . $percent_used . "% of your budget";
        }
        
        // Check for overbudget categories
        $overbudget_count = 0;
        foreach ($summary['summary']['categories'] as $cat) {
            if ($cat['percent_used'] > 100) {
                $overbudget_count++;
            }
        }
        
        if ($overbudget_count > 0) {
            $score -= ($overbudget_count * 10);
            $issues[] = "$overbudget_count categories are over budget";
        }
        
        // Check upcoming bills
        $upcoming_bills = $this->checkUpcomingBills($user_id);
        $upcoming_amount = array_sum(array_column($upcoming_bills, 'amount'));
        $available = $summary['summary']['total_remaining'];
        
        if ($upcoming_amount > $available) {
            $score -= 20;
            $issues[] = "Upcoming bills ($" . number_format($upcoming_amount, 2) . 
                       ") exceed available budget ($" . number_format($available, 2) . ")";
        }
        
        $score = max(0, $score);
        
        $health = [
            'score' => $score,
            'grade' => $this->getHealthGrade($score),
            'issues' => $issues,
            'total_spent' => $summary['summary']['total_spent'],
            'total_budget' => $summary['summary']['total_budget'],
            'percent_used' => $percent_used,
            'upcoming_bills_total' => $upcoming_amount
        ];
        
        return ['success' => true, 'health' => $health];
    }
    
    private function getHealthGrade($score) {
        if ($score >= 90) return 'A';
        if ($score >= 80) return 'B';
        if ($score >= 70) return 'C';
        if ($score >= 60) return 'D';
        return 'F';
    }
    
    private function getAIInsights($user_id) {
        // Get user's permission level
        $settings = $this->getSettings($user_id);
        $permission_level = $settings['settings']['permission_level'];
        
        if ($permission_level < 2) {
            return ['success' => false, 'message' => 'AI insights require permission level 2 or higher'];
        }
        
        // Gather data for AI analysis
        $health = $this->getBudgetHealth($user_id);
        $summary = $this->getSpendingSummary(['user_id' => $user_id]);
        $bills = $this->getBills($user_id);
        
        // Build context for Claude
        $context = "User Budget Analysis:\n\n";
        $context .= "Budget Health Score: {$health['health']['score']}/100 (Grade: {$health['health']['grade']})\n";
        $context .= "Total Budget: $" . number_format($summary['summary']['total_budget'], 2) . "\n";
        $context .= "Total Spent: $" . number_format($summary['summary']['total_spent'], 2) . 
                   " (" . $summary['summary']['percent_used'] . "%)\n\n";
        
        $context .= "Category Breakdown:\n";
        foreach ($summary['summary']['categories'] as $cat) {
            $context .= "- {$cat['category_name']}: $" . number_format($cat['total_spent'], 2) . 
                       " / $" . number_format($cat['monthly_limit'], 2) . 
                       " ({$cat['percent_used']}%)\n";
        }
        
        $context .= "\nUpcoming Bills:\n";
        foreach ($bills['bills'] as $bill) {
            $context .= "- {$bill['bill_name']}: $" . number_format($bill['amount'], 2) . 
                       " due in {$bill['days_until_due']} days\n";
        }
        
        if (!empty($health['health']['issues'])) {
            $context .= "\nCurrent Issues:\n";
            foreach ($health['health']['issues'] as $issue) {
                $context .= "- $issue\n";
            }
        }
        
        // Ask Claude for insights based on permission level
        $prompt = $this->buildInsightsPrompt($permission_level, $context);
        $insights = $this->callClaudeAPI($prompt);
        
        return [
            'success' => true,
            'insights' => $insights,
            'generated_at' => date('Y-m-d H:i:s')
        ];
    }
    
    private function buildInsightsPrompt($level, $context) {
        $base_prompt = "You are a financial assistant helping a user manage their budget. ";
        
        switch ($level) {
            case 2:
                $prompt = $base_prompt . "Provide basic observations about their spending patterns and suggest simple improvements.";
                break;
            case 3:
                $prompt = $base_prompt . "Provide detailed analysis of spending patterns, identify problems, and give actionable recommendations.";
                break;
            case 4:
                $prompt = $base_prompt . "Act as a financial partner. Provide comprehensive analysis, proactive suggestions for budget adjustments, and strategic advice.";
                break;
            case 5:
                $prompt = $base_prompt . "Act as a strict financial accountability partner. Point out violations, spending risks, and provide direct, no-nonsense recommendations to improve financial discipline.";
                break;
            default:
                $prompt = $base_prompt . "Provide basic spending observations.";
        }
        
        $prompt .= "\n\nHere's the user's current budget data:\n\n" . $context;
        $prompt .= "\n\nProvide 3-5 specific, actionable insights in a conversational tone. Be honest but encouraging.";
        
        return $prompt;
    }
    
    // =============================================
    // AI INTEGRATION
    // =============================================
    
    private function aiCategorizeExpense($user_id, $merchant, $description, $amount) {
        // Get user's categories
        $categories = $this->getCategories($user_id);
        $category_list = array_map(function($c) {
            return $c['category_name'];
        }, $categories['categories']);
        
        $prompt = "Categorize this expense:\n";
        $prompt .= "Merchant: " . ($merchant ?? 'Unknown') . "\n";
        $prompt .= "Description: " . ($description ?? 'None') . "\n";
        $prompt .= "Amount: $" . number_format($amount, 2) . "\n\n";
        $prompt .= "Available categories: " . implode(', ', $category_list) . "\n\n";
        $prompt .= "Return ONLY the category name that best matches this expense. If none match well, return 'Miscellaneous'.";
        
        $category_name = trim($this->callClaudeAPI($prompt));
        
        // Find category ID
        foreach ($categories['categories'] as $cat) {
            if (strcasecmp($cat['category_name'], $category_name) === 0) {
                return $cat['id'];
            }
        }
        
        // Default to Miscellaneous
        foreach ($categories['categories'] as $cat) {
            if (strcasecmp($cat['category_name'], 'Miscellaneous') === 0) {
                return $cat['id'];
            }
        }
        
        return null;
    }
    
    private function callClaudeAPI($prompt) {
        $data = [
            'model' => 'claude-sonnet-4-20250514',
            'max_tokens' => 1024,
            'messages' => [
                [
                    'role' => 'user',
                    'content' => $prompt
                ]
            ]
        ];
        
        $ch = curl_init($this->claude_api_url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            'Content-Type: application/json',
            'x-api-key: ' . $this->claude_api_key,
            'anthropic-version: 2023-06-01'
        ]);
        
        $response = curl_exec($ch);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        
        if ($http_code !== 200) {
            return "Unable to get AI response";
        }
        
        $result = json_decode($response, true);
        return $result['content'][0]['text'] ?? "No response";
    }
    
    // =============================================
    // ACCOUNTABILITY FEATURES (Level 4-5)
    // =============================================
    
    private function getViolations($user_id) {
        $stmt = $this->db->prepare("
            SELECT v.*, r.rule_name, r.rule_type
            FROM accountability_violations v
            JOIN accountability_rules r ON v.rule_id = r.id
            WHERE v.user_id = ?
            AND v.user_response = 'pending'
            ORDER BY v.violation_date DESC
        ");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        $violations = [];
        while ($row = $result->fetch_assoc()) {
            $violations[] = $row;
        }
        
        return ['success' => true, 'violations' => $violations];
    }
    
    private function resolveViolation($data) {
        $stmt = $this->db->prepare("
            UPDATE accountability_violations 
            SET user_response = ?, resolution_notes = ?, resolved_at = NOW()
            WHERE id = ? AND user_id = ?
        ");
        
        $stmt->bind_param(
            "ssii",
            $data['response'], // 'called_partner', 'overridden', 'cancelled'
            $data['notes'] ?? null,
            $data['violation_id'],
            $data['user_id']
        );
        
        $stmt->execute();
        
        return ['success' => true, 'message' => 'Violation resolved'];
    }
    
    private function notifyPartner($data) {
        $user_id = $data['user_id'];
        $partner_id = $data['partner_id'];
        $message = $data['message'];
        
        $stmt = $this->db->prepare("
            INSERT INTO pending_notifications 
            (user_id, notification_type, message, priority, requires_response)
            VALUES (?, 'budget_discussion', ?, 'medium', 1)
        ");
        $stmt->bind_param("is", $partner_id, $message);
        $stmt->execute();
        
        return ['success' => true, 'message' => 'Partner notified'];
    }
    
    // =============================================
    // HELPER FUNCTIONS
    // =============================================
    
    private function updateSpendingPatterns($user_id, $category_id, $amount) {
        if (!$category_id) return;
        
        $month_year = date('Y-m');
        
        $stmt = $this->db->prepare("
            INSERT INTO spending_patterns 
            (user_id, category_id, month_year, total_spent, transaction_count, average_transaction)
            VALUES (?, ?, ?, ?, 1, ?)
            ON DUPLICATE KEY UPDATE
                total_spent = total_spent + ?,
                transaction_count = transaction_count + 1,
                average_transaction = (total_spent + ?) / (transaction_count + 1)
        ");
        
        $stmt->bind_param("iisddd", $user_id, $category_id, $month_year, $amount, $amount, $amount, $amount);
        $stmt->execute();
    }
}

// =============================================
// MODULE EXPORT
// =============================================

// This gets called from the main API router
function handleBudgetKeeperRequest($db, $api_key, $action, $data) {
    $budget_keeper = new BudgetKeeperAI($db, $api_key);
    return $budget_keeper->handleRequest($action, $data);
}

?>
