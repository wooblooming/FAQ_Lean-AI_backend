from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import (
    SignupView, LoginView, UsernameCheckView, 
    SendVerificationCodeView, VerifyCodeView, 
    UserPublicListView, UserPublicDetailView, 
    EditView, PasswordResetView, UserProfileView,
    UserProfilePhotoUpdateView, CustomerPublicView,
    GenerateQrCodeView, QrCodeImageView,
    DeactivateAccountView,StatisticsView, ComplaintsView, 
    ComplaintsRegisterView, UpdateComplaintStatusView,
    PublicCreateView, PublicListView, PublicDetailView,
    UserPublicInfoView, DepartmentListView
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('check-username/', UsernameCheckView.as_view(), name='check-username'),
    path('send-code/', SendVerificationCodeView.as_view(), name='send-code'),
    path('verify-code/', VerifyCodeView.as_view(), name='verify-code'),
    path('user-public-info/', UserPublicInfoView.as_view(), name='user_public_info'),
    path('public-register/', PublicCreateView.as_view(), name='public_register'),
    path('public-institutions/', PublicListView.as_view(), name='public_institutions'),
    path('public-details/', PublicDetailView.as_view(), name='public_details'),
    path('generate-qr-code/', GenerateQrCodeView.as_view(), name='generate-qr-code'),
    path('qrCodeImage/', QrCodeImageView.as_view(), name='qr_code_image'),
    path('user-profile/', UserProfileView.as_view(), name='user-profile'),
    path('update-profile-photo/', UserProfilePhotoUpdateView.as_view(), name='update-profile-photo'),
    path('edit/', EditView.as_view(), name='edit-request'),
    path('complaints/', ComplaintsView.as_view(), name='complaint-list'),              
    path('complaints/register/', ComplaintsRegisterView.as_view(), name='complaint-create'), 
    path('department-list/', DepartmentListView.as_view(), name='department-list'),

    path('statistics/', StatisticsView.as_view(), name='statistics'),
    path('complaints/', ComplaintsView.as_view(), name='complaint-list'),               # 민원 목록 조회
    path('complaints/register/', ComplaintsRegisterView.as_view(), name='complaint-create'), # 민원 등록
    path('complaints/<str:id>/status/', UpdateComplaintStatusView.as_view(), name='complaint-status-update'), # 민원 상태 업데이트


        
    path('reset-password/', PasswordResetView.as_view(), name='reset-password'),
    path('deactivate-account/', DeactivateAccountView.as_view(), name='deactivate-account'),

    path('user-publics/<int:public_id>/', UserPublicDetailView.as_view(), name='user_public_detail'),
   
    
    path('public-info/', CustomerPublicView.as_view(), name='public_info'),
]