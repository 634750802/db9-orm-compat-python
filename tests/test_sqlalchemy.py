"""SQLAlchemy compatibility tests for db9 (psycopg2 driver)."""
import json
import pytest
from sqlalchemy import (
    create_engine, text, inspect,
    MetaData, Table, Column, Integer, String, Boolean, JSON,
    UniqueConstraint, Index, select, insert, update, delete,
)
from sqlalchemy.orm import Session, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from tests.conftest import get_dsn

TABLE = "sa_compat_test"


class Base(DeclarativeBase):
    pass


class TestItem(Base):
    __tablename__ = TABLE
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    meta: Mapped[dict] = mapped_column(JSON, nullable=True)


@pytest.fixture(scope="module")
def engine():
    e = create_engine(get_dsn(), echo=False)
    Base.metadata.drop_all(e, checkfirst=True)
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e, checkfirst=True)
    e.dispose()


class TestConnection:
    def test_connect(self, engine):
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 AS n"))
            assert result.scalar() == 1

    def test_server_version(self, engine):
        with engine.connect() as conn:
            result = conn.execute(text("SHOW server_version"))
            version = result.scalar()
            assert version is not None


class TestDDL:
    def test_table_created(self, engine):
        insp = inspect(engine)
        assert TABLE in insp.get_table_names()

    def test_columns_exist(self, engine):
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns(TABLE)}
        assert {"id", "name", "active", "meta"} <= cols


class TestCRUD:
    def test_insert_returning(self, engine):
        with Session(engine) as s:
            item = TestItem(name="alpha", active=True, meta={"k": "v"})
            s.add(item)
            s.commit()
            assert item.id is not None and item.id > 0

    def test_select(self, engine):
        with Session(engine) as s:
            items = s.query(TestItem).filter_by(name="alpha").all()
            assert len(items) >= 1
            assert items[0].name == "alpha"

    def test_update(self, engine):
        with Session(engine) as s:
            item = s.query(TestItem).filter_by(name="alpha").first()
            item.name = "alpha_updated"
            s.commit()
            refreshed = s.get(TestItem, item.id)
            assert refreshed.name == "alpha_updated"

    def test_delete(self, engine):
        with Session(engine) as s:
            item = s.query(TestItem).filter_by(name="alpha_updated").first()
            s.delete(item)
            s.commit()
            assert s.query(TestItem).filter_by(name="alpha_updated").first() is None


class TestTransactions:
    def test_rollback(self, engine):
        with Session(engine) as s:
            s.add(TestItem(name="rollback_me"))
            s.flush()
            s.rollback()
            assert s.query(TestItem).filter_by(name="rollback_me").first() is None

    def test_savepoint(self, engine):
        with Session(engine) as s:
            s.add(TestItem(name="outer"))
            s.flush()
            sp = s.begin_nested()
            s.add(TestItem(name="inner_rollback"))
            s.flush()
            sp.rollback()
            s.commit()
            assert s.query(TestItem).filter_by(name="outer").first() is not None
            assert s.query(TestItem).filter_by(name="inner_rollback").first() is None


class TestJSONB:
    def test_json_insert_query(self, engine):
        with Session(engine) as s:
            s.add(TestItem(name="json_test", meta={"nested": {"a": 1}, "tags": ["x", "y"]}))
            s.commit()
            item = s.query(TestItem).filter_by(name="json_test").first()
            assert item.meta["nested"]["a"] == 1
            assert "x" in item.meta["tags"]


class TestUpsert:
    def test_on_conflict(self, engine):
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {TABLE}"))
            conn.execute(text(
                f"ALTER TABLE {TABLE} ADD CONSTRAINT uq_name UNIQUE (name)"
            ))
        try:
            with engine.begin() as conn:
                stmt = pg_insert(TestItem).values(name="upsert_test", active=True)
                conn.execute(stmt.on_conflict_do_update(
                    constraint="uq_name",
                    set_={"active": False}
                ))
                stmt2 = pg_insert(TestItem).values(name="upsert_test", active=True)
                conn.execute(stmt2.on_conflict_do_update(
                    constraint="uq_name",
                    set_={"active": False}
                ))
                result = conn.execute(
                    select(TestItem.active).where(TestItem.name == "upsert_test")
                )
                assert result.scalar() is False
        finally:
            with engine.begin() as conn:
                conn.execute(text(
                    f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS uq_name"
                ))


class TestIntrospection:
    def test_list_tables(self, engine):
        insp = inspect(engine)
        tables = insp.get_table_names()
        assert isinstance(tables, list)

    def test_get_columns(self, engine):
        insp = inspect(engine)
        cols = insp.get_columns(TABLE)
        names = [c["name"] for c in cols]
        assert "id" in names
        assert "name" in names

    def test_get_pk(self, engine):
        insp = inspect(engine)
        pk = insp.get_pk_constraint(TABLE)
        assert "id" in pk.get("constrained_columns", [])

    def test_get_indexes(self, engine):
        insp = inspect(engine)
        indexes = insp.get_indexes(TABLE)
        assert isinstance(indexes, list)
