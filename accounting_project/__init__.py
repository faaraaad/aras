# accounting_project/__init__.py
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    pass
