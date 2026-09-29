-- 001 — office_documents: add project_id / phase_id / doc_role
-- Only for a phoenix_office_db created from a schema.sql older than
-- 2026-09-28. A fresh database gets these three columns from schema.sql
-- itself (CREATE TABLE office_documents) and must NOT run this file.
--
-- SQLite/D1 has no "ADD COLUMN IF NOT EXISTS", and a failed ALTER inside a
-- --file run aborts the rest, so check first:
--   wrangler d1 execute phoenix_office_db --command="PRAGMA table_info(office_documents)" --remote
-- If project_id is already listed, stop — nothing to do (the live
-- phoenix_office_db had all three applied by hand on 2026-09-25).
-- Otherwise:
--   wrangler d1 execute phoenix_office_db --file=migrations/001-office-documents-project-columns.sql --remote
-- then re-run schema.sql (its idx_documents_project/idx_documents_phase
-- indexes are CREATE IF NOT EXISTS and need these columns to exist).
--
-- Additive only. Nullable soft-FKs, same idiom as supersedes_hex; does not
-- touch hex/hash_sha3/hash_blake2 or any tamper-evidence guarantee.
ALTER TABLE office_documents ADD COLUMN project_id TEXT DEFAULT NULL;
ALTER TABLE office_documents ADD COLUMN phase_id   TEXT DEFAULT NULL;
ALTER TABLE office_documents ADD COLUMN doc_role   TEXT DEFAULT NULL;
