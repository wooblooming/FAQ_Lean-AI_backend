from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('faq.urls')),  # FAQ 앱 관련 API
    path('chatbot/', include('chatbot.urls')),  # 챗봇 앱 관련 API
]
