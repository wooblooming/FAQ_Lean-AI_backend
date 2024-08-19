from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('faq.urls')),  # FAQ 앱 관련 API
]
