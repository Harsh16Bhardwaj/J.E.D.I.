-- JEDI authenticates and authorizes every request in FastAPI. Supabase's Data
-- API roles must never bypass those checks by reading the public schema.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;

-- Keep later Prisma-created objects backend-only by default. New tables should
-- also explicitly enable RLS in the migration that creates them.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
REVOKE ALL PRIVILEGES ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
REVOKE ALL PRIVILEGES ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
REVOKE ALL PRIVILEGES ON FUNCTIONS FROM anon, authenticated;

-- No policies are created intentionally. The postgres owner used by FastAPI
-- bypasses RLS; anon/authenticated receive no direct table access.
DO $$
DECLARE
    target RECORD;
BEGIN
    FOR target IN
        SELECT schemaname, tablename
        FROM pg_catalog.pg_tables
        WHERE schemaname = 'public'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',
            target.schemaname,
            target.tablename
        );
    END LOOP;
END
$$;
