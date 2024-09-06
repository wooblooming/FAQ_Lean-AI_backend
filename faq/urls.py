from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import (
    SignupView, LoginView, UsernameCheckView, 
    SendVerificationCodeView, VerifyCodeView, 
    UserStoresListView, UserStoreDetailView, 
    EditView, PasswordResetView, UserProfileView,
    UserProfilePhotoUpdateView, CustomerStoreView,
    GenerateQrCodeView, QrCodeImageView
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('check-username/', UsernameCheckView.as_view(), name='check-username'),
    path('send-code/', SendVerificationCodeView.as_view(), name='send-code'),
    path('verify-code/', VerifyCodeView.as_view(), name='verify-code'),
    path('user-stores/', UserStoresListView.as_view(), name='user-stores'),  # 모든 스토어
    path('user-stores/<int:store_id>/', UserStoreDetailView.as_view(), name='user-store-detail'),  # 특정 스토어
    path('edit/', EditView.as_view(), name='edit-request'),
    path('reset-password/', PasswordResetView.as_view(), name='reset-password'),
    path('user-profile/', UserProfileView.as_view(), name='user-profile'),
    path('update-profile-photo/', UserProfilePhotoUpdateView.as_view(), name='update-profile-photo'),
    path('storesinfo/', CustomerStoreView.as_view(), name='store_info'),
    path('generate-qr-code/', GenerateQrCodeView.as_view(), name='generate-qr-code'),
    path('qrCodeImage/', QrCodeImageView.as_view(), name='qr_code_image'),
    
]
