"""
WSGI config for the anonymization project.
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webapp_django.config.settings")
application = get_wsgi_application()
