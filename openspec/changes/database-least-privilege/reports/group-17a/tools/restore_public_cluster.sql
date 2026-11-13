-- Rollback of the cluster-wide closing done by `db-bootstrap` (group 17A). Run as the administrator on
-- the maintenance database `postgres`:
--   docker exec -i <container> sh -c 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -f -' < restore_public_cluster.sql
-- The original state: templates `=c` (PUBLIC can connect), every other database the default ACL
-- (PUBLIC can connect and create temporary tables). A GRANT writes an explicit ACL that is equivalent
-- to the default one (`=Tc/owner`), not byte for byte the NULL it started as.
DO $$
DECLARE d record;
BEGIN
  FOR d IN SELECT datname, datistemplate FROM pg_database LOOP
    IF d.datistemplate THEN
      EXECUTE format('GRANT CONNECT ON DATABASE %I TO PUBLIC', d.datname);
    ELSE
      EXECUTE format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO PUBLIC', d.datname);
    END IF;
  END LOOP;
END $$;
