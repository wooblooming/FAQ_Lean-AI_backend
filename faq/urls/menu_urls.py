# menu_urls.py
from rest_framework.routers import DefaultRouter
from ..views.menu_views import MenuViewSet

router = DefaultRouter()
router.register(r'menus', MenuViewSet, basename='menus')

urlpatterns = router.urls
