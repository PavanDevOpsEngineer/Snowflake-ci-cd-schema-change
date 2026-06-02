-- migrations/ddl/v1.0.1__add_user_table.sql--
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(200);
