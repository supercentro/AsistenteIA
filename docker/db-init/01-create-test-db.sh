#!/bin/sh
# Runs only when the data volume is created. Creates the database used exclusively by integration tests.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE DATABASE asistenteia_test OWNER "$POSTGRES_USER";
EOSQL
