# Spec Delta

## ADDED Requirements

### Requirement: Database outage returns 503
When the database cannot be reached while serving any endpoint, the API SHALL answer 503 with code `SERVICE_UNAVAILABLE` and a generic message, without connection details, instead of 500.

#### Scenario: Login and registration during an outage
- **WHEN** the database is unreachable and a client calls `POST /auth/login` or `POST /auth/register`
- **THEN** the response is 503 `SERVICE_UNAVAILABLE` with the common `Error` body and no host, credential or SQL text

### Requirement: Unexpected failures never write request data to logs
An unexpected exception or database statement error MUST NOT cause SQL parameters, hashes, emails, passwords or tracebacks containing request data to be written to the logs; only the exception type, method and path are logged.

#### Scenario: Unhandled exception
- **WHEN** a handler raises an unexpected exception whose message contains personal data
- **THEN** the exception is not propagated to the server's error log with a traceback, and the log contains only its type, method and path

#### Scenario: Statement-level database error
- **WHEN** a SQL statement fails while storing an account
- **THEN** the error text available to logs does not contain the statement parameters (email, password hash)
