# utility_urls.py
from django.urls import path
from ..views import (
    GenerateQrCodeView, QrCodeImageView,
    RequestServiceView, StatisticsView, 
)

urlpatterns = [
    path('generate-qr-code/', GenerateQrCodeView.as_view(), name='generate_qr_code'),
    path('qrCodeImage/', QrCodeImageView.as_view(), name='qr_code_image'),
    path('request-service/', RequestServiceView.as_view(), name='request_data'),
    path('statistics/', StatisticsView.as_view(), name='statistics'),

]