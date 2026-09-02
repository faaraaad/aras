"""
WSGI config for accounting_project.
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'accounting_project.settings')

application = get_wsgi_application()
