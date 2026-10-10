-- ============================================
-- BUDGET KEEPER AI (MODULE 8) - DATABASE SCHEMA
-- Life First AI System
-- ============================================

-- User Budget Settings (Permission Levels & Preferences)
CREATE TABLE IF NOT EXISTS user_budget_settings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    permission_level TINYINT NOT NULL DEFAULT 1, -- 1=Manual, 2=Basic AI, 3=Active Manager, 4=Full Partnership, 5=Total Accountability
    partner_user_id INT DEFAULT NULL, -- Link to partner for accountability (e.g., Laurie's user_id)
    accountability_threshold DECIMAL(10,2) DEFAULT 100.00, -- Dollar amount that triggers partner notification
    require_partner_call BOOLEAN DEFAULT FALSE, -- Level 5: Require call to partner before big purchases
    cooling_off_minutes INT DEFAULT 0, -- Level 5: Minutes to wait before purchase
    enable_email_parsing BOOLEAN DEFAULT FALSE, -- Parse receipts from email
    enable_realtime_warnings BOOLEAN DEFAULT FALSE, -- Warn before checkout
    budget_start_day TINYINT DEFAULT 1, -- Day of month budget resets (1-31)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (partner_user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Budget Categories (User-defined or AI-suggested)
CREATE TABLE IF NOT EXISTS budget_categories (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_name VARCHAR(100) NOT NULL, -- Groceries, Gas, Entertainment, Bills, etc.
    monthly_limit DECIMAL(10,2) DEFAULT 0.00,
    is_essential BOOLEAN DEFAULT FALSE, -- Bills, groceries are essential; entertainment isn't
    color_code VARCHAR(7) DEFAULT '#3498db', -- For UI visualization
    icon VARCHAR(50) DEFAULT 'category', -- Icon name for UI
    ai_suggested BOOLEAN DEFAULT FALSE, -- Was this category suggested by AI?
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_category (user_id, category_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Expenses (Tracked Spending)
CREATE TABLE IF NOT EXISTS expenses (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_id INT DEFAULT NULL,
    amount DECIMAL(10,2) NOT NULL,
    merchant VARCHAR(255) DEFAULT NULL,
    description TEXT,
    expense_date DATE NOT NULL,
    entry_method ENUM('manual', 'email_parsed', 'ai_detected') DEFAULT 'manual',
    receipt_data TEXT, -- JSON: parsed receipt details if available
    location VARCHAR(255) DEFAULT NULL, -- Store location
    was_warned BOOLEAN DEFAULT FALSE, -- Did AI warn before this purchase?
    warning_overridden BOOLEAN DEFAULT FALSE, -- Did user ignore the warning?
    partner_notified BOOLEAN DEFAULT FALSE, -- Was partner notified about this?
    notes TEXT, -- User or AI notes about this expense
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE SET NULL,
    INDEX idx_user_date (user_id, expense_date),
    INDEX idx_category (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bill Reminders (Recurring Bills)
CREATE TABLE IF NOT EXISTS bill_reminders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    bill_name VARCHAR(255) NOT NULL, -- Electric, Rent, Netflix, etc.
    amount DECIMAL(10,2) NOT NULL,
    due_day TINYINT NOT NULL, -- Day of month (1-31)
    frequency ENUM('monthly', 'weekly', 'quarterly', 'yearly', 'once') DEFAULT 'monthly',
    category_id INT DEFAULT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    autopay_enabled BOOLEAN DEFAULT FALSE, -- Does this bill auto-pay?
    remind_days_before INT DEFAULT 3, -- Alert X days before due
    last_paid_date DATE DEFAULT NULL,
    next_due_date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE SET NULL,
    INDEX idx_user_due (user_id, next_due_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Accountability Rules (Level 4-5 Features)
CREATE TABLE IF NOT EXISTS accountability_rules (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    rule_name VARCHAR(255) NOT NULL,
    rule_type ENUM('spending_limit', 'category_restriction', 'time_restriction', 'merchant_block', 'partner_approval') NOT NULL,
    category_id INT DEFAULT NULL, -- If rule applies to specific category
    threshold_amount DECIMAL(10,2) DEFAULT NULL, -- Dollar amount that triggers rule
    time_start TIME DEFAULT NULL, -- e.g., No spending after 10 PM
    time_end TIME DEFAULT NULL,
    merchant_pattern VARCHAR(255) DEFAULT NULL, -- e.g., "casino", "liquor"
    action_type ENUM('warn', 'require_call', 'delay', 'notify_partner', 'log_violation') NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Accountability Violations (When Rules Are Broken)
CREATE TABLE IF NOT EXISTS accountability_violations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    rule_id INT NOT NULL,
    expense_id INT DEFAULT NULL, -- Link to the expense that violated
    violation_type VARCHAR(100) NOT NULL,
    amount DECIMAL(10,2) DEFAULT NULL,
    merchant VARCHAR(255) DEFAULT NULL,
    user_response ENUM('called_partner', 'overridden', 'cancelled', 'delayed', 'pending') DEFAULT 'pending',
    partner_notified BOOLEAN DEFAULT FALSE,
    partner_response TEXT, -- What did partner say?
    resolution_notes TEXT,
    violation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (rule_id) REFERENCES accountability_rules(id) ON DELETE CASCADE,
    FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE SET NULL,
    INDEX idx_user_pending (user_id, user_response)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Spending Patterns (AI Learning Data)
CREATE TABLE IF NOT EXISTS spending_patterns (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_id INT NOT NULL,
    month_year VARCHAR(7) NOT NULL, -- Format: "2025-10"
    total_spent DECIMAL(10,2) DEFAULT 0.00,
    transaction_count INT DEFAULT 0,
    average_transaction DECIMAL(10,2) DEFAULT 0.00,
    predicted_next_month DECIMAL(10,2) DEFAULT NULL, -- AI prediction
    pattern_notes TEXT, -- AI observations: "User overspends on groceries mid-month"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_category_month (user_id, category_id, month_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Budget Adjustments (AI or User Changes)
CREATE TABLE IF NOT EXISTS budget_adjustments (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_id INT NOT NULL,
    old_limit DECIMAL(10,2) NOT NULL,
    new_limit DECIMAL(10,2) NOT NULL,
    adjustment_reason TEXT,
    adjusted_by ENUM('user', 'ai', 'partner') NOT NULL,
    ai_confidence DECIMAL(5,2) DEFAULT NULL, -- If AI suggested: 0.00-100.00
    user_approved BOOLEAN DEFAULT FALSE,
    adjustment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE CASCADE,
    INDEX idx_user_date (user_id, adjustment_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- SAMPLE DATA FOR TESTING
-- ============================================

-- Insert default categories for a user (assuming user_id 1 exists)
-- These would be created when a user first enables Budget Keeper

-- Default Essential Categories
INSERT IGNORE INTO budget_categories (user_id, category_name, monthly_limit, is_essential, color_code, icon) VALUES
(1, 'Rent/Mortgage', 0.00, TRUE, '#e74c3c', 'home'),
(1, 'Utilities', 200.00, TRUE, '#f39c12', 'bolt'),
(1, 'Groceries', 600.00, TRUE, '#27ae60', 'shopping-cart'),
(1, 'Gas/Transportation', 300.00, TRUE, '#3498db', 'car'),
(1, 'Insurance', 250.00, TRUE, '#9b59b6', 'shield');

-- Default Discretionary Categories  
INSERT IGNORE INTO budget_categories (user_id, category_name, monthly_limit, is_essential, color_code, icon) VALUES
(1, 'Dining Out', 200.00, FALSE, '#e67e22', 'utensils'),
(1, 'Entertainment', 100.00, FALSE, '#1abc9c', 'film'),
(1, 'Shopping', 150.00, FALSE, '#34495e', 'shopping-bag'),
(1, 'Personal Care', 75.00, FALSE, '#95a5a6', 'user'),
(1, 'Miscellaneous', 100.00, FALSE, '#7f8c8d', 'ellipsis-h');

-- Sample Bill Reminder
INSERT IGNORE INTO bill_reminders (user_id, bill_name, amount, due_day, frequency, next_due_date) VALUES
(1, 'Electric Bill', 150.00, 15, 'monthly', '2025-11-15');

-- Sample Accountability Rule (Level 5)
INSERT IGNORE INTO accountability_rules (user_id, rule_name, rule_type, threshold_amount, action_type) VALUES
(1, 'Large Purchase Approval', 'spending_limit', 100.00, 'require_call');

-- ============================================
-- INDEXES FOR PERFORMANCE
-- ============================================

-- Additional indexes for common queries
CREATE INDEX idx_expenses_user_month ON expenses(user_id, expense_date);
CREATE INDEX idx_bills_next_due ON bill_reminders(next_due_date, is_active);
CREATE INDEX idx_violations_pending ON accountability_violations(user_id, user_response, violation_date);

-- ============================================
-- END OF BUDGET KEEPER SCHEMA
-- ============================================
