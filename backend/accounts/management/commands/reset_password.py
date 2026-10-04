from django.core.management.base import BaseCommand, CommandError

from accounts import services
from accounts.models import User, normalize_email


class Command(BaseCommand):
    help = "Print a single-use link that lets a user set a new password."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email: str, **options):
        user = User.objects.filter(email=normalize_email(email)).first()
        if user is None:
            raise CommandError(f"No user has the email address {email!r}.")
        url, _ = services.create_reset_link(user)
        self.stdout.write(url)
