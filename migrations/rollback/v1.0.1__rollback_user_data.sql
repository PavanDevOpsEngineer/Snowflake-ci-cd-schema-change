-- migrations/rollback/v1.0.1__rollback_user_data.sql
DELETE FROM <env>_db.PUBLIC.users WHERE username = 'system' AND email = 'system@company.com';
