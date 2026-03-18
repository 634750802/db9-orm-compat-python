"""Piccolo ORM compatibility tests for db9 (asyncpg driver)."""
import pytest
import asyncio
from piccolo.engine.postgres import PostgresEngine
from piccolo.table import Table
from piccolo.columns import Varchar, Boolean, JSONB, Serial
from tests.conftest import get_dsn

TABLE = "pc_compat_test"

_dsn = get_dsn()
DB = PostgresEngine(config={"dsn": _dsn})


class PcItem(Table, db=DB, tablename=TABLE):
    id = Serial()
    name = Varchar(length=100)
    active = Boolean(default=True)
    meta = JSONB(null=True)


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module", autouse=True)
async def setup_piccolo(event_loop):
    await DB.start_connection_pool()
    await PcItem.create_table(if_not_exists=True).run()
    yield
    await PcItem.alter().drop_table(if_exists=True).run()
    await DB.close_connection_pool()


@pytest.mark.asyncio
class TestConnection:
    async def test_connect(self):
        result = await PcItem.raw("SELECT 1 AS n").run()
        assert result[0]["n"] == 1


@pytest.mark.asyncio
class TestCRUD:
    async def test_insert(self):
        item = PcItem(name="pc_alpha", active=True, meta={"k": "v"})
        await item.save().run()
        assert item._meta.primary_key is not None

    async def test_select(self):
        items = await PcItem.select().where(PcItem.name == "pc_alpha").run()
        assert len(items) >= 1

    async def test_update(self):
        await PcItem.update({PcItem.name: "pc_alpha_updated"}).where(
            PcItem.name == "pc_alpha"
        ).run()
        items = await PcItem.select().where(PcItem.name == "pc_alpha_updated").run()
        assert len(items) >= 1

    async def test_delete(self):
        await PcItem.delete().where(PcItem.name == "pc_alpha_updated").run()
        items = await PcItem.select().where(PcItem.name == "pc_alpha_updated").run()
        assert len(items) == 0


@pytest.mark.asyncio
class TestJSONB:
    async def test_json_field(self):
        item = PcItem(name="pc_json", meta={"nested": {"a": 1}})
        await item.save().run()
        results = await PcItem.select().where(PcItem.name == "pc_json").run()
        assert results[0]["meta"]["nested"]["a"] == 1
