import logging

logger = logging.getLogger('faq')

class FAQPublicRouter:
    def db_for_read(self, model, **hints):
        logger.debug(f"db_for_read called for model: {model}")
        if model._meta.app_label == 'faq_public':
            logger.debug("Reading from faq_public_db")
            return 'faq_public_db'
        return 'default'

    def db_for_write(self, model, **hints):
        logger.debug(f"db_for_write called for model: {model}")
        if model._meta.app_label == 'faq_public':
            logger.debug("Writing to faq_public_db")
            return 'faq_public_db'
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._meta.app_label == 'faq_public' or obj2._meta.app_label == 'faq_public':
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'faq_public':
            return db == 'faq_public_db'
        return db == 'default'
