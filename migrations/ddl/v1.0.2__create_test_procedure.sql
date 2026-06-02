-- v1.0.2__create_test_procedure.sql
-- Creates a test stored procedure to verify CI/CD execution and creates a test table
-- Uses <env> placeholders which are replaced by the CI workflows (dev/qa/prod)

CREATE OR REPLACE PROCEDURE <env>_db.PUBLIC.sp_create_cicd_test()
RETURNS STRING
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
BEGIN
  -- Create a simple test table for CI/CD validation
  CREATE TABLE IF NOT EXISTS <env>_db.PUBLIC.cicd_test_table (
    id INTEGER AUTOINCREMENT PRIMARY KEY,
    name STRING,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
  );

  -- Insert a sample row so tests can verify presence
  INSERT INTO <env>_db.PUBLIC.cicd_test_table (name) VALUES ('ci-test');

  RETURN 'cicd_test_created';
END;
$$;

-- Execute the procedure to create table and insert sample data
CALL <env>_db.PUBLIC.sp_create_cicd_test();
