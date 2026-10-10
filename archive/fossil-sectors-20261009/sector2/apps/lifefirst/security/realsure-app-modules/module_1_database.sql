-- ============================================
-- MODULE 1: LIFE FIRST DATABASE SCHEMA
-- 5 Specialized AI System - MySQL Database
-- ============================================
-- 
-- DEPLOYMENT INSTRUCTIONS:
-- 1. Open phpMyAdmin on your WAMP server
-- 2. Create new database: "lifefirst"
-- 3. Select the database
-- 4. Go to SQL tab
-- 5. Copy/paste this ENTIRE file
-- 6. Click "Go"
-- 7. DONE! ✅
--
-- ============================================

-- Create database (if not exists)
CREATE DATABASE IF NOT EXISTS lifefirst
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE lifefirst;

-- ============================================
-- USERS TABLE (You + Laurie)
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    phone_token VARCHAR(255),
    api_key_hash VARCHAR(255),
    preferences JSON,
    timezone VARCHAR(50) DEFAULT 'America/Chicago',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active TINYINT(1) DEFAULT 1,
    INDEX idx_username (username),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Insert you and Laurie
INSERT INTO users (username, display_name, preferences, timezone) VALUES
('you', 'You', '{"notification_sound": "high", "voice_speed": "normal"}', 'America/Chicago'),
('laurie', 'Laurie', '{"notification_sound": "loud", "voice_speed": "normal"}', 'America/Chicago');

-- ============================================
-- AI #1: SCHEDULE MANAGER
-- ============================================
CREATE TABLE IF NOT EXISTS schedule_events (
    event_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    is_blocking TINYINT(1) DEFAULT 1,
    priority ENUM('low', 'medium', 'high', 'critical') DEFAULT 'medium',
    conflict_checked TINYINT(1) DEFAULT 0,
    created_by_ai TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_time (user_id, start_time, end_time),
    INDEX idx_time_range (start_time, end_time),
    INDEX idx_blocking (is_blocking)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Sample schedule data for testing
INSERT INTO schedule_events (user_id, title, description, start_time, end_time, priority) VALUES
(1, 'Work Meeting', 'Client call', NOW() + INTERVAL 2 HOUR, NOW() + INTERVAL 3 HOUR, 'high'),
(2, 'Grocery Shopping', 'Weekly groceries', NOW() + INTERVAL 4 HOUR, NOW() + INTERVAL 5 HOUR, 'medium');

-- ============================================
-- AI #2: CROSS-PHONE MESSENGER
-- ============================================
CREATE TABLE IF NOT EXISTS pending_messages (
    message_id INT PRIMARY KEY AUTO_INCREMENT,
    from_user_id INT NOT NULL,
    to_user_id INT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    message_type ENUM('question', 'info', 'urgent') DEFAULT 'question',
    priority ENUM('low', 'medium', 'high', 'must_answer') DEFAULT 'medium',
    status ENUM('pending', 'delivered', 'answered', 'expired') DEFAULT 'pending',
    notification_sent TINYINT(1) DEFAULT 0,
    notification_count INT DEFAULT 0,
    last_notification_at TIMESTAMP NULL,
    answered_at TIMESTAMP NULL,
    expires_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (to_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_to_user_status (to_user_id, status),
    INDEX idx_pending (status, created_at),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- AI #3: MEMORY KEEPER
-- ============================================
CREATE TABLE IF NOT EXISTS memory_storage (
    memory_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category VARCHAR(100),
    key_phrase VARCHAR(255) NOT NULL,
    value_data TEXT NOT NULL,
    confidence_score DECIMAL(3,2) DEFAULT 0.80,
    source ENUM('learned', 'told', 'observed') DEFAULT 'learned',
    times_referenced INT DEFAULT 0,
    last_referenced_at TIMESTAMP NULL,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_category (user_id, category),
    INDEX idx_key_phrase (key_phrase),
    INDEX idx_active (is_active),
    FULLTEXT idx_search (key_phrase, value_data)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Sample memories for testing
INSERT INTO memory_storage (user_id, category, key_phrase, value_data, source) VALUES
(2, 'food_preferences', 'pickles', 'Laurie prefers dill pickles over sweet pickles', 'told'),
(1, 'work_habits', 'meeting_time', 'Prefers morning meetings before 11 AM', 'observed'),
(2, 'shopping', 'grocery_day', 'Likes to shop on Thursdays', 'learned');

-- ============================================
-- AI #4: NOTIFICATION ENFORCER
-- ============================================
CREATE TABLE IF NOT EXISTS notification_queue (
    notification_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    message_text TEXT NOT NULL,
    notification_type ENUM('info', 'reminder', 'question', 'urgent', 'must_answer') DEFAULT 'info',
    priority_level INT DEFAULT 5,
    escalation_level INT DEFAULT 0,
    max_escalation INT DEFAULT 3,
    delivery_attempts INT DEFAULT 0,
    status ENUM('queued', 'sent', 'delivered', 'acknowledged', 'failed') DEFAULT 'queued',
    related_message_id INT,
    scheduled_for TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP NULL,
    acknowledged_at TIMESTAMP NULL,
    expires_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (related_message_id) REFERENCES pending_messages(message_id) ON DELETE CASCADE,
    INDEX idx_user_status (user_id, status),
    INDEX idx_scheduled (scheduled_for, status),
    INDEX idx_priority (priority_level, escalation_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- AI #5: VOICE COMMANDER
-- ============================================
CREATE TABLE IF NOT EXISTS voice_interactions (
    interaction_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    voice_input TEXT,
    transcribed_text TEXT NOT NULL,
    detected_intent VARCHAR(100),
    routed_to_ai ENUM('schedule', 'messenger', 'memory', 'notification', 'general') NOT NULL,
    ai_response TEXT,
    response_spoken TINYINT(1) DEFAULT 0,
    processing_time_ms INT,
    success TINYINT(1) DEFAULT 1,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_time (user_id, created_at),
    INDEX idx_intent (detected_intent),
    INDEX idx_routed (routed_to_ai)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- SHARED: CONVERSATION HISTORY
-- ============================================
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    message_from ENUM('user', 'ai') NOT NULL,
    message_text TEXT NOT NULL,
    ai_model_used VARCHAR(50),
    context_data JSON,
    tokens_used INT,
    processing_time_ms INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_time (user_id, created_at),
    INDEX idx_time (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- SHARED: SYSTEM LOGS
-- ============================================
CREATE TABLE IF NOT EXISTS system_logs (
    log_id INT PRIMARY KEY AUTO_INCREMENT,
    log_level ENUM('debug', 'info', 'warning', 'error', 'critical') DEFAULT 'info',
    component VARCHAR(100),
    message TEXT NOT NULL,
    user_id INT,
    additional_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_level_time (log_level, created_at),
    INDEX idx_component (component)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- CLEANUP STORED PROCEDURE (Auto-delete old data)
-- ============================================
DELIMITER $$
CREATE PROCEDURE cleanup_old_data()
BEGIN
    -- Delete old conversations (older than 90 days)
    DELETE FROM conversations WHERE created_at < NOW() - INTERVAL 90 DAY;
    
    -- Delete old voice logs (older than 30 days)
    DELETE FROM voice_interactions WHERE created_at < NOW() - INTERVAL 30 DAY;
    
    -- Delete old system logs (older than 30 days, keep errors for 90)
    DELETE FROM system_logs WHERE created_at < NOW() - INTERVAL 30 DAY AND log_level NOT IN ('error', 'critical');
    DELETE FROM system_logs WHERE created_at < NOW() - INTERVAL 90 DAY;
    
    -- Delete expired/old pending messages
    DELETE FROM pending_messages WHERE status = 'expired' AND created_at < NOW() - INTERVAL 7 DAY;
    
    -- Delete old completed notifications
    DELETE FROM notification_queue WHERE status = 'acknowledged' AND acknowledged_at < NOW() - INTERVAL 7 DAY;
    
    -- Delete old past schedule events (keep 30 days back)
    DELETE FROM schedule_events WHERE end_time < NOW() - INTERVAL 30 DAY;
END$$
DELIMITER ;

-- ============================================
-- CREATE EVENT FOR AUTO-CLEANUP (runs daily at 3 AM)
-- ============================================
CREATE EVENT IF NOT EXISTS daily_cleanup
ON SCHEDULE EVERY 1 DAY
STARTS (TIMESTAMP(CURRENT_DATE) + INTERVAL 1 DAY + INTERVAL 3 HOUR)
DO CALL cleanup_old_data();

-- ============================================
-- UTILITY VIEWS FOR EASY QUERIES
-- ============================================

-- View: Current active schedule for both users
CREATE OR REPLACE VIEW active_schedules AS
SELECT 
    u.display_name,
    s.title,
    s.start_time,
    s.end_time,
    s.priority,
    s.is_blocking
FROM schedule_events s
JOIN users u ON s.user_id = u.user_id
WHERE s.end_time >= NOW()
ORDER BY s.start_time;

-- View: Pending questions that need answers
CREATE OR REPLACE VIEW pending_questions AS
SELECT 
    pm.message_id,
    u_from.display_name AS from_user,
    u_to.display_name AS to_user,
    pm.question,
    pm.priority,
    pm.notification_count,
    pm.created_at
FROM pending_messages pm
JOIN users u_from ON pm.from_user_id = u_from.user_id
JOIN users u_to ON pm.to_user_id = u_to.user_id
WHERE pm.status = 'pending'
ORDER BY pm.priority DESC, pm.created_at;

-- View: Active memories by category
CREATE OR REPLACE VIEW active_memories AS
SELECT 
    u.display_name,
    m.category,
    m.key_phrase,
    m.value_data,
    m.confidence_score,
    m.times_referenced
FROM memory_storage m
JOIN users u ON m.user_id = u.user_id
WHERE m.is_active = 1
ORDER BY m.times_referenced DESC;

-- ============================================
-- DATABASE STATS (for monitoring)
-- ============================================
CREATE OR REPLACE VIEW database_stats AS
SELECT 
    'Users' AS table_name, COUNT(*) AS row_count FROM users
UNION ALL
SELECT 'Schedule Events', COUNT(*) FROM schedule_events
UNION ALL
SELECT 'Pending Messages', COUNT(*) FROM pending_messages WHERE status = 'pending'
UNION ALL
SELECT 'Memories', COUNT(*) FROM memory_storage WHERE is_active = 1
UNION ALL
SELECT 'Notifications Queued', COUNT(*) FROM notification_queue WHERE status IN ('queued', 'sent')
UNION ALL
SELECT 'Voice Interactions (30d)', COUNT(*) FROM voice_interactions WHERE created_at > NOW() - INTERVAL 30 DAY
UNION ALL
SELECT 'Conversations (30d)', COUNT(*) FROM conversations WHERE created_at > NOW() - INTERVAL 30 DAY;

-- ============================================
-- GRANT PERMISSIONS (adjust username as needed)
-- ============================================
-- Replace 'your_wamp_user' with your actual MySQL username
-- GRANT ALL PRIVILEGES ON lifefirst.* TO 'your_wamp_user'@'localhost';
-- FLUSH PRIVILEGES;

-- ============================================
-- VERIFICATION QUERIES
-- ============================================
-- Run these to verify everything was created:

-- Check all tables
-- SHOW TABLES;

-- Check database size
-- SELECT 
--     table_name,
--     ROUND((data_length + index_length) / 1024, 2) AS size_kb
-- FROM information_schema.TABLES
-- WHERE table_schema = 'lifefirst'
-- ORDER BY (data_length + index_length) DESC;

-- Test the views
-- SELECT * FROM active_schedules;
-- SELECT * FROM pending_questions;
-- SELECT * FROM active_memories;
-- SELECT * FROM database_stats;

-- ============================================
-- MODULE 1 DEPLOYMENT COMPLETE! ✅
-- ============================================
--
-- NEXT STEPS:
-- 1. Verify tables created: Run "SHOW TABLES;"
-- 2. Check sample data: Run "SELECT * FROM users;"
-- 3. Test views: Run "SELECT * FROM database_stats;"
-- 4. Ready for MODULE 2: PHP API Router
--
-- DATABASE SIZE: ~10 KB (empty) to ~100 MB (1 year heavy use)
-- ============================================