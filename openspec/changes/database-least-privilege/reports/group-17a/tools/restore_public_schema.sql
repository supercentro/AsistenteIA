-- Rollback of `REVOKE ALL ON SCHEMA public FROM PUBLIC` done by `db-bootstrap` in the application
-- database (group 17A). Run as the administrator on that database:
--   docker exec -i <container> sh -c 'psql -U "$POSTGRES_USER" -d asistenteia -v ON_ERROR_STOP=1 -f -' < restore_public_schema.sql
-- PostgreSQL 15 default: PUBLIC has USAGE on schema public; the database owner has USAGE and CREATE.
GRANT USAGE ON SCHEMA public TO PUBLIC;
