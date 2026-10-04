import os

from .settings import *  # noqa: F403

DEBUG = os.environ.get("DJANGO_DEBUG", "") == "1"
