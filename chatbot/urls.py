# faq/urls.py

from django.urls import path
from .views import DialogflowRequestView

urlpatterns = [
    path('chating/', DialogflowRequestView.as_view(), name='chating'),

]
