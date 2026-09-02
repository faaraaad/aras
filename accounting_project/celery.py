import os
try:
    from celery import Celery

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'accounting_project.settings')

    app = Celery('accounting_project')
    app.config_from_object('django.conf:settings', namespace='CELERY')
    app.autodiscover_tasks()
except ImportError:
    # Celery is optional for standalone testing without celery installed
    app = None
