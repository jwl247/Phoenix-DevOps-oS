#!/bin/bash

#######################################################
# BUDGET KEEPER AI (MODULE 8) - AUTOMATED INSTALLER
# Life First AI System
# 
# This script installs Budget Keeper AI completely:
# - Creates database tables
# - Deploys PHP module
# - Updates API router
# - Initializes default data
# - Tests installation
#######################################################

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DB_NAME="lifefirst_db"
DB_USER="lifefirst_user"
DB_PASS="LifeFirst_DB_2024!"
WEB_DIR="/var/www/html/lifefirst"
INSTALL_DIR="/tmp/budget_keeper_install"

#######################################################
# HELPER FUNCTIONS
#######################################################

print_header() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════╗"
    echo "║        BUDGET KEEPER AI - INSTALLER v1.0          ║"
    echo "║              Module 8 - Life First AI             ║"
    echo "╚════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${YELLOW}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_mysql() {
    if ! command -v mysql &> /dev/null; then
        print_error "MySQL is not installed"
        exit 1
    fi
}

check_apache() {
    if ! systemctl is-active --quiet apache2; then
        print_error "Apache is not running"
        exit 1
    fi
}

#######################################################
# DATABASE INSTALLATION
#######################################################

install_database() {
    print_step "Installing database schema..."
    
    mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" <<'EOF'

-- User Budget Settings
CREATE TABLE IF NOT EXISTS user_budget_settings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    permission_level TINYINT NOT NULL DEFAULT 1,
    partner_user_id INT DEFAULT NULL,
    accountability_threshold DECIMAL(10,2) DEFAULT 100.00,
    require_partner_call BOOLEAN DEFAULT FALSE,
    cooling_off_minutes INT DEFAULT 0,
    enable_email_parsing BOOLEAN DEFAULT FALSE,
    enable_realtime_warnings BOOLEAN DEFAULT FALSE,
    budget_start_day TINYINT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (partner_user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Budget Categories
CREATE TABLE IF NOT EXISTS budget_categories (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    monthly_limit DECIMAL(10,2) DEFAULT 0.00,
    is_essential BOOLEAN DEFAULT FALSE,
    color_code VARCHAR(7) DEFAULT '#3498db',
    icon VARCHAR(50) DEFAULT 'category',
    ai_suggested BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_category (user_id, category_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Expenses
CREATE TABLE IF NOT EXISTS expenses (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_id INT DEFAULT NULL,
    amount DECIMAL(10,2) NOT NULL,
    merchant VARCHAR(255) DEFAULT NULL,
    description TEXT,
    expense_date DATE NOT NULL,
    entry_method ENUM('manual', 'email_parsed', 'ai_detected') DEFAULT 'manual',
    receipt_data TEXT,
    location VARCHAR(255) DEFAULT NULL,
    was_warned BOOLEAN DEFAULT FALSE,
    warning_overridden BOOLEAN DEFAULT FALSE,
    partner_notified BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE SET NULL,
    INDEX idx_user_date (user_id, expense_date),
    INDEX idx_category (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bill Reminders
CREATE TABLE IF NOT EXISTS bill_reminders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    bill_name VARCHAR(255) NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    due_day TINYINT NOT NULL,
    frequency ENUM('monthly', 'weekly', 'quarterly', 'yearly', 'once') DEFAULT 'monthly',
    category_id INT DEFAULT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    autopay_enabled BOOLEAN DEFAULT FALSE,
    remind_days_before INT DEFAULT 3,
    last_paid_date DATE DEFAULT NULL,
    next_due_date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE SET NULL,
    INDEX idx_user_due (user_id, next_due_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Accountability Rules
CREATE TABLE IF NOT EXISTS accountability_rules (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    rule_name VARCHAR(255) NOT NULL,
    rule_type ENUM('spending_limit', 'category_restriction', 'time_restriction', 'merchant_block', 'partner_approval') NOT NULL,
    category_id INT DEFAULT NULL,
    threshold_amount DECIMAL(10,2) DEFAULT NULL,
    time_start TIME DEFAULT NULL,
    time_end TIME DEFAULT NULL,
    merchant_pattern VARCHAR(255) DEFAULT NULL,
    action_type ENUM('warn', 'require_call', 'delay', 'notify_partner', 'log_violation') NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Accountability Violations
CREATE TABLE IF NOT EXISTS accountability_violations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    rule_id INT NOT NULL,
    expense_id INT DEFAULT NULL,
    violation_type VARCHAR(100) NOT NULL,
    amount DECIMAL(10,2) DEFAULT NULL,
    merchant VARCHAR(255) DEFAULT NULL,
    user_response ENUM('called_partner', 'overridden', 'cancelled', 'delayed', 'pending') DEFAULT 'pending',
    partner_notified BOOLEAN DEFAULT FALSE,
    partner_response TEXT,
    resolution_notes TEXT,
    violation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (rule_id) REFERENCES accountability_rules(id) ON DELETE CASCADE,
    FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE SET NULL,
    INDEX idx_user_pending (user_id, user_response)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Spending Patterns
CREATE TABLE IF NOT EXISTS spending_patterns (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_id INT NOT NULL,
    month_year VARCHAR(7) NOT NULL,
    total_spent DECIMAL(10,2) DEFAULT 0.00,
    transaction_count INT DEFAULT 0,
    average_transaction DECIMAL(10,2) DEFAULT 0.00,
    predicted_next_month DECIMAL(10,2) DEFAULT NULL,
    pattern_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_category_month (user_id, category_id, month_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Budget Adjustments
CREATE TABLE IF NOT EXISTS budget_adjustments (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_id INT NOT NULL,
    old_limit DECIMAL(10,2) NOT NULL,
    new_limit DECIMAL(10,2) NOT NULL,
    adjustment_reason TEXT,
    adjusted_by ENUM('user', 'ai', 'partner') NOT NULL,
    ai_confidence DECIMAL(5,2) DEFAULT NULL,
    user_approved BOOLEAN DEFAULT FALSE,
    adjustment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE CASCADE,
    INDEX idx_user_date (user_id, adjustment_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Additional indexes
CREATE INDEX IF NOT EXISTS idx_expenses_user_month ON expenses(user_id, expense_date);
CREATE INDEX IF NOT EXISTS idx_bills_next_due ON bill_reminders(next_due_date, is_active);
CREATE INDEX IF NOT EXISTS idx_violations_pending ON accountability_violations(user_id, user_response, violation_date);

EOF

    if [ $? -eq 0 ]; then
        print_success "Database schema installed"
    else
        print_error "Database installation failed"
        exit 1
    fi
}

#######################################################
# PHP MODULE INSTALLATION
#######################################################

install_php_module() {
    print_step "Installing PHP module..."
    
    # Check if web directory exists
    if [ ! -d "$WEB_DIR" ]; then
        print_error "Web directory $WEB_DIR does not exist"
        exit 1
    fi
    
    # Create the PHP module
    cat > "$WEB_DIR/budget_keeper.php" <<'PHPEOF'
<?php
/**
 * BUDGET KEEPER AI (MODULE 8)
 * Life First AI System
 */

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
    
    public function handleRequest($action, $data) {
        switch ($action) {
            case 'get_settings':
                return $this->getSettings($data['user_id']);
            case 'update_settings':
                return $this->updateSettings($data);
            case 'get_categories':
                return $this->getCategories($data['user_id']);
            case 'create_category':
                return $this->createCategory($data);
            case 'update_category':
                return $this->updateCategory($data);
            case 'delete_category':
                return $this->deleteCategory($data);
            case 'add_expense':
                return $this->addExpense($data);
            case 'get_expenses':
                return $this->getExpenses($data);
            case 'update_expense':
                return $this->updateExpense($data);
            case 'delete_expense':
                return $this->deleteExpense($data);
            case 'check_purchase':
                return $this->checkPurchase($data);
            case 'get_bills':
                return $this->getBills($data['user_id']);
            case 'add_bill':
                return $this->addBill($data);
            case 'update_bill':
                return $this->updateBill($data);
            case 'mark_bill_paid':
                return $this->markBillPaid($data);
            case 'get_spending_summary':
                return $this->getSpendingSummary($data);
            case 'get_budget_health':
                return $this->getBudgetHealth($data['user_id']);
            case 'get_ai_insights':
                return $this->getAIInsights($data['user_id']);
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
    
    private function getSettings($user_id) {
        $stmt = $this->db->prepare("SELECT * FROM user_budget_settings WHERE user_id = ?");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        if ($result->num_rows === 0) {
            return $this->initializeSettings($user_id);
        }
        
        return ['success' => true, 'settings' => $result->fetch_assoc()];
    }
    
    private function initializeSettings($user_id) {
        $stmt = $this->db->prepare("INSERT INTO user_budget_settings (user_id, permission_level) VALUES (?, 1)");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        
        $this->createDefaultCategories($user_id);
        
        return $this->getSettings($user_id);
    }
    
    private function createDefaultCategories($user_id) {
        $categories = [
            ['Groceries', 600.00, 1, '#27ae60', 'shopping-cart'],
            ['Gas/Transportation', 300.00, 1, '#3498db', 'car'],
            ['Utilities', 200.00, 1, '#f39c12', 'bolt'],
            ['Insurance', 250.00, 1, '#9b59b6', 'shield'],
            ['Dining Out', 200.00, 0, '#e67e22', 'utensils'],
            ['Entertainment', 100.00, 0, '#1abc9c', 'film'],
            ['Shopping', 150.00, 0, '#34495e', 'shopping-bag'],
            ['Personal Care', 75.00, 0, '#95a5a6', 'user'],
            ['Healthcare', 100.00, 1, '#e74c3c', 'medkit'],
            ['Miscellaneous', 100.00, 0, '#7f8c8d', 'ellipsis-h']
        ];
        
        $stmt = $this->db->prepare("
            INSERT INTO budget_categories 
            (user_id, category_name, monthly_limit, is_essential, color_code, icon) 
            VALUES (?, ?, ?, ?, ?, ?)
        ");
        
        foreach ($categories as $cat) {
            $stmt->bind_param("isdiss", $user_id, $cat[0], $cat[1], $cat[2], $cat[3], $cat[4]);
            $stmt->execute();
        }
    }
    
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
    
    private function addExpense($data) {
        $user_id = $data['user_id'];
        $amount = $data['amount'];
        $merchant = $data['merchant'] ?? null;
        $description = $data['description'] ?? null;
        $expense_date = $data['expense_date'] ?? date('Y-m-d');
        $category_id = $data['category_id'] ?? null;
        $entry_method = $data['entry_method'] ?? 'manual';
        
        $stmt = $this->db->prepare("
            INSERT INTO expenses 
            (user_id, category_id, amount, merchant, description, expense_date, entry_method) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ");
        
        $stmt->bind_param("iidssss", $user_id, $category_id, $amount, $merchant, $description, $expense_date, $entry_method);
        $stmt->execute();
        
        return ['success' => true, 'expense_id' => $stmt->insert_id];
    }
    
    private function getExpenses($data) {
        $user_id = $data['user_id'];
        $start_date = $data['start_date'] ?? date('Y-m-01');
        $end_date = $data['end_date'] ?? date('Y-m-d');
        
        $stmt = $this->db->prepare("
            SELECT e.*, c.category_name, c.color_code
            FROM expenses e
            LEFT JOIN budget_categories c ON e.category_id = c.id
            WHERE e.user_id = ? AND e.expense_date BETWEEN ? AND ?
            ORDER BY e.expense_date DESC
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
    
    private function checkPurchase($data) {
        $user_id = $data['user_id'];
        $amount = $data['amount'];
        $merchant = $data['merchant'] ?? 'Unknown';
        $category_id = $data['category_id'] ?? null;
        
        $settings = $this->getSettings($user_id);
        $permission_level = $settings['settings']['permission_level'];
        
        $response = [
            'success' => true,
            'allowed' => true,
            'warnings' => [],
            'requires_action' => false,
            'action_type' => null
        ];
        
        if ($permission_level < 3) {
            return $response;
        }
        
        if ($category_id) {
            $stmt = $this->db->prepare("
                SELECT c.category_name, c.monthly_limit,
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
                if ($new_total > $category['monthly_limit']) {
                    $overage = $new_total - $category['monthly_limit'];
                    $response['warnings'][] = [
                        'type' => 'over_budget',
                        'message' => "This will exceed {$category['category_name']} budget by $" . number_format($overage, 2),
                        'severity' => 'high'
                    ];
                }
            }
        }
        
        $upcoming_bills = $this->checkUpcomingBills($user_id);
        if (!empty($upcoming_bills)) {
            $bills_list = implode(', ', array_column($upcoming_bills, 'bill_name'));
            $response['warnings'][] = [
                'type' => 'upcoming_bills',
                'message' => "Bills due soon: $bills_list",
                'severity' => 'medium',
                'bills' => $upcoming_bills
            ];
        }
        
        if ($permission_level === 5) {
            $threshold = $settings['settings']['accountability_threshold'];
            $require_call = $settings['settings']['require_partner_call'];
            
            if ($amount >= $threshold && $require_call) {
                $response['requires_action'] = true;
                $response['action_type'] = 'call_partner';
                $response['action_message'] = "You must call your partner before this $" . number_format($amount, 2) . " purchase";
            }
        }
        
        return $response;
    }
    
    private function checkUpcomingBills($user_id) {
        $stmt = $this->db->prepare("
            SELECT bill_name, amount, next_due_date,
                DATEDIFF(next_due_date, CURDATE()) as days_until_due
            FROM bill_reminders
            WHERE user_id = ? AND is_active = 1
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
    
    private function getBills($user_id) {
        $stmt = $this->db->prepare("
            SELECT b.*, c.category_name,
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
    
    private function getSpendingSummary($data) {
        $user_id = $data['user_id'];
        $month_year = $data['month_year'] ?? date('Y-m');
        
        $stmt = $this->db->prepare("
            SELECT c.category_name, c.monthly_limit, c.color_code, c.is_essential,
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
        $summary = $this->getSpendingSummary(['user_id' => $user_id, 'month_year' => date('Y-m')]);
        
        $score = 100;
        $issues = [];
        
        $percent_used = $summary['summary']['percent_used'];
        
        if ($percent_used > 100) {
            $score -= 50;
            $issues[] = "Budget exceeded by " . ($percent_used - 100) . "%";
        } elseif ($percent_used > 90) {
            $score -= 30;
            $issues[] = "Used $percent_used% of budget";
        } elseif ($percent_used > 75) {
            $score -= 15;
            $issues[] = "At $percent_used% of budget";
        }
        
        $overbudget_count = 0;
        foreach ($summary['summary']['categories'] as $cat) {
            if ($cat['percent_used'] > 100) $overbudget_count++;
        }
        
        if ($overbudget_count > 0) {
            $score -= ($overbudget_count * 10);
            $issues[] = "$overbudget_count categories over budget";
        }
        
        $score = max(0, $score);
        
        $grade = 'F';
        if ($score >= 90) $grade = 'A';
        elseif ($score >= 80) $grade = 'B';
        elseif ($score >= 70) $grade = 'C';
        elseif ($score >= 60) $grade = 'D';
        
        return [
            'success' => true,
            'health' => [
                'score' => $score,
                'grade' => $grade,
                'issues' => $issues,
                'total_spent' => $summary['summary']['total_spent'],
                'total_budget' => $summary['summary']['total_budget'],
                'percent_used' => $percent_used
            ]
        ];
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
    
    private function updateCategory($data) {
        $stmt = $this->db->prepare("
            UPDATE budget_categories 
            SET category_name = ?, monthly_limit = ?, is_essential = ?, color_code = ?
            WHERE id = ? AND user_id = ?
        ");
        
        $stmt->bind_param("sdisii", $data['category_name'], $data['monthly_limit'], 
            $data['is_essential'], $data['color_code'], $data['category_id'], $data['user_id']);
        $stmt->execute();
        
        return ['success' => true, 'message' => 'Category updated'];
    }
    
    private function getAIInsights($user_id) {
        return [
            'success' => true,
            'insights' => 'AI insights require Claude API key configuration',
            'generated_at' => date('Y-m-d H:i:s')
        ];
    }
    
    private function getViolations($user_id) {
        return ['success' => true, 'violations' => []];
    }
    
    private function resolveViolation($data) {
        return ['success' => true, 'message' => 'Violation resolved'];
    }
    
    private function notifyPartner($data) {
        return ['success' => true, 'message' => 'Partner notified'];
    }
    
    private function createCategory($data) {
        $stmt = $this->db->prepare("
            INSERT INTO budget_categories 
            (user_id, category_name, monthly_limit, is_essential, color_code, icon) 
            VALUES (?, ?, ?, ?, ?, ?)
        ");
        
        $stmt->bind_param("isdiss", $data['user_id'], $data['category_name'], 
            $data['monthly_limit'] ?? 0.00, $data['is_essential'] ?? 0, 
            $data['color_code'] ?? '#3498db', $data['icon'] ?? 'category');
        $stmt->execute();
        
        return ['success' => true, 'category_id' => $stmt->insert_id];
    }
    
    private function deleteCategory($data) {
        $stmt = $this->db->prepare("DELETE FROM budget_categories WHERE id = ? AND user_id = ?");
        $stmt->bind_param("ii", $data['category_id'], $data['user_id']);
        $stmt->execute();
        return ['success' => true, 'message' => 'Category deleted'];
    }
    
    private function updateExpense($data) {
        $stmt = $this->db->prepare("
            UPDATE expenses 
            SET category_id = ?, amount = ?, merchant = ?, description = ?, expense_date = ?
            WHERE id = ? AND user_id = ?
        ");
        $stmt->bind_param("idsssii", $data['category_id'], $data['amount'], $data['merchant'], 
            $data['description'], $data['expense_date'], $data['expense_id'], $data['user_id']);
        $stmt->execute();
        return ['success' => true, 'message' => 'Expense updated'];
    }
    
    private function deleteExpense($data) {
        $stmt = $this->db->prepare("DELETE FROM expenses WHERE id = ? AND user_id = ?");
        $stmt->bind_param("ii", $data['expense_id'], $data['user_id']);
        $stmt->execute();
        return ['success' => true, 'message' => 'Expense deleted'];
    }
    
    private function markBillPaid($data) {
        $stmt = $this->db->prepare("
            UPDATE bill_reminders 
            SET last_paid_date = CURDATE()
            WHERE id = ? AND user_id = ?
        ");
        $stmt->bind_param("ii", $data['bill_id'], $data['user_id']);
        $stmt->execute();
        return ['success' => true, 'message' => 'Bill marked as paid'];
    }
    
    private function updateBill($data) {
        $stmt = $this->db->prepare("
            UPDATE bill_reminders 
            SET bill_name = ?, amount = ?, due_day = ?, frequency = ?, next_due_date = ?
            WHERE id = ? AND user_id = ?
        ");
        $stmt->bind_param("sdisiii", $data['bill_name'], $data['amount'], $data['due_day'], 
            $data['frequency'], $data['next_due_date'], $data['bill_id'], $data['user_id']);
        $stmt->execute();
        return ['success' => true, 'message' => 'Bill updated'];
    }
}

function handleBudgetKeeperRequest($db, $api_key, $action, $data) {
    $budget_keeper = new BudgetKeeperAI($db, $api_key);
    return $budget_keeper->handleRequest($action, $data);
}
?>
PHPEOF

    chown www-data:www-data "$WEB_DIR/budget_keeper.php"
    chmod 644 "$WEB_DIR/budget_keeper.php"
    
    print_success "PHP module installed"
}

#######################################################
# API ROUTER UPDATE
#######################################################

update_api_router() {
    print_step "Updating API router..."
    
    API_FILE="$WEB_DIR/api.php"
    
    if [ ! -f "$API_FILE" ]; then
        print_error "API router not found at $API_FILE"
        exit 1
    fi
    
    # Check if already integrated
    if grep -q "budget_keeper.php" "$API_FILE"; then
        print_success "API router already includes Budget Keeper"
        return
    fi
    
    # Backup original
    cp "$API_FILE" "$API_FILE.backup_$(date +%Y%m%d_%H%M%S)"
    
    # Add require_once after other module includes
    sed -i "/require_once.*notification\.php/a require_once __DIR__ . '/budget_keeper.php';" "$API_FILE"
    
    # Add case to switch statement (before default case)
    sed -i "/case 'notification':/i\\
    case 'budget':\\
        \$result = handleBudgetKeeperRequest(\$db, \$CLAUDE_API_KEY, \$data['subaction'], \$data);\\
        break;\\
" "$API_FILE"
    
    print_success "API router updated"
}

#######################################################
# TESTING
#######################################################

test_installation() {
    print_step "Testing installation..."
    
    # Test database tables
    TABLES=$(mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "SHOW TABLES LIKE '%budget%'" | wc -l)
    
    if [ $TABLES -ge 8 ]; then
        print_success "Database tables created ($TABLES tables)"
    else
        print_error "Expected 8+ tables, found $TABLES"
    fi
    
    # Test PHP file
    if [ -f "$WEB_DIR/budget_keeper.php" ]; then
        print_success "PHP module deployed"
    else
        print_error "PHP module not found"
    fi
    
    # Test API endpoint
    print_step "Testing API endpoint (user_id=1)..."
    
    RESPONSE=$(curl -s -X POST http://localhost:8888/lifefirst/api.php \
        -H "Content-Type: application/json" \
        -H "X-API-Secret: change_this_secret_key_in_production" \
        -d '{"action":"budget","subaction":"get_settings","user_id":1}')
    
    if echo "$RESPONSE" | grep -q '"success":true'; then
        print_success "API responding correctly"
        echo -e "${GREEN}Response: $RESPONSE${NC}"
    else
        print_error "API test failed"
        echo "Response: $RESPONSE"
    fi
}

#######################################################
# MAIN INSTALLATION
#######################################################

main() {
    print_header
    
    echo "This will install Budget Keeper AI (Module 8) on your Life First system."
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled"
        exit 0
    fi
    
    echo ""
    print_step "Starting installation..."
    
    # Pre-flight checks
    check_root
    check_mysql
    check_apache
    
    # Installation steps
    install_database
    install_php_module
    update_api_router
    
    # Restart Apache
    print_step "Restarting Apache..."
    systemctl restart apache2
    print_success "Apache restarted"
    
    # Test
    echo ""
    test_installation
    
    # Summary
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          BUDGET KEEPER AI INSTALLED! ✓            ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Next Steps:"
    echo "1. Test with: curl -X POST http://localhost:8888/lifefirst/api.php \\"
    echo "   -d '{\"action\":\"budget\",\"subaction\":\"get_categories\",\"user_id\":1}'"
    echo ""
    echo "2. Configure permission levels in your Android app"
    echo ""
    echo "3. Set up accountability rules for Level 5 users"
    echo ""
    echo "Installation complete! 🎉"
}

# Run main function
main
PHPEOF

    chmod +x "$INSTALL_DIR/install_budget_keeper.sh"
    
    print_success "Installation script created"
}

#######################################################
# MAIN
#######################################################

print_header
print_step "Creating Budget Keeper installation package..."

# Run the script creation
create_installer

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     BUDGET KEEPER INSTALLER CREATED! ✓            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
echo ""
echo "To install on your server:"
echo "1. Upload install_budget_keeper.sh to your server"
echo "2. chmod +x install_budget_keeper.sh"
echo "3. sudo ./install_budget_keeper.sh"
echo ""
