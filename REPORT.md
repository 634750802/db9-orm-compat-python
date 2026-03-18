# Python ORM Compatibility — Staging Test Results

**Date:** 2026-03-18
**Target:** db9 staging (api.staging.db9.ai), database `dark-yak-91`
**Author:** R1

---

## Test Results Summary

| ORM | Driver | Tests | Passed | Failed | Result |
|-----|--------|-------|--------|--------|--------|
| **Peewee** | psycopg2 | 13 | 13 | 0 | **100% GREEN** |
| **SQLAlchemy** | psycopg2 | 16 | 14 | 2 | **87.5% GREEN** (introspection gap) |
| **Django ORM** | psycopg2 | 12 | 11 | 1 | **91.7% GREEN** (introspection gap) |
| **Tortoise** | asyncpg | 8 | 0 | 8 | **RED — blocked** |
| **Piccolo** | asyncpg | — | — | — | **RED — blocked** (same asyncpg issue) |

**Total: 49 tests across 5 ORMs. 38 passed, 11 failed.**

---

## Detailed Results

### Peewee — 13/13 PASSED (100%)

All categories green:
- Connection: 2/2
- CRUD (insert/select/update/delete): 4/4
- Transactions (atomic commit/rollback/savepoint): 3/3
- JSONB: 1/1
- Upsert (ON CONFLICT): 1/1
- Introspection (get_tables/get_columns): 2/2

**Verdict: Fully compatible. Recommended as the first Python ORM for db9.**

### SQLAlchemy (psycopg2) — 14/16 PASSED (87.5%)

Passed:
- Connection (connect, server_version): 2/2
- DDL (table_created): 1/1
- CRUD (insert_returning, select, update, delete): 4/4
- Transactions (rollback, savepoint): 2/2
- JSONB: 1/1
- Upsert (ON CONFLICT): 1/1
- Introspection (list_tables, get_pk, get_indexes): 3/3

Failed:
- `test_columns_exist` — `get_columns()` fails with `psycopg2.errors.UndefinedTable: relation "10000000002" does not exist`
- `test_get_columns` — same error

**Root cause:** SQLAlchemy's `get_columns()` queries `pg_catalog.pg_attribute` with a JOIN on `pg_class`, and db9's `pg_class` returns OIDs that don't correctly resolve back via `::regclass` or `pg_attribute.attrelid`. The numeric OID `10000000002` suggests db9 uses a different OID numbering scheme than standard PostgreSQL.

**Verdict: CRUD/transactions/JSONB fully green. Column introspection broken — affects Alembic autogenerate and `inspect()` but NOT normal ORM operations.**

### Django ORM — 11/12 PASSED (91.7%)

Passed:
- Connection (connect, server_version): 2/2
- CRUD (create, read, update, delete): 4/4
- Transactions (atomic_commit, atomic_rollback, savepoint): 3/3
- JSONB: 1/1
- Introspection (get_table_list): 1/1

Failed:
- `test_get_table_description` — `column "t.typnotnull" does not exist`

**Root cause:** Django's `get_table_description()` queries `pg_catalog.pg_type` and references column `typnotnull`, which doesn't exist in db9's `pg_type` implementation. This is a pg_catalog schema gap.

**Verdict: CRUD/transactions/JSONB fully green. Column introspection broken — affects `python manage.py inspectdb` and migration introspection, but NOT normal ORM operations or `migrate` with code-first models.**

### Tortoise ORM (asyncpg) — 0/8 PASSED (RED)

All tests failed at setup with:
```
asyncpg.exceptions.FeatureNotSupportedError: Unsupported statement: Close { cursor: All }
```

**Root cause:** asyncpg sends a `Close` pgwire message during connection pool reset (`connection.reset()`). db9-server does not support the `Close` protocol message. This blocks ALL asyncpg-based operations — not just Tortoise, but any ORM using asyncpg (Piccolo, SQLAlchemy+asyncpg, etc.).

**Verdict: RED — completely blocked by pgwire `Close` message gap. Not usable until db9-server implements `Close` support.**

### Piccolo ORM (asyncpg) — NOT RUN

Skipped because it uses the same asyncpg driver and will hit the same `Close` message blocker.

**Verdict: RED — blocked by same asyncpg issue.**

---

## Blocker Summary

| Blocker | Severity | Affects | Fix Location |
|---------|----------|---------|-------------|
| **pgwire `Close` message not supported** | **CRITICAL** | ALL asyncpg-based ORMs (Tortoise, Piccolo, SQLAlchemy+asyncpg) | db9-server pgwire handler |
| **`pg_type.typnotnull` column missing** | HIGH | Django introspection | db9-server pg_catalog schema |
| **`pg_attribute` OID resolution fails** | HIGH | SQLAlchemy column introspection | db9-server pg_catalog OID numbering |
| **Advisory locks not supported** | MEDIUM | Alembic/Django/Knex concurrent migrations | db9-server (or ORM config workaround) |

---

## Recommendations

1. **Use Peewee for immediate Python ORM needs** — 100% compatible today
2. **SQLAlchemy and Django work for CRUD** — only introspection is broken, which doesn't affect code-first workflows
3. **Fix pgwire `Close` message** — this single fix unblocks ALL async Python ORMs
4. **Fix `pg_type.typnotnull`** — small catalog gap that blocks Django introspection
5. **Fix `pg_attribute` OID resolution** — blocks SQLAlchemy column reflection
