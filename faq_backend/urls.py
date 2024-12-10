from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from webhook import views

def home(request):
    return HttpResponse("Welcome to the homepage.")

urlpatterns = [
    path('', home),
    path('admin/', admin.site.urls),
    path('api/', include('faq.urls')),  # FAQ 앱 관련 API
    path('public/', include('faq_public.urls')),
    path('webhook/', views.webhook, name='webhook'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)