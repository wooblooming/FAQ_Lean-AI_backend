from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import (
    SignupView, LoginView, UsernameCheckView,
    SendVerificationCodeView, VerifyCodeView,
    PasswordResetView, DeactivateAccountView,
    UserPublicInfoView, PublicInfoView, 
    PublicCreateView, PublicListView, PublicDetailView,
    GenerateQrCodeView, QrCodeImageView,
    UserProfileView, UserProfilePhotoUpdateView,
    RequestServiceView, StatisticsView, 
    ComplaintsView, ComplaintsRegisterView, ComplaintTransferView,
    ComplaintUpdateStatusView, ComplaintsCustomerView, ComplaintAnswerView,
    DepartmentListView, DepartmentCreateAPIView, DepartmentUpdateView,

)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('check-username/', UsernameCheckView.as_view(), name='check_username'),
    path('send-code/', SendVerificationCodeView.as_view(), name='send_code'),
    path('verify-code/', VerifyCodeView.as_view(), name='verify_code'),
    path('user-public-info/', UserPublicInfoView.as_view(), name='/user_public_info'),
    path('public-info/', PublicInfoView.as_view(), name='public_info'),
    path('public-register/', PublicCreateView.as_view(), name='public_register'), # 공공기관 등록
    path('public-institutions/', PublicListView.as_view(), name='public_institutions'), # 등록된 공공기관 전체 보기
    path('public-details/', PublicDetailView.as_view(), name='public_details'), # 선택된 공공기괸의 정보 보기
    path('generate-qr-code/', GenerateQrCodeView.as_view(), name='generate_qr_code'),
    path('qrCodeImage/', QrCodeImageView.as_view(), name='qr_code_image'),
    path('user-profile/', UserProfileView.as_view(), name='user_profile'),
    path('update-profile-photo/', UserProfilePhotoUpdateView.as_view(), name='update_profile_photo'),
    path('request-service/', RequestServiceView.as_view(), name='request_data'),
    path('complaints/', ComplaintsView.as_view(), name='complaint_list'),              
    path('complaints/register/', ComplaintsRegisterView.as_view(), name='complaint_create'), 
    path('complaints/<str:id>/status/', ComplaintUpdateStatusView.as_view(), name='complaint_status_update'), # 민원 상태 업데이트
    path('complaint-customer/', ComplaintsCustomerView.as_view(), name='complaint_customer'),
    path('complaint-transfer/',ComplaintTransferView.as_view(), name='complaint_transfer'),
    path('complaints-answer/',ComplaintAnswerView.as_view(), name='complaint_answer'),
    path('department-list/', DepartmentListView.as_view(), name='department_list'),
    path('department-create/', DepartmentCreateAPIView.as_view(), name='department-create'),
    path('department-update/', DepartmentUpdateView.as_view(), name='update-department'),

    path('statistics/', StatisticsView.as_view(), name='statistics'),
        
    path('reset-password/', PasswordResetView.as_view(), name='reset_password'),
    path('deactivate-account/', DeactivateAccountView.as_view(), name='deactivate_account'),

]