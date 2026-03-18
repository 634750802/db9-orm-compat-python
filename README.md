# db9 Python ORM Compatibility Test Suite

Runnable tests for Python ORM compatibility with [db9](https://db9.ai).

## ORMs Covered

| ORM | Test File | Driver |
|-----|-----------|--------|
| SQLAlchemy | `tests/test_sqlalchemy.py` | psycopg2 |
| Django ORM | `tests/test_django_orm.py` | psycopg2 |
| Peewee | `tests/test_peewee.py` | psycopg2 |
| Tortoise ORM | `tests/test_tortoise.py` | asyncpg |
| Piccolo | `tests/test_piccolo.py` | asyncpg |

## Setup

```bash
git clone https://github.com/634750802/db9-orm-compat-python
cd db9-orm-compat-python
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running Tests

Set your db9 connection string:

```bash
export PG_DSN="postgresql://tenant.admin:password@host:5433/postgres"
```

Run all tests:
```bash
pytest tests/ -v
```

Run a single ORM:
```bash
pytest tests/test_sqlalchemy.py -v
pytest tests/test_peewee.py -v
pytest tests/test_django_orm.py -v
pytest tests/test_tortoise.py -v
pytest tests/test_piccolo.py -v
```

## Test Categories

Each ORM test covers:
1. **Connection** — verify driver connects to db9
2. **DDL** — CREATE TABLE, DROP TABLE
3. **CRUD** — INSERT (with RETURNING), SELECT, UPDATE, DELETE
4. **Transactions** — commit, rollback, savepoints
5. **JSONB** — insert/query JSON fields
6. **Introspection** — table listing, column metadata (migration-critical)
7. **Upsert** — ON CONFLICT DO UPDATE

## Compatibility Report

See [COMPATIBILITY.md](./COMPATIBILITY.md) for the full analysis.
