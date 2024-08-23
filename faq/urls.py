from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import SignupView, LoginView, UsernameCheckView, SendVerificationCodeView, VerifyCodeView, UserStoresView, EditView

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('check-username/', UsernameCheckView.as_view(), name='check-username'),
    path('send-code/', SendVerificationCodeView.as_view(), name='send-code'),
    path('verify-code/', VerifyCodeView.as_view(), name='verify-code'),
    path('user-stores/', UserStoresView.as_view(), name='user-stores'),
    path('user-stores/<int:store_id>/', UserStoresView.as_view(), name='user-store-detail'),  # GET 및 PUT (특정 가게)
    path('edit/', EditView.as_view(), name='edit-request'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
