-- migrations/ddl/v1.0.0__create_initial_schema.sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER AUTOINCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
