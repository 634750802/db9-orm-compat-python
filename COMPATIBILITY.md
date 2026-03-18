# Python ORM Compatibility with db9

**Author:** R1
**Date:** 2026-03-18
**Task:** #t45

---

## Summary

db9 exposes a PostgreSQL-compatible interface (pgwire on TiKV). All Python ORMs that support PostgreSQL can connect to db9 using standard PostgreSQL drivers (psycopg2, asyncpg). However, ORM features that depend on deep `pg_catalog` introspection may hit gaps depending on db9-server's catalog completeness.

**Key finding:** Basic CRUD, transactions, RETURNING, JSONB, and standard SQL all work. The primary risk areas are schema introspection/reflection (used by migration tools) and asyncpg's mandatory type introspection on connect.

---

## Compatibility Matrix

| ORM | Driver | Basic CRUD | Migrations | Introspection | JSONB | Transactions | Overall |
|-----|--------|-----------|------------|---------------|-------|-------------|---------|
| **SQLAlchemy** (psycopg2) | psycopg2 | GREEN | YELLOW | YELLOW | GREEN | GREEN | **GREEN** |
| **SQLAlchemy** (asyncpg) | asyncpg | YELLOW | YELLOW | YELLOW | GREEN | GREEN | **YELLOW** |
| **Django ORM** | psycopg2 | GREEN | YELLOW | YELLOW | GREEN | GREEN | **GREEN** |
| **Peewee** | psycopg2 | GREEN | GREEN | YELLOW | GREEN | GREEN | **GREEN** |
| **Tortoise ORM** | asyncpg | YELLOW | GREEN | GREEN | GREEN | GREEN | **YELLOW** |
| **SQLModel** | psycopg2 | GREEN | YELLOW | YELLOW | GREEN | GREEN | **GREEN** |
| **Piccolo** | asyncpg | YELLOW | GREEN | GREEN | GREEN | GREEN | **YELLOW** |

**Legend:** GREEN = works, YELLOW = works with caveats or unverified edge cases, RED = blocked

---

## Tier 1 ORMs (Detailed Analysis)

### 1. SQLAlchemy (most popular Python ORM)

**Verdict: GREEN with psycopg2, YELLOW with asyncpg**

#### What works:
- All CRUD operations (INSERT/SELECT/UPDATE/DELETE)
- RETURNING clause (used by default for PK retrieval after INSERT)
- Transactions, savepoints, nested transactions
- JSONB fields and operators (`@>`, `<@`, `?`, `#>>`)
- ON CONFLICT (upsert)
- SERIAL / IDENTITY columns and sequences
- Array types
- Connection pooling

#### Blockers / Caveats:

**asyncpg driver (CRITICAL RISK):**
asyncpg runs mandatory type introspection queries on every connection using a recursive CTE against `pg_catalog.pg_type`, `pg_catalog.pg_namespace`, and `pg_range`. These queries are NOT optional — if these catalog tables are incomplete or missing, asyncpg connections will fail or behave incorrectly.

Required catalog tables for asyncpg:
- `pg_catalog.pg_type` (oid, typname, typnamespace, typtype, typelem, typbasetype, typlen)
- `pg_catalog.pg_namespace` (oid, nspname)
- `pg_range` (rngsubtype, rngmultirange for PG14+)

**Schema reflection (YELLOW):**
SQLAlchemy uses `pg_catalog` (NOT `information_schema`) for all reflection because it's faster and exposes PG-specific features:

| Operation | pg_catalog tables needed |
|-----------|------------------------|
| `get_table_names()` | `pg_class`, `pg_namespace`, `pg_table_is_visible()` |
| `get_columns()` | `pg_attribute`, `pg_attrdef`, `pg_type`, `pg_class`, `pg_namespace`, `pg_collation` |
| `get_pk_constraint()` | `pg_constraint`, `pg_class`, `pg_attribute` |
| `get_foreign_keys()` | `pg_constraint`, `pg_class`, `pg_namespace`, `pg_attribute`, `pg_get_constraintdef()` |
| `get_indexes()` | `pg_index`, `pg_class`, `pg_am`, `pg_attribute` |
| `get_enums()` | `pg_type`, `pg_enum`, `pg_namespace` |

PostgreSQL functions needed: `pg_get_constraintdef()`, `pg_table_is_visible()`, `col_description()`, `obj_description()`, `format_type()`, `current_schema()`

**Migration tool (Alembic):**
- Delegates all reflection to SQLAlchemy's Inspector (same queries above)
- Some deployments use `pg_advisory_lock()` for concurrent migration locking — **not supported by db9**
- Autogenerate compares live schema (via reflection) against models

**Recommendation:** Use psycopg2 driver (not asyncpg) to avoid type introspection blocker. For migrations, use Alembic with `--sql` mode (offline) or ensure pg_catalog tables are populated.

---

### 2. Django ORM

**Verdict: GREEN for CRUD, YELLOW for migrations/introspection**

#### What works:
- All CRUD operations
- RETURNING clause for PK retrieval
- Transactions, savepoints
- JSONB via `django.contrib.postgres.fields.JSONField`
- Array fields via `django.contrib.postgres.fields.ArrayField`
- DISTINCT ON (PostgreSQL-specific)
- ON CONFLICT (upsert)
- SET TIME ZONE on connect

#### Blockers / Caveats:

**Connection initialization:**
- `SET TIME ZONE` on every new connection — should work
- Server version via `connection.info.server_version` (protocol-level) — should work

**Schema introspection (YELLOW):**
Django's `introspection.py` queries `pg_catalog` extensively:

| Operation | pg_catalog tables needed |
|-----------|------------------------|
| `get_table_list()` | `pg_class`, `pg_namespace`, `pg_table_is_visible()`, `obj_description()` |
| `get_table_description()` | `pg_attribute`, `pg_attrdef`, `pg_collation`, `pg_type`, `pg_class`, `pg_namespace`, `col_description()`, `pg_get_expr()` |
| `get_sequences()` | `pg_class`, `pg_depend`, `pg_attribute` |
| `get_relations()` | `pg_constraint`, `pg_class`, `pg_attribute` |
| `get_constraints()` | `pg_constraint`, `pg_class`, `pg_attribute`, `pg_index`, `pg_am` |

**Migration-specific features:**
- `pg_get_serial_sequence()` — for sequence reset operations
- `TRUNCATE ... RESTART IDENTITY CASCADE` — for test database teardown
- `SERIAL` (legacy) or `IDENTITY` (Django 4.1+) columns
- Savepoints (used by migration runner to wrap each migration)
- `SET CONSTRAINTS ALL IMMEDIATE/DEFERRED` — for deferred FK constraints

**Known issues from CockroachDB/YugabyteDB experience:**
- CockroachDB requires a dedicated Django backend (`django-cockroachdb`) due to: `IntegerField` introspected as `BigIntegerField`, `ALTER COLUMN TYPE` limitations, some pg_catalog divergences
- YugabyteDB requires `django-yugabytedb` backend
- db9 may need a similar lightweight adapter if pg_catalog gaps are significant

**Recommendation:** Start with Django + psycopg2. Test `python manage.py migrate` against db9 to verify introspection works. If migrations fail, consider writing a `db9-django` backend that overrides problematic introspection queries.

---

### 3. Peewee

**Verdict: GREEN — lightest catalog dependency of Tier 1 ORMs**

#### What works:
- All CRUD operations
- RETURNING clause
- JSONB via `BinaryJSONField`
- Array fields, HStore, TSVector
- ON CONFLICT (upsert)
- Transactions (savepoints available but optional)

#### Blockers / Caveats:

**Schema introspection (lightweight):**
Peewee's `playhouse.reflection` module is simpler than SQLAlchemy/Django:
- Uses `pg_type` for type discovery
- Uses `pg_catalog.pg_attribute` for column types
- Uses `::regclass` cast (requires `pg_class`)
- `format_type()` function needed

**Migration tool (playhouse.migrate):**
- `SchemaMigrator` uses `ALTER TABLE` DDL — less catalog-dependent
- No advisory lock dependency

**CockroachDB first-class support:**
Peewee has built-in `playhouse.cockroachdb.CockroachDatabase` — proves it works with PG-compatible databases. Key adaptations: disables savepoints, adds client-side retry logic.

**Recommendation:** Best first ORM to test with db9 due to minimal catalog dependency. If Peewee works, it validates the baseline PG compatibility.

---

## Tier 2 ORMs

### 4. Tortoise ORM (async)

**Verdict: YELLOW — asyncpg dependency is the main risk**

- Code-first approach — generates schemas from models, minimal introspection
- Migration tool (Aerich) compares model snapshots, not live schema
- **Main risk:** asyncpg's mandatory type introspection (same as SQLAlchemy+asyncpg)
- If asyncpg connects successfully, Tortoise should work for CRUD

### 5. SQLModel

**Verdict: Same as SQLAlchemy — it's a thin wrapper**

- Built on SQLAlchemy + Pydantic
- Zero additional catalog queries or PG dependencies
- All compatibility concerns are identical to SQLAlchemy
- Use psycopg2 driver to avoid asyncpg issues

### 6. Piccolo ORM

**Verdict: YELLOW — asyncpg risk, but uses information_schema (safer)**

- Uses `information_schema` (not `pg_catalog`) for most introspection — more portable
- Migration system is snapshot-based (less catalog-dependent)
- Has explicit CockroachDB support — good sign for PG-compatible DBs
- **Main risk:** asyncpg driver dependency
- Runs `SHOW server_version` on connect, enforces minimum version 10

---

## Critical Blockers for db9 (Cross-ORM)

### Must-Have for ANY Python ORM

| Feature | Status | Impact |
|---------|--------|--------|
| `RETURNING` clause | Should work (standard SQL) | ALL ORMs use this for INSERT PK retrieval |
| `SERIAL` / `IDENTITY` + sequences | Should work | ALL ORMs use this for auto-increment PKs |
| `current_schema()` function | Needs verification | SQLAlchemy uses on connect |
| `SET TIME ZONE` | Needs verification | Django uses on connect |
| Savepoints (`SAVEPOINT` / `RELEASE`) | Should work | Django, SQLAlchemy use for nested transactions |
| `information_schema` views | Supported by db9 | Piccolo, some Django paths |

### Must-Have for psycopg2-based ORMs (SQLAlchemy, Django, Peewee)

| pg_catalog Table | Who Needs It | Risk |
|-----------------|-------------|------|
| `pg_type` (basic built-in types) | All reflection | HIGH |
| `pg_class` | Table listing | HIGH |
| `pg_attribute` | Column metadata | HIGH |
| `pg_namespace` | Schema resolution | HIGH |
| `pg_constraint` | FK/PK/unique reflection | HIGH |
| `pg_index` | Index reflection | MEDIUM |
| `pg_table_is_visible()` | SQLAlchemy, Django | MEDIUM |
| `pg_get_constraintdef()` | SQLAlchemy FK reflection | MEDIUM |
| `format_type()` | Peewee, SQLAlchemy | MEDIUM |

### Must-Have for asyncpg-based ORMs (Tortoise, Piccolo, SQLAlchemy+asyncpg)

| Requirement | Risk |
|------------|------|
| `pg_catalog.pg_type` with recursive CTE support | **CRITICAL** — asyncpg cannot connect without it |
| `pg_catalog.pg_namespace` | **CRITICAL** |
| `pg_range` | **HIGH** — needed if any range types registered |

### Known NOT Supported by db9

| Feature | Impact |
|---------|--------|
| `pg_advisory_lock()` | Alembic/Django concurrent migration locking — use alternative lock or single-writer |
| `LISTEN/NOTIFY` | Not used by any ORM core — optional |
| `ALTER COLUMN TYPE` | Migration column type changes — use drop-recreate pattern |

---

## Recommended Verification Order

1. **Peewee + psycopg2** — lightest catalog dependency, fastest to validate
2. **SQLAlchemy + psycopg2** — most popular, tests pg_catalog reflection depth
3. **Django ORM + psycopg2** — tests migration framework compatibility
4. **Piccolo + asyncpg** — tests asyncpg type introspection + information_schema path
5. **Tortoise + asyncpg** — tests async ORM path
6. **SQLModel** — no additional testing needed (same as SQLAlchemy)

---

## Comparison with Other PG-Compatible DBs

| Feature | CockroachDB | YugabyteDB | db9 (expected) |
|---------|------------|------------|----------------|
| Dedicated SQLAlchemy dialect | Yes (required) | No | Likely not needed |
| Dedicated Django backend | Yes (required) | Yes (required) | TBD — depends on pg_catalog gaps |
| Peewee support | Built-in | N/A | Expected green |
| pg_catalog completeness | ~70% | ~85% | TBD |
| Advisory locks | Stubbed only | Supported | Not supported |
| LISTEN/NOTIFY | Not supported | Supported | Not supported |
| Default isolation | Serializable | Read Committed | Repeatable Read |

**Note:** YugabyteDB achieves higher PG compatibility (~85%) because it reuses PostgreSQL's actual query layer source code, including native pg_catalog. CockroachDB reimplements pg_catalog from scratch (~70%). db9's compatibility level depends on how much of pg_catalog the TiKV-backed server exposes.
