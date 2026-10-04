import os

from config.env import load_config
from django.core.management import call_command
from django.core.management.base import BaseCommand

from accounts.setup import bootstrap


class Command(BaseCommand):
    help = "Migrate the database, then create the first admin or a setup token."

    def handle(self, *args, **options):
        # Migration progress goes to stderr: stdout carries only the token line.
        call_command("migrate", interactive=False, stdout=self.stderr)
        bootstrap(load_config(os.environ), self.stdout)
