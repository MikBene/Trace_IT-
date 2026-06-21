from django.apps import AppConfig


class TraceItConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Trace_It'

    def ready(self):
        import Trace_It.models  # Ensures signals are registered