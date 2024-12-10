from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import (
    SignupView, LoginView, UsernameCheckView, 
    SendVerificationCodeView, VerifyCodeView, 
    RegisterDataView, RequestServiceView, 
    PasswordResetView, UserProfileView,
    UserProfilePhotoUpdateView, StoreView, StoreUpdateView,
    GenerateQrCodeView, QrCodeImageView, MenuListView,
    DeactivateAccountView, StatisticsView, 
    FeedListView, FeedUploadView, FeedDeleteView, FeedRenameView,
    PushTokenView, SendPushNotificationView,
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('check-username/', UsernameCheckView.as_view(), name='check-username'),
    path('send-code/', SendVerificationCodeView.as_view(), name='send-code'),
    path('verify-code/', VerifyCodeView.as_view(), name='verify-code'),
    path('storesinfo/', StoreView.as_view(), name='store_info'),
    path('storesinfo-update/<str:store_id>/', StoreUpdateView.as_view(), name='store_info_update'),
    path('reset-password/', PasswordResetView.as_view(), name='reset-password'),
    path('user-profile/', UserProfileView.as_view(), name='user-profile'),
    path('update-profile-photo/', UserProfilePhotoUpdateView.as_view(), name='update-profile-photo'),
    path('register-data/', RegisterDataView.as_view(), name='edit-request'),
    path('request-service/', RequestServiceView.as_view(), name='request_data'),
    path('generate-qr-code/', GenerateQrCodeView.as_view(), name='generate-qr-code'),
    path('qrCodeImage/', QrCodeImageView.as_view(), name='qr_code_image'),
    path('menu-details/', MenuListView.as_view(), name='menu-details'),
    path('statistics/', StatisticsView.as_view(), name='statistics'),
    path('feed/', FeedListView.as_view(), name='feed_list'),
    path('feed-upload/', FeedUploadView.as_view(), name='feed_upload'),
    path('feed-delete/', FeedDeleteView.as_view(), name='feed_delete'),
    path('feed-rename/', FeedRenameView.as_view(), name='feed_rename'),
    path('deactivate-account/', DeactivateAccountView.as_view(), name='deactivate-account'),
    path('register-push-token/', PushTokenView.as_view(), name='register_push_token'),
    path('send-push-notification/', SendPushNotificationView.as_view(), name='send_push_notification'),

]