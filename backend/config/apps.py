from django.apps import AppConfig
from django.db import connections
from django.db.models.signals import pre_migrate


def create_platform_schema(using, **kwargs):
    with connections[using].cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS platform")


class ConfigConfig(AppConfig):
    name = "config"

    def ready(self):
        pre_migrate.connect(
            create_platform_schema, dispatch_uid="create_platform_schema"
        )
