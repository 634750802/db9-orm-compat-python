"""Django ORM compatibility tests for db9 (psycopg2 driver).

Uses Django in standalone mode (no full project required).
"""
import os
import pytest
from urllib.parse import urlparse
from tests.conftest import get_dsn

TABLE = "dj_compat_test"

# Parse DSN for Django DATABASES config
_u = urlparse(get_dsn())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_django_orm")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _u.path.lstrip("/") or "postgres",
        "USER": _u.username or "",
        "PASSWORD": _u.password or "",
        "HOST": _u.hostname or "localhost",
        "PORT": str(_u.port or 5433),
    }
}

INSTALLED_APPS = ["django.contrib.contenttypes"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

import django
django.setup()

from django.db import models, connection
from django.db import transaction as dj_transaction


class DjItem(models.Model):
    name = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    meta = models.JSONField(null=True, blank=True)

    class Meta:
        app_label = "contenttypes"
        db_table = TABLE


@pytest.fixture(scope="module", autouse=True)
def setup_table():
    with connection.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                id BIGSERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                active BOOLEAN DEFAULT TRUE,
                meta JSONB
            )
        """)
    yield
    with connection.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")


class TestConnection:
    def test_connect(self):
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1

    def test_server_version(self):
        assert connection.pg_version > 0


class TestCRUD:
    def test_create(self):
        item = DjItem.objects.create(name="dj_alpha", active=True, meta={"k": "v"})
        assert item.pk is not None

    def test_read(self):
        items = DjItem.objects.filter(name="dj_alpha")
        assert items.exists()

    def test_update(self):
        DjItem.objects.filter(name="dj_alpha").update(name="dj_alpha_updated")
        assert DjItem.objects.filter(name="dj_alpha_updated").exists()

    def test_delete(self):
        DjItem.objects.filter(name="dj_alpha_updated").delete()
        assert not DjItem.objects.filter(name="dj_alpha_updated").exists()


class TestTransactions:
    def test_atomic_commit(self):
        with dj_transaction.atomic():
            DjItem.objects.create(name="dj_tx_commit")
        assert DjItem.objects.filter(name="dj_tx_commit").exists()

    def test_atomic_rollback(self):
        try:
            with dj_transaction.atomic():
                DjItem.objects.create(name="dj_tx_rollback")
                raise ValueError("force rollback")
        except ValueError:
            pass
        assert not DjItem.objects.filter(name="dj_tx_rollback").exists()

    def test_savepoint(self):
        with dj_transaction.atomic():
            DjItem.objects.create(name="dj_sp_outer")
            try:
                with dj_transaction.atomic():
                    DjItem.objects.create(name="dj_sp_inner")
                    raise ValueError("rollback inner")
            except ValueError:
                pass
        assert DjItem.objects.filter(name="dj_sp_outer").exists()
        assert not DjItem.objects.filter(name="dj_sp_inner").exists()


class TestJSONB:
    def test_json_field(self):
        DjItem.objects.create(name="dj_json", meta={"nested": {"a": 1}})
        item = DjItem.objects.get(name="dj_json")
        assert item.meta["nested"]["a"] == 1


class TestIntrospection:
    def test_get_table_list(self):
        with connection.cursor() as cur:
            tables = connection.introspection.get_table_list(cur)
            table_names = [t.name for t in tables]
            assert TABLE in table_names

    def test_get_table_description(self):
        with connection.cursor() as cur:
            desc = connection.introspection.get_table_description(cur, TABLE)
            col_names = [d.name for d in desc]
            assert "id" in col_names
            assert "name" in col_names
