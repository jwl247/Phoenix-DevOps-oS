-- ============================================
-- Life First — Module 5 (Memory Keeper) schema migration
-- ============================================
-- module_1_database.sql creates memory_storage with the columns
--   key_phrase / value_data / confidence_score / times_referenced /
--   last_referenced_at and source ENUM(learned, told, observed).
-- module_5_ai_memory.php reads and writes
--   memory_key / memory_value / memory_type / confidence / access_count /
--   last_accessed and source IN (user_stated, inferred), and relies on a
--   UNIQUE (user_id, memory_key) for its ON DUPLICATE KEY UPDATE.
-- The two shipped mismatched since the 2026-07-04 consolidation, so every
-- "remember ..." / "what does Laurie like" request died in prepare().
-- This file brings memory_storage to the contract module_5 actually uses.
--
-- Idempotent on MariaDB (CHANGE/ADD ... IF [NOT] EXISTS, MariaDB >= 10.0.2).
-- install.sh runs it right after module_1_database.sql on a fresh database;
-- on an existing database run it by hand once:
--   mysql lifefirst < module_5_memory_migration.sql
-- Existing rows keep their data (renames only); the FULLTEXT and
-- idx_key_phrase indexes follow the renamed columns.

ALTER TABLE memory_storage
    CHANGE COLUMN IF EXISTS key_phrase         memory_key   VARCHAR(255) NOT NULL,
    CHANGE COLUMN IF EXISTS value_data         memory_value TEXT NOT NULL,
    CHANGE COLUMN IF EXISTS confidence_score   confidence   DECIMAL(3,2) DEFAULT 0.80,
    CHANGE COLUMN IF EXISTS times_referenced   access_count INT DEFAULT 0,
    CHANGE COLUMN IF EXISTS last_referenced_at last_accessed TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS memory_type VARCHAR(50) DEFAULT 'fact' AFTER memory_value,
    MODIFY COLUMN source ENUM('learned', 'told', 'observed', 'user_stated', 'inferred') DEFAULT 'learned',
    ADD UNIQUE INDEX IF NOT EXISTS uq_user_memory_key (user_id, memory_key);
