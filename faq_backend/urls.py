from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('faq/', include('faq.urls')),  # faq 앱의 URL 패턴을 포함
    path('', include('faq.urls')),  # 필요에 따라 루트 경로에 대해서도 faq의 URL 패턴을 사용 가능
    path('accounts/', include('allauth.urls')),
]
