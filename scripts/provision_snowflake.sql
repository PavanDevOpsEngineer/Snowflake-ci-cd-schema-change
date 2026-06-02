-- One-shot Snowflake provisioning SQL tailored for this repo
-- Run as ACCOUNTADMIN or SECURITYADMIN. Replace placeholders before running.
-- Usage: paste into Snowflake worksheet or run via snowsql as an admin.

-- Configuration
-- Databases (from config/*.yml)
-- DEV: DEV_DB
-- QA:  QA_DB
-- PROD: PROD_DB

-- Warehouse for CI/deploy (change name/size as needed)
CREATE WAREHOUSE IF NOT EXISTS deploy_wh
  WAREHOUSE_SIZE = 'XSMALL'
  WAREHOUSE_TYPE = 'STANDARD'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE;

-- Create databases
CREATE DATABASE IF NOT EXISTS DEV_DB;
CREATE DATABASE IF NOT EXISTS QA_DB;
CREATE DATABASE IF NOT EXISTS PROD_DB;

-- Create PUBLIC schema in each database (if you use other schema names, adjust)
CREATE SCHEMA IF NOT EXISTS DEV_DB.PUBLIC;
CREATE SCHEMA IF NOT EXISTS QA_DB.PUBLIC;
CREATE SCHEMA IF NOT EXISTS PROD_DB.PUBLIC;

-- Create a deploy role and user. Replace <DEPLOY_USER> and <STRONG_PASSWORD>.
CREATE ROLE IF NOT EXISTS deploy_role;
CREATE USER IF NOT EXISTS deploy_user
  PASSWORD = '<STRONG_PASSWORD>'
  DEFAULT_ROLE = deploy_role
  DEFAULT_WAREHOUSE = deploy_wh
  MUST_CHANGE_PASSWORD = FALSE;
GRANT ROLE deploy_role TO USER deploy_user;

-- Grants for the deploy role (adjust for least privilege)
GRANT USAGE ON WAREHOUSE deploy_wh TO ROLE deploy_role;

-- DEV privileges
GRANT USAGE ON DATABASE DEV_DB TO ROLE deploy_role;
GRANT USAGE ON SCHEMA DEV_DB.PUBLIC TO ROLE deploy_role;
GRANT CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT ON SCHEMA DEV_DB.PUBLIC TO ROLE deploy_role;
GRANT INSERT, UPDATE, DELETE, SELECT ON ALL TABLES IN SCHEMA DEV_DB.PUBLIC TO ROLE deploy_role;
GRANT INSERT, UPDATE, DELETE, SELECT ON FUTURE TABLES IN SCHEMA DEV_DB.PUBLIC TO ROLE deploy_role;

-- QA privileges
GRANT USAGE ON DATABASE QA_DB TO ROLE deploy_role;
GRANT USAGE ON SCHEMA QA_DB.PUBLIC TO ROLE deploy_role;
GRANT CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT ON SCHEMA QA_DB.PUBLIC TO ROLE deploy_role;
GRANT INSERT, UPDATE, DELETE, SELECT ON ALL TABLES IN SCHEMA QA_DB.PUBLIC TO ROLE deploy_role;
GRANT INSERT, UPDATE, DELETE, SELECT ON FUTURE TABLES IN SCHEMA QA_DB.PUBLIC TO ROLE deploy_role;

-- PROD privileges (review carefully before applying to prod)
GRANT USAGE ON DATABASE PROD_DB TO ROLE deploy_role;
GRANT USAGE ON SCHEMA PROD_DB.PUBLIC TO ROLE deploy_role;
GRANT CREATE TABLE, CREATE VIEW, CREATE STAGE, CREATE FILE FORMAT ON SCHEMA PROD_DB.PUBLIC TO ROLE deploy_role;
GRANT INSERT, UPDATE, DELETE, SELECT ON ALL TABLES IN SCHEMA PROD_DB.PUBLIC TO ROLE deploy_role;
GRANT INSERT, UPDATE, DELETE, SELECT ON FUTURE TABLES IN SCHEMA PROD_DB.PUBLIC TO ROLE deploy_role;

-- Create migration tracking tables in each environment schema
-- schema_migrations(filename VARCHAR, checksum VARCHAR, applied_at TIMESTAMP_LTZ, status VARCHAR, note VARCHAR)
-- schema_migration_lock(lock_name VARCHAR, owner VARCHAR, acquired_at TIMESTAMP_LTZ)

CREATE TABLE IF NOT EXISTS DEV_DB.PUBLIC.schema_migrations (
  filename VARCHAR,
  checksum VARCHAR,
  applied_at TIMESTAMP_LTZ,
  status VARCHAR,
  note VARCHAR
);

CREATE TABLE IF NOT EXISTS DEV_DB.PUBLIC.schema_migration_lock (
  lock_name VARCHAR,
  owner VARCHAR,
  acquired_at TIMESTAMP_LTZ
);

CREATE TABLE IF NOT EXISTS QA_DB.PUBLIC.schema_migrations (
  filename VARCHAR,
  checksum VARCHAR,
  applied_at TIMESTAMP_LTZ,
  status VARCHAR,
  note VARCHAR
);

CREATE TABLE IF NOT EXISTS QA_DB.PUBLIC.schema_migration_lock (
  lock_name VARCHAR,
  owner VARCHAR,
  acquired_at TIMESTAMP_LTZ
);

CREATE TABLE IF NOT EXISTS PROD_DB.PUBLIC.schema_migrations (
  filename VARCHAR,
  checksum VARCHAR,
  applied_at TIMESTAMP_LTZ,
  status VARCHAR,
  note VARCHAR
);

CREATE TABLE IF NOT EXISTS PROD_DB.PUBLIC.schema_migration_lock (
  lock_name VARCHAR,
  owner VARCHAR,
  acquired_at TIMESTAMP_LTZ
);

-- Notes:
-- * To use key-pair auth for `deploy_user`, create the user without a password and set
--   the public key on the user: ALTER USER deploy_user SET RSA_PUBLIC_KEY='...';
-- * Replace <STRONG_PASSWORD> before running, or prefer key-pair auth and remove the password.
-- * Run this as an admin role. Review grants for least privilege before applying to PROD.
