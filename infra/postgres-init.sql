-- Create the restricted application role used by the backend at runtime.
-- PostgreSQL bypasses RLS for superusers and table owners, so the app must
-- connect as a non-superuser role that is NOT the table owner.
--
-- NOTE: 'scholarhub_app_pw' is a LOCAL DEV DEFAULT matching the
-- SCHOLARHUB_APP_DB_PASSWORD fallback in infra/docker-compose.yml.
-- This script runs only on first initialization of an empty data volume.
-- For real deployments, change the password here BEFORE first init and
-- set SCHOLARHUB_APP_DB_PASSWORD in your .env accordingly.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'scholarhub_app') THEN
    CREATE ROLE scholarhub_app
      LOGIN
      PASSWORD 'scholarhub_app_pw'
      NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END $$;

-- Grant access to the application schema (tables + sequences created by
-- alembic migrations owned by the POSTGRES_USER superuser).
GRANT USAGE ON SCHEMA public TO scholarhub_app;
GRANT ALL ON ALL TABLES IN SCHEMA public TO scholarhub_app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO scholarhub_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO scholarhub_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO scholarhub_app;
