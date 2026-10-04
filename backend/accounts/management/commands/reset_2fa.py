from django.core.management.base import BaseCommand, CommandError

from accounts import services
from accounts.models import User, normalize_email


class Command(BaseCommand):
    help = "Remove a user's second factor; they enrol again at the next login."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email: str, **options):
        user = User.objects.filter(email=normalize_email(email)).first()
        if user is None:
            raise CommandError(f"No user has the email address {email!r}.")
        services.reset_second_factor(user)
        self.stdout.write(f"Two-factor authentication was reset for {user.email}.")
