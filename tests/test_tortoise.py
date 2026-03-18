"""Tortoise ORM compatibility tests for db9 (asyncpg driver)."""
import pytest
import asyncio
from tortoise import Tortoise, fields
from tortoise.models import Model
from tests.conftest import get_dsn

TABLE = "tt_compat_test"

# Convert postgresql:// to postgres:// for tortoise
_dsn = get_dsn().replace("postgresql://", "postgres://", 1)


class TtItem(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100)
    active = fields.BooleanField(default=True)
    meta = fields.JSONField(null=True)

    class Meta:
        table = TABLE


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module", autouse=True)
async def setup_tortoise(event_loop):
    await Tortoise.init(
        db_url=_dsn,
        modules={"models": ["tests.test_tortoise"]},
    )
    await Tortoise.generate_schemas(safe=True)
    yield
    await TtItem.all().delete()
    await Tortoise.close_connections()


@pytest.mark.asyncio
class TestConnection:
    async def test_connect(self):
        conn = Tortoise.get_connection("default")
        result = await conn.execute_query("SELECT 1 AS n")
        assert result[1][0]["n"] == 1


@pytest.mark.asyncio
class TestCRUD:
    async def test_create(self):
        item = await TtItem.create(name="tt_alpha", active=True, meta={"k": "v"})
        assert item.id is not None

    async def test_read(self):
        items = await TtItem.filter(name="tt_alpha")
        assert len(items) >= 1

    async def test_update(self):
        await TtItem.filter(name="tt_alpha").update(name="tt_alpha_updated")
        item = await TtItem.get_or_none(name="tt_alpha_updated")
        assert item is not None

    async def test_delete(self):
        await TtItem.filter(name="tt_alpha_updated").delete()
        assert await TtItem.get_or_none(name="tt_alpha_updated") is None


@pytest.mark.asyncio
class TestTransactions:
    async def test_atomic_commit(self):
        async with Tortoise.get_connection("default")._in_transaction():
            await TtItem.create(name="tt_tx_commit")
        assert await TtItem.get_or_none(name="tt_tx_commit") is not None

    async def test_atomic_rollback(self):
        try:
            async with Tortoise.get_connection("default")._in_transaction():
                await TtItem.create(name="tt_tx_rollback")
                raise ValueError("force rollback")
        except ValueError:
            pass
        assert await TtItem.get_or_none(name="tt_tx_rollback") is None


@pytest.mark.asyncio
class TestJSONB:
    async def test_json_field(self):
        await TtItem.create(name="tt_json", meta={"nested": {"a": 1}})
        item = await TtItem.get(name="tt_json")
        assert item.meta["nested"]["a"] == 1
