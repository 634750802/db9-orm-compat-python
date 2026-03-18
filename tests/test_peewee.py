"""Peewee compatibility tests for db9 (psycopg2 driver)."""
import json
import pytest
from urllib.parse import urlparse
from peewee import (
    PostgresqlDatabase, Model,
    AutoField, CharField, BooleanField,
)
from playhouse.postgres_ext import BinaryJSONField
from tests.conftest import get_dsn

TABLE = "pw_compat_test"


def _parse_dsn(dsn):
    u = urlparse(dsn)
    return dict(
        database=u.path.lstrip("/") or "postgres",
        user=u.username,
        password=u.password,
        host=u.hostname,
        port=u.port or 5433,
    )


@pytest.fixture(scope="module")
def db():
    params = _parse_dsn(get_dsn())
    database = PostgresqlDatabase(**params)
    database.connect()

    class BaseModel(Model):
        class Meta:
            database_obj = database

    class PwItem(BaseModel):
        id = AutoField()
        name = CharField(max_length=100)
        active = BooleanField(default=True)
        meta = BinaryJSONField(null=True)

        class Meta:
            database = database
            table_name = TABLE

    database.drop_tables([PwItem], safe=True)
    database.create_tables([PwItem])

    yield database, PwItem

    database.drop_tables([PwItem], safe=True)
    database.close()


class TestConnection:
    def test_connect(self, db):
        database, _ = db
        assert not database.is_closed()

    def test_raw_query(self, db):
        database, _ = db
        cursor = database.execute_sql("SELECT 1 AS n")
        assert cursor.fetchone()[0] == 1


class TestCRUD:
    def test_insert(self, db):
        _, PwItem = db
        item = PwItem.create(name="alpha", active=True, meta={"k": "v"})
        assert item.id is not None

    def test_select(self, db):
        _, PwItem = db
        items = list(PwItem.select().where(PwItem.name == "alpha"))
        assert len(items) >= 1

    def test_update(self, db):
        _, PwItem = db
        PwItem.update(name="alpha_updated").where(PwItem.name == "alpha").execute()
        item = PwItem.get_or_none(PwItem.name == "alpha_updated")
        assert item is not None

    def test_delete(self, db):
        _, PwItem = db
        PwItem.delete().where(PwItem.name == "alpha_updated").execute()
        assert PwItem.get_or_none(PwItem.name == "alpha_updated") is None


class TestTransactions:
    def test_atomic_commit(self, db):
        database, PwItem = db
        with database.atomic():
            PwItem.create(name="tx_commit")
        assert PwItem.get_or_none(PwItem.name == "tx_commit") is not None

    def test_atomic_rollback(self, db):
        database, PwItem = db
        try:
            with database.atomic():
                PwItem.create(name="tx_rollback")
                raise ValueError("force rollback")
        except ValueError:
            pass
        assert PwItem.get_or_none(PwItem.name == "tx_rollback") is None

    def test_savepoint(self, db):
        database, PwItem = db
        with database.atomic():
            PwItem.create(name="sp_outer")
            try:
                with database.atomic():
                    PwItem.create(name="sp_inner")
                    raise ValueError("rollback inner")
            except ValueError:
                pass
        assert PwItem.get_or_none(PwItem.name == "sp_outer") is not None
        assert PwItem.get_or_none(PwItem.name == "sp_inner") is None


class TestJSONB:
    def test_json_insert_query(self, db):
        _, PwItem = db
        PwItem.create(name="json_test", meta={"nested": {"a": 1}})
        item = PwItem.get(PwItem.name == "json_test")
        assert item.meta["nested"]["a"] == 1


class TestUpsert:
    def test_on_conflict(self, db):
        database, PwItem = db
        database.execute_sql(f"DELETE FROM {TABLE}")
        database.execute_sql(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_pw_name ON {TABLE} (name)"
        )
        try:
            PwItem.insert(name="upsert_pw", active=True).on_conflict(
                conflict_target=[PwItem.name],
                update={PwItem.active: False},
            ).execute()
            PwItem.insert(name="upsert_pw", active=True).on_conflict(
                conflict_target=[PwItem.name],
                update={PwItem.active: False},
            ).execute()
            item = PwItem.get(PwItem.name == "upsert_pw")
            assert item.active is False
        finally:
            database.execute_sql(f"DROP INDEX IF EXISTS uq_pw_name")


class TestIntrospection:
    def test_get_tables(self, db):
        database, _ = db
        tables = database.get_tables()
        assert TABLE in tables

    def test_get_columns(self, db):
        database, _ = db
        cols = database.get_columns(TABLE)
        names = [c.name for c in cols]
        assert "id" in names
        assert "name" in names
