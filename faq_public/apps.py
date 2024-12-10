from django.apps import AppConfig


class FaqPublicConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'faq_public'

    def ready(self):
        import faq_public.signals 
