from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    #path('faq/', include('faq.urls')),  # faq 앱의 URL 패턴을 포함
    #path('', include('faq.urls')),
    path('accounts/', include('allauth.urls')),  # 계정 관련 URL
    path('api/', include('rest_framework.urls')),  # API 관련 URL
]
