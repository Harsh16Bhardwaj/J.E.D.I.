"""Additive migration safety checks; PostgreSQL uses an explicit disposable DB."""

import os
import re
from pathlib import Path

import psycopg
import pytest

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "prisma/migrations/20261102000000_resume_learning/migration.sql"
)


def test_resume_learning_migration_is_additive_and_transactional():
    sql = MIGRATION.read_text()
    statements = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    ).upper()
    assert not re.search(
        r"(?m)^\s*(?:DROP\s+(?:TABLE|COLUMN)|TRUNCATE\b|DELETE\s+FROM\b|UPDATE\s+)",
        statements,
    )
    assert statements.strip().startswith("BEGIN;")
    assert statements.strip().endswith("COMMIT;")
    assert 'CREATE TABLE "public"."ResumeEvidence"' in sql
    assert 'CREATE TABLE "public"."LearningAttempt"' in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "lock_timeout" in sql


def test_resume_learning_migration_preserves_rows_and_rolls_back():
    dsn = os.getenv("JEDI_MIGRATION_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set JEDI_MIGRATION_TEST_DATABASE_URL to a disposable test DB")
    with psycopg.connect(dsn, autocommit=True) as connection:
        if not connection.info.dbname.startswith("jedi_migration_test_"):
            pytest.fail("Refusing migration tests outside a disposable named database")
        connection.execute('CREATE TABLE "GroupMember" (id TEXT PRIMARY KEY)')
        connection.execute('INSERT INTO "GroupMember" VALUES (%s)', ("member-test",))
        connection.execute('CREATE TABLE "Job" (id TEXT PRIMARY KEY, data JSONB)')
        connection.execute(
            'INSERT INTO "Job" VALUES (%s, %s::jsonb)',
            ("existing-job", '{"notes":"preserve me", "score": 42}'),
        )
        before = connection.execute('SELECT * FROM "Job" ORDER BY id').fetchall()
        # Supabase-style roles may already exist in the disposable cluster.
        for role in ("anon", "authenticated"):
            if not connection.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
                (role,),
            ).fetchone()[0]:
                connection.execute(
                    psycopg.sql.SQL("CREATE ROLE {} NOLOGIN").format(
                        psycopg.sql.Identifier(role)
                    )
                )
        sql = MIGRATION.read_text()
        # A failure after all DDL must roll back both new tables.
        with pytest.raises(psycopg.errors.DivisionByZero):
            connection.execute(sql.replace("COMMIT;", "SELECT 1 / 0;\nCOMMIT;"))
        connection.execute("ROLLBACK")
        assert (
            connection.execute(
                "SELECT to_regclass('public.\"ResumeEvidence\"')"
            ).fetchone()[0]
            is None
        )
        assert (
            connection.execute('SELECT * FROM "Job" ORDER BY id').fetchall() == before
        )
        connection.execute(sql)
        assert (
            connection.execute('SELECT * FROM "Job" ORDER BY id').fetchall() == before
        )
        assert connection.execute('SELECT id FROM "GroupMember"').fetchall() == [
            ("member-test",)
        ]
        for table in ("ResumeEvidence", "LearningAttempt"):
            assert connection.execute(
                "SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass",
                (f'public."{table}"',),
            ).fetchone()[0]
            for role in ("anon", "authenticated"):
                assert not connection.execute(
                    "SELECT has_table_privilege(%s, %s, 'SELECT')",
                    (role, f'public."{table}"'),
                ).fetchone()[0]
        connection.execute(
            'INSERT INTO "ResumeEvidence" '
            '(id, "groupMemberId", evidence, "updatedAt") '
            "VALUES ('resume-test', 'member-test', '{}'::jsonb, NOW())"
        )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            connection.execute(
                'INSERT INTO "ResumeEvidence" '
                '(id, "groupMemberId", evidence, "updatedAt") '
                "VALUES ('bad-owner', 'missing-member', '{}'::jsonb, NOW())"
            )
        assert connection.execute('SELECT COUNT(*) FROM "Job"').fetchone()[0] == 1
