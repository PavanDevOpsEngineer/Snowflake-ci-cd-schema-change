-- migrations/dml/v1.0.0__insert_reference_data.sql--
INSERT INTO <env>_db.PUBLIC.users (username, email)
VALUES ('system', 'system@company.com');
