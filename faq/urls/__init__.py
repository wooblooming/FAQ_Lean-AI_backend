# __init__.py
from .auth_urls import urlpatterns as auth_urls
from .store_urls import urlpatterns as store_urls
from .menu_urls import urlpatterns as menu_urls
from .user_urls import urlpatterns as user_urls
from .utility_urls import urlpatterns as utility_urls

urlpatterns = auth_urls + store_urls + menu_urls + user_urls + utility_urls
