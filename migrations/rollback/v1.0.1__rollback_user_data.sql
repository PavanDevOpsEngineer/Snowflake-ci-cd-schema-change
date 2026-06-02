-- migrations/rollback/v1.0.1__rollback_user_data.sql
DELETE FROM users WHERE username = 'system' AND email = 'system@company.com';
