-- migrations/rollback/v1.0.1__rollback_user_table.sql
ALTER TABLE users DROP COLUMN IF EXISTS display_name;
