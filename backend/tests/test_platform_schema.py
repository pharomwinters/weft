from django.db import connection


def test_django_tables_live_in_platform_schema(db):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_schema FROM information_schema.tables "
            "WHERE table_name = 'django_migrations'"
        )
        schemas = [row[0] for row in cursor.fetchall()]
    assert schemas == ["platform"]
